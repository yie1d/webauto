import asyncio
import dataclasses
import random
import subprocess
from typing import Literal

from cdpkit.connection import CDPSession, CDPSessionExecutor, CDPSessionManager
from cdpkit.exception import BrowserLaunchError, NoValidTabError, TabNotFoundError
from cdpkit.protocol import Browser, Network, Storage, Target
from src.browser.constants import BrowserState, ProcessState
from src.browser.options import ChromeOptions, Options
from src.browser.tab import Tab
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
        self._status: ProcessState = ProcessState.INITIALIZED

    @staticmethod
    def _run_process(command: list[str]) -> subprocess.Popen:
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def run(self) -> None:
        if self._process is None and self._process != ProcessState.STARTED:
            self._process = self._run_process(self._start_command)
            self._status = ProcessState.STARTED

    def stop(self) -> None:
        if self._process and self._status == ProcessState.STARTED:
            logger.info('Stopping process')
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                logger.info('process killed')
            self._process = None
            self._status = ProcessState.STOPPED


class BrowserHandler(CDPSessionExecutor):
    def __init__(
        self,
        session: CDPSession | None = None,
        session_manager: CDPSessionManager | None = None
    ):
        self._page_load_timeout = 30
        super().__init__(session=session, session_manager=session_manager)

    async def set_page_load_timeout(self, timeout: int):
        self._page_load_timeout = timeout

    async def create_browser_context(self) -> Browser.BrowserContextID:
        return (await self.execute_method(Target.CreateBrowserContext())).browserContextId

    async def delete_browser_context(self, browser_context_id: Browser.BrowserContextID) -> None:
        await self.execute_method(Target.DisposeBrowserContext(browser_context_id=browser_context_id))

    async def get_browser_contexts(self) -> list[Browser.BrowserContextID]:
        return (await self.execute_method(Target.GetBrowserContexts())).browserContextIds

    async def new_tab(self, url: str = '', browser_context_id: Browser.BrowserContextID | None = None) -> Tab:
        target_id = (await self.execute_method(
            Target.CreateTarget(url=url, browser_context_id=browser_context_id)
        )).targetId

        return await Tab.create_obj(
            session_manager=self._session_manager,
            target_id=target_id,
            browser_context_id=browser_context_id,
            page_load_timeout=self._page_load_timeout
        )

    async def _get_targets(self) -> list[Target.TargetInfo]:
        return (await self.execute_method(Target.GetTargets(filter_=[{
            'type': 'page',
            'exclude': False
        }]))).targetInfos

    async def _get_valid_target_infos(self) -> dict[Target.TargetID, Target.TargetInfo]:
        target_infos = await self._get_targets()

        valid_target_infos = {
            target_info.targetId: target_info for target_info in target_infos if 'extension' not in target_info.url
        }
        return valid_target_infos

    async def get_tab(self, target_id: Target.TargetID | None = None) -> Tab:
        valid_target_infos = await self._get_valid_target_infos()

        if target_id is not None:
            if target_id not in valid_target_infos:
                raise TabNotFoundError(f'Tab {target_id} not found')
            return await Tab.create_obj(
                session_manager=self._session_manager,
                target_id=target_id,
                browser_context_id=valid_target_infos[target_id].browserContextId,
                page_load_timeout=self._page_load_timeout
            )
        else:
            if not valid_target_infos:
                return await self.new_tab()
            else:
                last_target_id = list(valid_target_infos.keys())[-1]
                return await Tab.create_obj(
                    session_manager=self._session_manager,
                    target_id=last_target_id,
                    browser_context_id=valid_target_infos[last_target_id].browserContextId,
                    page_load_timeout=self._page_load_timeout
                )

    async def set_download_path(self, path: str, browser_context_id: Browser.BrowserContextID | None = None) -> None:
        await self.execute_method(Browser.SetDownloadBehavior(
            behavior='allow',
            browser_context_id=browser_context_id,
            download_path=path
        ))

    async def set_download_behavior(
        self,
        behavior: Literal['deny', 'allow', 'allowAndName', 'default'],
        download_path: str | None = None,
        browser_context_id: str | None = None,
        events_enabled: bool = False,
    ):
        return await self.execute_method(
            Browser.SetDownloadBehavior(
                behavior=behavior,
                download_path=download_path,
                browser_context_id=browser_context_id,
                events_enabled=events_enabled
            )
        )

    async def set_cookies(self, cookies: list[dict], browser_context_id: Browser.BrowserContextID | None = None):
        cookies = [Network.CookieParam.model_validate(cookie) for cookie in cookies]
        await self.execute_method(Storage.SetCookies(cookies=cookies, browser_context_id=browser_context_id))

    async def delete_all_cookies(self, browser_context_id: Browser.BrowserContextID | None = None):
        await self.execute_method(Storage.ClearCookies(browser_context_id=browser_context_id))

    async def get_cookies(self, browser_context_id: Browser.BrowserContextID | None = None) -> list[Network.Cookie]:
        return (await self.execute_method(Storage.GetCookies(browser_context_id=browser_context_id))).cookies

    async def get_window_id_by_target(self, target_id: Target.TargetID) -> int:
        return (await self.execute_method(
            Browser.GetWindowForTarget(target_id=target_id)
        )).windowId

    async def get_window_id_by_tab(self, tab: Tab) -> int:
        return await self.get_window_id_by_target(tab.target_id)

    async def get_window_id(self) -> int:
        valid_target_infos = await self._get_valid_target_infos()

        if not valid_target_infos:
            raise NoValidTabError

        last_target_id = list(valid_target_infos.keys())[-1]

        return await self.get_window_id_by_target(last_target_id)

    async def set_window_maximized(self, window_id: int | None = None) -> None:
        await self.execute_method(Browser.SetWindowBounds(
            window_id=await self.get_window_id() if window_id is None else window_id,
            bounds=Browser.Bounds(windowState=Browser.WindowState.MAXIMIZED)
        ))

    async def set_window_minimized(self, window_id: int | None = None) -> None:
        await self.execute_method(Browser.SetWindowBounds(
            window_id=await self.get_window_id() if window_id is None else window_id,
            bounds=Browser.Bounds(windowState=Browser.WindowState.MINIMIZED)
        ))

    async def set_window_bounds(self, bounds: Browser.Bounds | dict, window_id: int | None = None):
        if isinstance(bounds, dict):
            bounds = Browser.Bounds.model_validate(bounds)

        await self.execute_method(Browser.SetWindowBounds(
            window_id=await self.get_window_id() if window_id is None else window_id,
            bounds=bounds
        ))


