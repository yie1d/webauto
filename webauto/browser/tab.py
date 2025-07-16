from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import PrivateAttr

import aiofiles

from cdpkit.connection import CDPSessionManager
from cdpkit.protocol import DOM, Browser, Page, Runtime, Target
from cdpkit.logger import logger
from webauto.browser.constants import JsScripts
from webauto.browser.element import ElementFinder
from webauto.browser.manager import InstanceManager
from webauto.browser.utils import decode_base64_to_bytes, get_img_format


class Tab(ElementFinder):
    target_id: Target.TargetID
    browser_context_id: Browser.BrowserContextID
    page_load_timeout: int
    tab_manager: InstanceManager[Target.TargetID, Tab]

    _event_enable: bool = PrivateAttr(default=False)

    @classmethod
    async def create_obj(
        cls,
        session_manager: CDPSessionManager,
        tab_manager: InstanceManager[Target.TargetID, Tab],
        target_id: Target.TargetID,
        browser_context_id: Browser.BrowserContextID,
        page_load_timeout: int
    ):
        tab = cls(
            session=await session_manager.get_session(target_id),
            session_manager=session_manager,
            tab_manager=tab_manager,
            target_id=target_id,
            browser_context_id=browser_context_id,
            page_load_timeout=page_load_timeout
        )
        await tab._wait_page_load()

        tab_manager[target_id] = tab
        return tab

    async def _wait_page_load(self):
        if not self._event_enable:
            await self.execute_method(Page.Enable())
            await self.execute_method(DOM.Enable())
            await self.execute_method(Runtime.Enable())
            self._event_enable = True

        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < self.page_load_timeout:
            if (await self.execute_script(JsScripts.document_ready_state())) == 'complete':
                # reset page state
                self.backend_node_id = None

                await self.node
                return
            await asyncio.sleep(0.5)
        else:
            raise TimeoutError('Page load timed out')

    async def _refresh_if_url_not_changed(self, url: str) -> bool:
        current_url = await self.current_url
        if current_url == url:
            await self.refresh()
            return True
        return False

    @property
    async def current_url(self) -> str:
        return (await self.execute_method(Target.GetTargetInfo(target_id=self.target_id))).targetInfo.url

    @property
    async def title(self) -> str:
        return (await self.execute_method(Target.GetTargetInfo(target_id=self.target_id))).targetInfo.title

    @property
    async def page_source(self) -> str:
        return (await self.execute_method(DOM.GetOuterHTML(backend_node_id=self.backend_node_id))).outerHTML

    async def activate(self):
        await self.execute_method(Target.ActivateTarget(target_id=self.target_id))
        await self.execute_method(Page.BringToFront())

    async def close(self):
        await self.execute_method(Page.Close())
        await self.session_manager.remove_session(self.target_id)
        await self.session.close()

    async def go_to(self, url: str):
        await self.execute_method(Page.Navigate(url=url))

        await self._wait_page_load()

    async def new_tab(self, url: str = '', browser_context_id: Browser.BrowserContextID | None = None) -> Tab:
        target_id = (await self.execute_method(Target.CreateTarget(
            url=url,
            browser_context_id=browser_context_id if browser_context_id is not None else self.browser_context_id
        ))).targetId

        return await Tab.create_obj(
            session_manager=self.session_manager,
            tab_manager=self.tab_manager,
            target_id=target_id,
            browser_context_id=browser_context_id if browser_context_id is not None else self.browser_context_id,
            page_load_timeout=self.page_load_timeout
        )

    async def refresh(self, ignore_cache: bool | None = None, script_to_evaluate_on_load: str | None = None,):
        await self.execute_method(Page.Reload(
            ignore_cache=ignore_cache,
            script_to_evaluate_on_load=script_to_evaluate_on_load
        ))

        await self._wait_page_load()

    async def take_screenshot(
        self,
        path: Path | str | None = None,
        quality: int = 100,
        as_base64: bool = False
    ) -> str | None:
        if path is None and as_base64 is False:
            raise ValueError('Either path or as_base64 must be specified')

        img_base64 = (await self.execute_method(Page.CaptureScreenshot(
            format_=get_img_format(path),
            quality=quality,
        ))).data

        if as_base64:
            return img_base64

        if path:
            async with aiofiles.open(path, 'wb') as f:
                await f.write(decode_base64_to_bytes(img_base64))

        return None

    async def print_to_pdf(
        self,
        path: str | None = None,
        landscape: bool = False,
        display_header_footer: bool = False,
        print_background: bool = True,
        scale: float = 1.0,
        as_base64: bool = False,
    ) -> str | None:
        if path is None and as_base64 is False:
            raise ValueError('Either path or as_base64 must be specified')

        pdf_data = (await self.execute_method(Page.PrintToPDF(
            landscape=landscape,
            display_header_footer=display_header_footer,
            print_background=print_background,
            scale=scale
        ))).data

        if as_base64:
            return pdf_data

        if path:
            async with aiofiles.open(path, 'wb') as f:
                await f.write(decode_base64_to_bytes(pdf_data))

        return None

    @asynccontextmanager
    async def expect_file_chooser(
        self, files: str | Path | list[str | Path]
    ) -> AsyncGenerator[None]:
        async def event_handler(event: Page.FileChooserOpened):
            await self.execute_method(DOM.SetFileInputFiles(files=files, backend_node_id=event.backendNodeId))

        await self.execute_method(Page.SetInterceptFileChooserDialog(enabled=True))

        await self.on(Page.FileChooserOpened, event_handler, temporary=True)

        yield

        await self.execute_method(Page.SetInterceptFileChooserDialog(enabled=False))
