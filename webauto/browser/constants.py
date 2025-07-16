from enum import StrEnum


class By(StrEnum):
    ID = "id"
    XPATH = "xpath"
    NAME = "name"
    TAG_NAME = "tag name"
    CLASS_NAME = "class name"
    CSS_SELECTOR = "selector"


class JsScripts:
    """
    A class containing JavaScript scripts used in web automation.
    """
    @classmethod
    def document_ready_state(cls) -> str:
        return """document.readyState"""

    @classmethod
    def text_content(cls) -> str:
        return """
        function() {
            return this.textContent;
        }"""

    @classmethod
    def get_bounding_client_rect(cls) -> str:
        return """
        function() {
            return JSON.stringify(this.getBoundingClientRect());
        }"""

    @classmethod
    def find_element_by_xpath(cls, xpath: str) -> str:
        return f"""
        function() {{
            return document.evaluate(
                "{xpath}", this, null,
                XPathResult.FIRST_ORDERED_NODE_TYPE, null
            ).singleNodeValue;
        }}"""

    @classmethod
    def find_elements_by_xpath(cls, xpath: str) -> str:
        return f"""
            function() {{
                var elements = document.evaluate(
                    "{xpath}", this, null,
                    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
                );
                var results = [];
                for (var inx = 0; inx < elements.snapshotLength; inx++) {{
                    results.push(elements.snapshotItem(inx));
                }}
                return results;
            }}"""