class Chromium(BrowserHandler):
    def __init__(
        self,
        options: Options | None = None,
        remote_port: int | None = None
    ):
        if options is None:
            options = ChromeOptions()

        if remote_port is None:
            remote_port = random.randint(9222, 9322)
        logger.info(f'remote_port: {remote_port}')

        self._info = BrowserInfo(
            options=options,
            remote_port=remote_port
        )

        self._process = BrowserProcess(self._info.start_command)
        self._state = BrowserState.INITIALIZED

        super().__init__(
            session_manager=CDPSessionManager(self._info.remote_port)
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # self.quit()
        ...

    async def _verify_browser_running(self):
        if not await self._is_browser_running():
            raise BrowserLaunchError('Browser is not running')

    async def _is_browser_running(self, timeout: int = 5) -> bool:
        for _ in range(timeout):
            if await self._session.ping():
                return True
            await asyncio.sleep(1)
        return False

    async def _on_target_created(self, event_data: Target.TargetCreated):
        logger.debug(f'_on_target_created: {event_data}')

    async def _on_target_destroyed(self, event_data: Target.TargetDestroyed):
        logger.debug(f'_on_target_destroyed: {event_data}')

    async def _init_browser_session(self):
        await self.execute_method(Target.SetDiscoverTargets(discover=True))
        await self.on(
            Target.TargetCreated,
            self._on_target_created
        )
        await self.on(
            Target.TargetDestroyed,
            self._on_target_destroyed
        )

    async def launch(self) -> Tab:
        self._process.run()

        self._session = await self._session_manager.get_session()

        await self._verify_browser_running()
        await self._init_browser_session()

        self._state = BrowserState.STARTED

        return await self.get_tab()

    async def connect(self, remote_port: int | None = None) -> Tab:
        if remote_port and remote_port != self._info.remote_port:
            self._info.remote_port = remote_port
            self._session_manager = CDPSessionManager(self._info.remote_port)
        self._session = await self._session_manager.get_session()
        await self._verify_browser_running()
        await self._init_browser_session()
        self._state = BrowserState.STARTED
        return await self.get_tab()

    def quit(self) -> None:
        if self._state == BrowserState.STARTED:
            self._state = BrowserState.STOPPED
            self.execute_method(Browser.Close())
            # self._process.stop()
            # TempDirectoryFactory().clean_up()
