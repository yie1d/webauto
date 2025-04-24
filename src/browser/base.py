import asyncio
import dataclasses
import random
import subprocess
from enum import Enum, auto

from src.browser.managers import BrowserOptionsManager
from src.browser.options import Options
from src.cdp import Target
from src.cdp.base import CDPMethod
from src.connection.connection import CDPSession, CDPSessionManager
from src.logger import logger
from src.utils import TempDirectoryFactory


class BrowserState(int, Enum):
    """
    浏览器对象状态
        已初始化
        已启动
        已停止
    """
    INITIALIZED: int = auto()
    STARTED: int = auto()
    STOPPED: int = auto()


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

    @staticmethod
    def _run_process(command: list[str]) -> subprocess.Popen:
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def run(self) -> None:
        if self._process is None:
            self._process = self._run_process(self._start_command)

    def stop(self) -> None:
        if self._process:
            logger.info('Stopping process')
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                logger.info('process killed')
            self._process = None


class Browser:
    def __init__(
        self,
        options: Options | None = None,
        remote_port: int | None = None,
    ):
        self._browser_info = BrowserInfo(
            options=BrowserOptionsManager.initialize_options(options),
            remote_port=remote_port if remote_port else random.randint(9222, 9242)
        )
        logger.info(self._browser_info.remote_port)
        self._process = BrowserProcess(self._browser_info.start_command)
        self._cdp_session_manager = CDPSessionManager(self._browser_info.remote_port)

        self._cdp_session: CDPSession | None = None
        self._state = BrowserState.INITIALIZED
        self._pages: list[Target.TargetInfo] = []

    async def __aenter__(self):
        await self._launch_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # self.quit()
        ...

    async def _launch_browser(self):
        self._process.run()

        self._cdp_session = await self._cdp_session_manager.create_session()

        await self._verify_browser_running()
        await self._init_page()

        self._state = BrowserState.STARTED

    async def _init_page(self):
        self._pages = await self._get_all_pages()

    async def _get_all_pages(self) -> list[Target.TargetInfo]:
        return await self._execute_command(Target.getTargets(_filter=[{
            'type': 'page',
            'exclude': False
        }]))

    async def _verify_browser_running(self):
        if not await self._is_browser_running():
            raise Exception('Browser is not running')

    async def _is_browser_running(self, timeout: int = 5) -> bool:
        for _ in range(timeout):
            if await self._cdp_session.ping():
                return True
            await asyncio.sleep(1)
        return False

    async def _execute_command(self, command: CDPMethod, timeout: int = 60):
        return await self._cdp_session.execute_command(
            command,
            timeout
        )

    def quit(self) -> None:
        if self._state == BrowserState.STARTED:
            self._state = BrowserState.STOPPED
            self._process.stop()
            TempDirectoryFactory().clean_up()

    async def new_page(self, url: str = ''):
        await self._execute_command(
            Target.createTarget(url=url)
        )


async def main():
    async with Browser() as browser:
        await asyncio.sleep(10)


if __name__ == '__main__':
    asyncio.run(main())
