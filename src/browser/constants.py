from enum import IntEnum, auto


class State(IntEnum):
    """
    已初始化
    已启动
    已停止
    """
    INITIALIZED: int = auto()
    STARTED: int = auto()
    STOPPED: int = auto()


class PageSessionState(IntEnum):
    DISABLED: int = auto()
    ENABLED: int = auto()


class BrowserType(IntEnum):
    CHROME: int = auto()
    EDGE: int = auto()
