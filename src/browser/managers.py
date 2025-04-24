from src.browser.options import ChromeOptions, Options


class BrowserOptionsManager:
    @staticmethod
    def initialize_options(options: Options | None = None) -> Options:
        if options is None:
            return ChromeOptions()

        return options
