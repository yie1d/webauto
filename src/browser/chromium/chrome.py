from src.browser.chromium.chromium import Chromium
from src.browser.options import ChromeOptions, Options


class Chrome(Chromium):
    def __init__(
        self,
        options: Options | None = None,
        remote_port: int | None = None,
    ):
        if options is None:
            options = ChromeOptions()

        super().__init__(
            options=options,
            remote_port=remote_port
        )
