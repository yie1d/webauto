import asyncio
from pathlib import Path
from typing import Literal

import aiofiles

from cdpkit.connection import CDPSession, CDPSessionManager
from cdpkit.protocol import DOM, RESULT_TYPE, Browser, CDPEvent, CDPMethod, Page, Runtime, Target
from src.browser.constants import TabState
from src.browser.element import ElementFinder
from src.logger import logger
from src.utils import decode_base64_to_bytes, get_path_ext


class Tab(ElementFinder):
    def __init__(
        self,
        session: CDPSession,
        session_manager: CDPSessionManager,
        target_id: Target.TargetID,
        browser_context_id: Browser.BrowserContextID | None = None,
        page_load_timeout: int = 30
    ):
        super().__init__(
            session=session,
            session_manager=session_manager
        )

        self._target_id = target_id
        self._browser_context_id = browser_context_id
        self._page_load_timeout = page_load_timeout
        self._state = TabState.DISABLED

    @property
    def target_id(self):
        return self._target_id

    @classmethod
    async def create_obj(
        cls,
        session_manager: CDPSessionManager,
        target_id: Target.TargetID,
        browser_context_id: Browser.BrowserContextID | None,
        page_load_timeout: int
    ):
        return cls(
            session=await session_manager.get_session(target_id),
            session_manager=session_manager,
            target_id=target_id,
            browser_context_id=browser_context_id,
            page_load_timeout=page_load_timeout
        )

    async def _on_dialog_opening(self, event_data: Page.JavascriptDialogOpening):
        logger.debug(f'Page.JavascriptDialogOpening: {event_data}')

    async def _on_dialog_closed(self, event_data: Page.JavascriptDialogClosed):
        logger.debug(f'Page.JavascriptDialogClosed: {event_data}')

    async def _wait_page_load(self):
        """Wait for the page load."""
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < self._page_load_timeout:
            if (
                await self.execute_method(Runtime.Evaluate(expression='document.readyState'))
            ).result.value == 'complete':
                return
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError('Page load timed out')

    async def _init_tab(self):
        await self._wait_page_load()
        await self.on(Page.JavascriptDialogOpening, self._on_dialog_opening)
        await self.on(Page.JavascriptDialogClosed, self._on_dialog_closed)

        await self.execute_method(Page.Enable())
        await self.execute_method(DOM.Enable())
        await self.execute_method(Runtime.Enable())

        # reset page state
        self.reset()
        await self.node

    async def enable_page_session(self):
        self._state = TabState.ENABLED
        await self._init_tab()

    async def _judge_session_state(self):
        if self._state == TabState.DISABLED:
            await self.enable_page_session()
        elif self._state == TabState.CLOSED:
            raise RuntimeError('Page session has closed')

    async def execute_method(self, cdp_method: CDPMethod[RESULT_TYPE], timeout: int = 60) -> RESULT_TYPE:
        await self._judge_session_state()

        return await super().execute_method(cdp_method, timeout)

    async def on(self, event: type[CDPEvent], callback: callable, temporary: bool = False) -> int:
        await self._judge_session_state()

        return await super().on(event, callback, temporary)

    def __str__(self):
        return f'Tab(target_id={self._target_id})'

    def __repr__(self) -> str:
        return str(self)

    async def _refresh_if_url_not_changed(self, url: str) -> bool:
        current_url = await self.current_url
        if current_url == url:
            await self.refresh()
            return True
        return False

    @property
    async def current_url(self) -> str:
        return (await self.execute_method(Target.GetTargetInfo(target_id=self._target_id))).targetInfo.url

    @property
    async def title(self) -> str:
        return (await self.execute_method(Target.GetTargetInfo(target_id=self._target_id))).targetInfo.title

    @property
    async def page_source(self) -> str:
        return (await self.execute_method(DOM.GetOuterHTML(backend_node_id=await self.backend_node_id))).outerHTML

    async def activate(self):
        await self.execute_method(Target.ActivateTarget(target_id=self._target_id))
        await self.execute_method(Page.BringToFront())

    async def close(self):
        await self.execute_method(Page.Close())
        self._state = TabState.CLOSED

    async def get(self, url: str):
        await self.execute_method(Page.Navigate(url=url))

        await self._init_tab()

    async def new_tab(self, url: str = '', browser_context_id: Browser.BrowserContextID | None = None) -> 'Tab':
        target_id = (await self.execute_method(Target.CreateTarget(
            url=url,
            browser_context_id=browser_context_id if browser_context_id is not None else self._browser_context_id
        ))).targetId

        return await Tab.create_obj(
            session_manager=self._session_manager,
            target_id=target_id,
            browser_context_id=browser_context_id if browser_context_id is not None else self._browser_context_id,
            page_load_timeout=self._page_load_timeout
        )

    async def refresh(self, ignore_cache: bool | None = None, script_to_evaluate_on_load: str | None = None,):
        await self.execute_method(Page.Reload(
            ignore_cache=ignore_cache,
            script_to_evaluate_on_load=script_to_evaluate_on_load
        ))

        await self._init_tab()

    @staticmethod
    def get_img_format(path: Path | str | None) -> Literal['jpeg', 'png', 'webp'] | None:
        ext = get_path_ext(path)

        if ext in ['jpeg', 'png', 'webp']:
            return ext
        else:
            raise TypeError(f'Invalid image format: {ext}, only jpeg, png, webp are supported')

    async def take_screenshot(
        self,
        path: Path | str | None = None,
        quality: int = 100,
        as_base64: bool = False
    ) -> str | None:
        if path is None and as_base64 is False:
            raise ValueError('Either path or as_base64 must be specified')

        img_base64 = (await self.execute_method(Page.CaptureScreenshot(
            format_=self.get_img_format(path),
            quality=quality,
        ))).data

        if as_base64:
            return img_base64

        if path:
            async with aiofiles.open(path, 'wb') as f:
                await f.write(decode_base64_to_bytes(img_base64))

        return None
