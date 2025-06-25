from typing import Any

from pydantic import BaseModel

from webauto.browser.options import Options


class BrowserInfo(BaseModel):
    options: Options
    remote_port: int

    def model_post_init(self, context: Any, /) -> None:
        self.options.check(self.remote_port)
