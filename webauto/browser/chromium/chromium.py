import asyncio
import platform
import stat
from pathlib import Path

from pydantic import PrivateAttr

from cdpkit.connection import CDPSessionExecutor, CDPSessionManager
from cdpkit.exception import BrowserLaunchError, ExecutableNotFoundError
from cdpkit.protocol import Target
from webauto.browser.chromium.context import BrowserInfo, BrowserProcess
from webauto.browser.chromium.options import Options


class BrowserHandler(CDPSessionExecutor):
    _page_load_timeout: int = PrivateAttr(default=30)

    async def set_page_load_timeout(self, timeout: int):
        self._page_load_timeout = timeout

    async def get_tab(self, target_id: Target.TargetID = 'browser'):
        # todo get_tab
        ...


class BrowserType(BrowserHandler):
    name: str
    browser_path_dict: dict[str, list[str]] | None = None

    _info: BrowserInfo | None = PrivateAttr()
    _process: BrowserProcess | None = PrivateAttr()

    async def connect(
        self,
        host: str,
        port: int | str
    ):
        self._info = BrowserInfo(host=host, remote_port=int(port))
        self._process = BrowserProcess(browser_info=self._info)

        await self._init_connect()

    async def launch(
        self,
        options: Options | None,
        port: int | str | None = None
    ):
        if options is None:
            options = Options()

        if not options.executable_path:
            options.executable_path = self._get_default_executable_path()
        else:
            self._validate_browser_paths([options.executable_path])

        self._info = BrowserInfo(
            options=options,
            remote_port=port
        )

        self._process = BrowserProcess(browser_info=self._info)
        self._process.run()

        await self._init_connect()

    async def _verify_browser_running(self):
        if not await self._is_browser_running():
            raise BrowserLaunchError('Browser is not running')

    async def _is_browser_running(self, timeout: int = 5) -> bool:
        for _ in range(timeout):
            if await self._session.ping():
                return True
            await asyncio.sleep(1)
        return False

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

    async def _init_connect(self):
        self._session_manager = CDPSessionManager(ws_endpoint=f'{self._info.host}:{self._info.remote_port}')
        self._session = await self._session_manager.get_session()
        await self._verify_browser_running()
        await self._init_browser_session()

        return await self.get_tab()

    @staticmethod
    def _validate_browser_paths(paths: list[str]) -> str | None:
        for path in paths:
            _path = Path(path)
            if _path.exists() and _path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                return path

        raise ExecutableNotFoundError(f'None of the executable paths exist, {paths}.')

    def _get_default_executable_path(self) -> str:
        if self.browser_path_dict is None:
            raise NotImplementedError(f'{self.name} does not support auto-detection of executable path')

        os_name = platform.system()

        browser_path = self.browser_path_dict.get(os_name)

        if not browser_path:
            raise ValueError('Unsupported OS')

        return self._validate_browser_paths(browser_path)
