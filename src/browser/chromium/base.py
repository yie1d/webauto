import asyncio
import dataclasses
import random
import subprocess

from cdpkit.connection import CDPSession, CDPSessionManager
from cdpkit.exceptions import PageNotFoundError
from cdpkit.protocol import Browser, Network, Storage, Target
from cdpkit.protocol.base import RESULT_TYPE, CDPEvent, CDPMethod
from src.browser.constants import BrowserType, State
from src.browser.options import ChromeOptions, EdgeOptions, Options
from src.browser.page import PageSession
from src.logger import logger
from src.utils import TempDirectoryFactory


@dataclasses.dataclass
class BrowserInfo:
    """
    记录浏览器信息
        配置参数
        远程调试端口号
        启动命令
    """
    options: Options
    remote_port: int
    start_command: list[str] | None = None

    def _delete_options_arguments(self, options_args_dict: dict[str, str]) -> None:
        """
        删除options_args中的参数
        """
        need_delete_args = ('--remote-debugging-port', )

        for need_delete_arg in need_delete_args:
            if need_delete_arg in options_args_dict:
                logger.warning(f'The custom *{need_delete_arg}* parameter will be overwritten by '
                               f'the value {self.remote_port}')
                self.options.remove_argument(options_args_dict[need_delete_arg])

    def _set_headless(self, options_args_dict: dict[str, str]) -> None:
        if self.options.headless:
            headless_arg = '--headless'
            if headless_arg not in options_args_dict:
                self.options.add_argument(headless_arg)

    def _set_user_data_dir(self, options_args_dict: dict[str, str]) -> None:
        user_data_dir_arg = '--user-data-dir'

        if self.options.user_data_dir:
            if user_data_dir_arg in options_args_dict:
                self.options.remove_argument(options_args_dict[user_data_dir_arg])
            else:
                self.options.add_argument(f'{user_data_dir_arg}={self.options.user_data_dir}')
        else:
            if user_data_dir_arg not in options_args_dict:
                temp_dir = TempDirectoryFactory().create_temp_dir('chromium_user_data_dir-')
                self.options.add_argument(f'{user_data_dir_arg}={temp_dir.name}')

    def __post_init__(self):
        options_args_dict = {arg.split('=')[0]: arg for inx, arg in enumerate(self.options.arguments)}
        self._delete_options_arguments(options_args_dict)

        self._set_headless(options_args_dict)

        self._set_user_data_dir(options_args_dict)

        self.options.add_default_arguments()

        self.options.add_argument(f'--remote-debugging-port={self.remote_port}')

        self.start_command = [
            self.options.executable_path or self.options.get_default_executable_path(),
            *self.options.arguments
        ]


class BrowserProcess:
    """
    浏览器进程控制器
    """
    def __init__(self, start_command: list[str]):
        self._start_command = start_command
        self._process: subprocess.Popen | None = None
        self._status: State = State.INITIALIZED

    @staticmethod
    def _run_process(command: list[str]) -> subprocess.Popen:
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def run(self) -> None:
        if self._process is None and self._process != State.STARTED:
            self._process = self._run_process(self._start_command)
            self._status = State.STARTED

    def stop(self) -> None:
        if self._process and self._status == State.STARTED:
            logger.info('Stopping process')
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                logger.info('process killed')
            self._process = None
            self._status = State.STOPPED


class Chromium:
    def __init__(
        self,
        options: Options | None = None,
        remote_port: int | None = None,
        browser_type: BrowserType | None = None
    ):
        if options is None:
            match browser_type:
                case BrowserType.EDGE:
                    options = EdgeOptions()
                case BrowserType.CHROME:
                    options = ChromeOptions()
                case _:
                    options = ChromeOptions()

        if remote_port is None:
            remote_port = random.randint(9222, 9322)
        logger.info(f'remote_port: {remote_port}')

        self._info = BrowserInfo(
            options=options,
            remote_port=remote_port
        )

        self._process = BrowserProcess(self._info.start_command)
        self._session_manager = CDPSessionManager(self._info.remote_port)

        self._session: CDPSession | None = None
        self._state = State.INITIALIZED

    @property
    async def pages(self) -> list[Target.TargetID]:
        pages = []
        for page in await self._get_all_pages():
            pages.append(page.targetId)
        return pages

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # self.quit()
        ...

    async def _get_all_pages(self) -> list[Target.TargetInfo]:
        return (await self.execute_method(Target.GetTargets(filter_=[{
            'type': 'page',
            'exclude': False
        }]))).targetInfos

    async def _verify_browser_running(self):
        if not await self._is_browser_running():
            raise Exception('Browser is not running')

    async def _is_browser_running(self, timeout: int = 5) -> bool:
        for _ in range(timeout):
            if await self._session.ping():
                return True
            await asyncio.sleep(1)
        return False

    async def execute_method(self, cdp_method: CDPMethod[RESULT_TYPE], timeout: int = 60) -> RESULT_TYPE:
        return await self._session.execute(
            cdp_method,
            timeout
        )

    async def launch(self):
        self._process.run()

        self._session = self._session_manager.get_session()

        await self._verify_browser_running()

        self._state = State.STARTED

    async def connect(self, remote_port: int | None = None) -> PageSession:
        if remote_port and remote_port != self._info.remote_port:
            self._info.remote_port = remote_port
            self._session_manager = CDPSessionManager(self._info.remote_port)
            self._session = self._session_manager.get_session()
        await self._verify_browser_running()

        return await self.get_page()

    def quit(self) -> None:
        if self._state == State.STARTED:
            self._state = State.STOPPED
            # self._process.stop()
            # TempDirectoryFactory().clean_up()

    async def get_page(self, page_id: Target.TargetID | None = None) -> PageSession:
        pages = await self.pages

        if page_id is not None:
            if page_id not in pages:
                raise PageNotFoundError(f'Page {page_id} not found')
            return PageSession(self._session_manager, page_id)
        else:
            if len(pages) == 0:
                return await self.new_page()
            else:
                return PageSession(self._session_manager, pages[-1])

    async def new_page(self, url: str = '') -> PageSession:
        target_id = (await self.execute_method(Target.CreateTarget(url=url))).targetId

        return PageSession(self._session_manager, target_id)

    async def set_download_path(self, path: str) -> None:
        await self.execute_method(Browser.SetDownloadBehavior(
            behavior='allow',
            download_path=path
        ))

    async def set_cookies(self, cookies: list[dict]):
        """
        Sets cookies in the browser.

        Args:
            cookies (list[dict]): A list of dictionaries containing the cookie data.
        """
        await self.execute_method(Storage.SetCookies(cookies=cookies))
        await self.execute_method(Network.SetCookies(cookies=cookies))

    async def delete_all_cookies(self):
        """
        Deletes all cookies from the browser.
        """
        await self.execute_method(Storage.ClearCookies())
        await self.execute_method(Network.ClearBrowserCookies())

    async def get_cookies(self) -> list[Network.Cookie]:
        return (await self.execute_method(Storage.GetCookies())).cookies

    async def on(self, event: type[CDPEvent], callback: callable, temporary: bool = False) -> int:
        return await self._session.event_handler.register_callback(
            event.event_name, callback, temporary
        )
