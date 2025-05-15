from enum import IntEnum, StrEnum, auto


class ProcessState(IntEnum):
    """
    已初始化
    已启动
    已停止
    """
    INITIALIZED: int = auto()
    STARTED: int = auto()
    STOPPED: int = auto()


class BrowserState(IntEnum):
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
    CLOSED: int = auto()


class BrowserType(IntEnum):
    CHROME: int = auto()
    EDGE: int = auto()


class By(StrEnum):
    """
    定位器
    """

    ID = "id"
    XPATH = "xpath"
    NAME = "name"
    TAG_NAME = "tag name"
    CLASS_NAME = "class name"
    CSS_SELECTOR = "selector"
