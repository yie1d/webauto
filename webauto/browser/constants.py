from enum import StrEnum


class By(StrEnum):
    ID = "id"
    XPATH = "xpath"
    NAME = "name"
    TAG_NAME = "tag name"
    CLASS_NAME = "class name"
    CSS_SELECTOR = "selector"
