import asyncio
import platform
import stat
from pathlib import Path

from pydantic import PrivateAttr

from cdpkit.connection import CDPSessionExecutor, CDPSessionManager
from cdpkit.exception import BrowserLaunchError, ExecutableNotFoundError
from cdpkit.protocol import Target
from webauto.browser.chromium.context import BrowserInfo, BrowserProcess, ContextManager
from webauto.browser.chromium.options import Options


class BrowserType(CDPSessionExecutor):
    name: str
    browser_path_dict: dict[str, list[str]] | None = None

    _info: BrowserInfo | None = PrivateAttr(default=None)
    _process: BrowserProcess | None = PrivateAttr(default=None)

    async def connect(
        self,
        port: int | str,
        host: str = 'localhost',
    ) -> ContextManager:
        self._info = BrowserInfo(host=host, remote_port=int(port))
        self._process = BrowserProcess(browser_info=self._info)

        return await self._init_connect()

    async def launch(
        self,
        options: Options | None = None,
        port: int | str | None = None
    ) -> ContextManager:
        if options is None:
            options = Options()

        if not options.executable_path:
            options.executable_path = self._get_default_executable_path()
        else:
            self._validate_browser_paths([options.executable_path])

        self._info = BrowserInfo(
            remote_port=port,
            options=options
        )

        self._process = BrowserProcess(browser_info=self._info)
        self._process.run()

        return await self._init_connect()

    async def _is_browser_running(self, timeout: int = 5) -> bool:
        for _ in range(timeout):
            if await self.session.ping():
                return True
            await asyncio.sleep(1)
        return False

    async def _init_connect(self) -> ContextManager:
        self.session_manager = CDPSessionManager(ws_endpoint=f'{self._info.host}:{self._info.remote_port}')
        self.session = await self.session_manager.get_session()

        if not await self._is_browser_running():
            raise BrowserLaunchError('Browser is not running')

        return await ContextManager(
            browser_type=self.name,
            session_manager=self.session_manager,
            session=self.session
        ).init_manager()

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
