import random
import subprocess
from typing import Any

from pydantic import BaseModel, PrivateAttr

from cdpkit.logger import logger
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
