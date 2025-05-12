from src.browser.chromium.base import Browser
from src.browser.constants import BrowserType
from src.browser.options import Options


class Chrome(Browser):
    def __init__(
        self,
        options: Options | None = None,
        remote_port: int | None = None,
    ):
        super().__init__(
            options=options,
            remote_port=remote_port,
            browser_type=BrowserType.CHROME
        )
