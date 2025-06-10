from enum import IntEnum, StrEnum, auto


class ProcessState(IntEnum):
    """
    已初始化
    已启动
    已停止
    """
    INITIALIZED = auto()
    STARTED = auto()
    STOPPED = auto()


class BrowserState(IntEnum):
    """
    已初始化
    已启动
    已停止
    """
    INITIALIZED = auto()
    STARTED = auto()
    STOPPED = auto()


class TabState(IntEnum):
    DISABLED = auto()
    ENABLED = auto()
    CLOSED = auto()


class BrowserType(IntEnum):
    CHROME = auto()
    EDGE = auto()


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
