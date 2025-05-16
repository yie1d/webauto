import asyncio

from cdpkit.connection import CDPSessionManager
from cdpkit.protocol import DOM, RESULT_TYPE, CDPEvent, CDPMethod, Page, Runtime, Target
from src.browser.constants import PageSessionState
from src.browser.element import ElementFinder
from src.logger import logger


class PageSession(ElementFinder):
    def __init__(self, session_manager: CDPSessionManager, target_id: Target.TargetID, page_load_timeout: int = 30):
        super().__init__(
            session=session_manager.get_session(target_id),
            session_manager=session_manager
        )

        self._target_id = target_id
        self._page_load_timeout = page_load_timeout
        self._state = PageSessionState.DISABLED

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

    async def _init_page(self):
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
        self._state = PageSessionState.ENABLED
        await self._init_page()

    async def _judge_session_state(self):
        if self._state == PageSessionState.DISABLED:
            await self.enable_page_session()
        elif self._state == PageSessionState.CLOSED:
            raise RuntimeError('Page session has closed')

    async def execute_method(self, cdp_method: CDPMethod[RESULT_TYPE], timeout: int = 60) -> RESULT_TYPE:
        await self._judge_session_state()

        return await super().execute_method(cdp_method, timeout)

    async def on(self, event: type[CDPEvent], callback: callable, temporary: bool = False) -> int:
        await self._judge_session_state()

        return await super().on(event, callback, temporary)

    def __str__(self):
        return f'PageSession(target_id={self._target_id})'

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
        await self.execute_method(Target.CloseTarget(target_id=self._target_id))
        self._state = PageSessionState.CLOSED

    async def get(self, url: str):
        await self.execute_method(Page.Navigate(url=url))

        await self._init_page()

    async def new_page(self, url: str = '') -> 'PageSession':
        target_id = (await self.execute_method(Target.CreateTarget(url=url))).targetId

        return PageSession(self._session_manager, target_id, self._page_load_timeout)

    async def refresh(self):
        await self.execute_method(Page.Reload())

        await self._init_page()
