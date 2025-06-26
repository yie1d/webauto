from webauto.browser.chromium.chromium import BrowserType


class Edge(BrowserType):
    name: str = 'edge'
    browser_path_dict = {
        'Windows': [
            (
                r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
            ),
            (
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
            ),
        ],
        'Linux': [
            '/usr/bin/microsoft-edge',
        ],
        'Darwin': [
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        ],
    }
