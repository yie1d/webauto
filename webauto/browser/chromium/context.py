from __future__ import annotations

import random
import subprocess
from collections.abc import AsyncGenerator
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr

from cdpkit.connection import CDPSessionExecutor
from cdpkit.exception import NoValidTabError, TabNotFoundError
from cdpkit.logger import logger
from cdpkit.protocol import Browser, Network, Storage, Target
from webauto.browser.chromium.options import Options
from webauto.browser.tab import Tab


class BrowserInfo(BaseModel):
    host: str = 'localhost'
    remote_port: int = random.randint(9222, 9322)
    options: Options = Options()

    def model_post_init(self, context: Any, /) -> None:
        self.options.check(self.remote_port)


class BrowserProcess(BaseModel):
    browser_info: BrowserInfo

    _process: subprocess.Popen | None = PrivateAttr(default=None)

    def run(self):
        if self._process is None and self.browser_info.options.executable_path:
            self._process = subprocess.Popen(
                [
                    self.browser_info.options.executable_path,
                    *self.browser_info.options.arguments
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

    def stop(self):
        if self._process is not None:
            logger.info('Stopping process')
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                logger.info('process killed')
            self._process = None


class BrowserContext(CDPSessionExecutor):
    context_id: Browser.BrowserContextID
    context_manager: ContextManager
    page_load_timeout: int = 30

    async def _get_targets(self) -> AsyncGenerator[Target.TargetInfo, Any]:
        targets = (await self.execute_method(Target.GetTargets(filter_=[{
            'type': 'page',
            'exclude': False
        }]))).targetInfos

        for target in targets:
            if target.browserContextId == self.context_id:
                yield target

    async def _get_valid_target_infos(self) -> dict[Target.TargetID, Target.TargetInfo]:
        valid_target_infos = {}
        async for target_info in self._get_targets():
            if 'extension' not in target_info.url:
                valid_target_infos[target_info.targetId] = target_info

        return valid_target_infos

    async def new_tab(self, url: str = '') -> Tab:
        target_id = (await self.execute_method(
            Target.CreateTarget(url=url, browser_context_id=self.context_id)
        )).targetId

        return await Tab.create_obj(
            session_manager=self.session_manager,
            target_id=target_id,
            browser_context_id=self.context_id,
            page_load_timeout=self.page_load_timeout
        )

    async def get_tab(self, target_id: Target.TargetID | None = None) -> Tab:
        valid_target_infos = await self._get_valid_target_infos()

        if target_id is not None:
            if target_id not in valid_target_infos:
                raise TabNotFoundError(f'Tab {target_id} not found')
            return await Tab.create_obj(
                session_manager=self.session_manager,
                target_id=target_id,
                browser_context_id=self.context_id,
                page_load_timeout=self.page_load_timeout
            )
        else:
            if not valid_target_infos:
                return await self.new_tab()
            else:
                last_target_id = list(valid_target_infos.keys())[-1]
                return await Tab.create_obj(
                    session_manager=self.session_manager,
                    target_id=last_target_id,
                    browser_context_id=self.context_id,
                    page_load_timeout=self.page_load_timeout
                )

    async def set_download_path(self, path: str) -> None:
        await self.execute_method(Browser.SetDownloadBehavior(
            behavior='allow',
            browser_context_id=self.context_id,
            download_path=path
        ))

    async def set_download_behavior(
        self,
        behavior: Literal['deny', 'allow', 'allowAndName', 'default'],
        download_path: str | None = None,
        events_enabled: bool = False,
    ):
        return await self.execute_method(
            Browser.SetDownloadBehavior(
                behavior=behavior,
                download_path=download_path,
                browser_context_id=self.context_id,
                events_enabled=events_enabled
            )
        )

    async def set_cookies(self, cookies: list[dict]):
        cookies = [Network.CookieParam.model_validate(cookie) for cookie in cookies]
        await self.execute_method(Storage.SetCookies(cookies=cookies, browser_context_id=self.context_id))

    async def delete_all_cookies(self):
        await self.execute_method(Storage.ClearCookies(browser_context_id=self.context_id))

    async def get_cookies(self) -> list[Network.Cookie]:
        return (await self.execute_method(Storage.GetCookies(browser_context_id=self.context_id))).cookies

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


class ContextManager(CDPSessionExecutor):
    browser_type: str
    contexts: set[Browser.BrowserContextID] = Field(default_factory=set)

    _cur_context_id: Browser.BrowserContextID | None = PrivateAttr(default=None)

    async def init_manager(self) -> ContextManager:
        all_created_contexts = set(await self._get_browser_contexts())
        all_exists_contexts = set()

        target_infos = (await self.execute_method(Target.GetTargets())).targetInfos
        for target_info in target_infos:
            all_exists_contexts.add(target_info.browserContextId)

        self.contexts = all_created_contexts | all_exists_contexts

        # By default, prioritize manually created contexts
        origin_context = all_exists_contexts - all_created_contexts
        if not origin_context:
            origin_context = all_exists_contexts
        self._cur_context_id = origin_context.pop()

        return self

    async def get_context(self, context_id: Browser.BrowserContextID | None = None) -> BrowserContext:
        if context_id is None:
            context_id = self._cur_context_id

        return BrowserContext(
            context_id=context_id,
            context_manager=self,
            session_manager=self.session_manager,
            session=self.session
        )

    async def new_context(self) -> BrowserContext:
        browser_context_id = (await self.execute_method(Target.CreateBrowserContext())).browserContextId
        self.contexts.add(browser_context_id)

        return BrowserContext(
            context_id=browser_context_id,
            context_manager=self,
            session_manager=self.session_manager,
            session=self.session
        )

    async def delete_context(self, browser_context: Browser.BrowserContextID | BrowserContext) -> None:
        if isinstance(browser_context, BrowserContext):
            browser_context_id = browser_context.context_id
        else:
            browser_context_id = browser_context

        self.contexts.remove(browser_context_id)
        await self.execute_method(Target.DisposeBrowserContext(browser_context_id=browser_context_id))

    async def _get_browser_contexts(self) -> list[Browser.BrowserContextID]:
        return (await self.execute_method(Target.GetBrowserContexts())).browserContextIds
