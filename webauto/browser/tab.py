from __future__ import annotations

from cdpkit.connection import CDPSessionManager
from cdpkit.protocol import Browser, Target
from webauto.browser.element import ElementFinder


class Tab(ElementFinder):
    target_id: Target.TargetID
    browser_context_id: Browser.BrowserContextID
    page_load_timeout: int

    @classmethod
    async def create_obj(
        cls,
        session_manager: CDPSessionManager,
        target_id: Target.TargetID,
        browser_context_id: Browser.BrowserContextID,
        page_load_timeout: int
    ):
        return cls(
            session=await session_manager.get_session(target_id),
            session_manager=session_manager,
            target_id=target_id,
            browser_context_id=browser_context_id,
            page_load_timeout=page_load_timeout
        )

    # todo
