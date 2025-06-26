import random
import subprocess
from typing import Any

from pydantic import BaseModel, PrivateAttr

from cdpkit.connection import CDPSessionExecutor
from cdpkit.logger import logger
from cdpkit.protocol import Browser, Target
from webauto.browser.chromium.options import Options


class BrowserInfo(BaseModel):
    options: Options = Options()
    host: str = 'localhost'
    remote_port: int = random.randint(9222, 9322)

    def model_post_init(self, context: Any, /) -> None:
        self.options.check(self.remote_port)


class BrowserProcess(BaseModel):
    browser_info: BrowserInfo

    _process: subprocess.Popen | None = PrivateAttr()

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


class ContextManager(CDPSessionExecutor):
    browser_type: str

    contexts: list[Browser.BrowserContextID] = PrivateAttr(default_factory=list)

    async def init_manager(self) -> 'ContextManager':
        self.contexts = await self.get_browser_contexts()
        return self

    async def new_context(self) -> BrowserContext:
        browser_context_id = (await self.execute_method(Target.CreateBrowserContext())).browserContextId
        self.contexts.append(browser_context_id)

        return BrowserContext(
            context_id=browser_context_id,
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

    async def get_browser_contexts(self) -> list[Browser.BrowserContextID]:
        return (await self.execute_method(Target.GetBrowserContexts())).browserContextIds
