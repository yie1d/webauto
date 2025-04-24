from enum import Enum, auto


class BrowserState(int, Enum):
    INITIALIZED: int = auto()
    STARTED: int = auto()
    STOPPED: int = auto()
