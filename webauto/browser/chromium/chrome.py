from webauto.browser.chromium.chromium import BrowserType


class Chrome(BrowserType):
    name: str = 'chrome'
    browser_path_dict: dict[str, list[str]] = {
        'Windows': [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        ],
        'Linux': [
            '/usr/bin/google-chrome',
        ],
        'Darwin': [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        ],
    }
