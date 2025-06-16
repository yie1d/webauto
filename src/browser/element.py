from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import aiofiles
from bs4 import BeautifulSoup

from cdpkit.connection import CDPSession, CDPSessionExecutor, CDPSessionManager
from cdpkit.exception import NoSuchElement
from cdpkit.protocol import DOM, Page, Runtime
from src.browser.constants import By
from src.browser.utils import RuntimeParser
from src.utils import decode_base64_to_bytes, get_img_format


class ElementFinder(CDPSessionExecutor):
    def __init__(
        self,
        session: CDPSession | None = None,
        session_manager: CDPSessionManager | None = None,
        backend_node_id: DOM.BackendNodeId | None = None,
        node: DOM.Node | None = None
    ):
        super().__init__(
            session=session,
            session_manager=session_manager
        )

        if backend_node_id is None and node is not None:
            backend_node_id = node.backendNodeId

        self._backend_node_id = backend_node_id
        self._object_id: Runtime.RemoteObjectId | None = None

    def reset(self, backend_node_id: DOM.BackendNodeId | None = None):
        self._object_id = None
        self._backend_node_id = backend_node_id

    @property
    async def node(self) -> DOM.Node:
        if self._backend_node_id is None:
            _node = (await self.execute_method(DOM.GetDocument(depth=0))).root
            self._backend_node_id = _node.backendNodeId
        else:
            _node = (await self.execute_method(DOM.DescribeNode(
                backend_node_id=await self.backend_node_id
            ))).node
        return _node

    @property
    async def backend_node_id(self) -> DOM.BackendNodeId:
        if self._backend_node_id is None:
            return (await self.node).backendNodeId
        return self._backend_node_id

    @property
    async def object_id(self) -> Runtime.RemoteObjectId:
        if self._object_id is None:
            self._object_id = (await self.execute_method(DOM.ResolveNode(
                backend_node_id=await self.backend_node_id
            ))).object.objectId
        return self._object_id

    @property
    async def node_id(self) -> DOM.NodeId:
        return (await self.node).nodeId

    @staticmethod
    async def _convert_find_by_value(by: By, value: str) -> str:
        match by:
            case By.ID:
                value = f'[id="{value}"]'
            case By.NAME:
                value = f'[name="{value}"]'
            case By.CLASS_NAME:
                value = f'.{value}'
            case _:
                ...
        return value

    async def _make_element(self, node_id: DOM.NodeId | None = None, node: DOM.Node | None = None) -> Element:
        if node is None:
            if node_id is None:
                raise ValueError('node_id or node must be specified')
            elif node_id == 0:
                raise NoSuchElement
            node = (await self.execute_method(DOM.DescribeNode(node_id=node_id))).node

        return Element(
            session=self._session,
            session_manager=self._session_manager,
            node=node
        )

    async def find_element_by_selector(
        self,
        selector: str,
        mode: Literal['single', 'multiple'] = 'single'
    ) -> list[Element]:
        backend_node_ids = [await self.backend_node_id]

        node_id = (await self.execute_method(
            DOM.PushNodesByBackendIdsToFrontend(backend_node_ids=backend_node_ids)
        )).nodeIds[0]

        if mode == 'multiple':
            node_ids = (await self.execute_method(DOM.QuerySelectorAll(node_id=node_id, selector=selector))).nodeIds
        else:
            node_ids = [(await self.execute_method(DOM.QuerySelector(node_id=node_id, selector=selector))).nodeId]

        return [await self._make_element(node_id=node_id) for node_id in node_ids]

    async def find_element_by_xpath(
        self,
        xpath: str,
        mode: Literal['single', 'multiple'] = 'single'
    ) -> list[Element]:
        if self.__class__.__name__ == 'Element':
            xpath = xpath.replace('"', '\\"')

            if mode == 'multiple':
                function_declaration = f"""
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
                    }}
                """
            else:
                function_declaration = f"""
                    function() {{
                        return document.evaluate(
                            "{xpath}", this, null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE, null
                        ).singleNodeValue;
                    }}
                """

            call_result = (await self.execute_method(Runtime.CallFunctionOn(
                function_declaration=function_declaration,
                object_id=await self.object_id,
                return_by_value=False
            ))).result

            object_ids: list[Runtime.RemoteObjectId] | None = await RuntimeParser.parse_remote_object(
                session_executor=self,
                remote_object=call_result
            )
            if object_ids is None:
                raise NoSuchElement

            elements = []
            for object_id in object_ids:
                node = (await self.execute_method(DOM.DescribeNode(object_id=object_id))).node
                if node.nodeId == 0:
                    node.nodeId = (await self.execute_method(DOM.PushNodesByBackendIdsToFrontend(
                        backend_node_ids=[node.backendNodeId]
                    ))).nodeIds[0]
                elements.append(await self._make_element(node=node))
            return elements
        else:
            perform_search = (await self.execute_method(
                DOM.PerformSearch(query=xpath, include_user_agent_shadow_dom=True)
            ))
            try:
                if perform_search.resultCount == 0:
                    if mode == 'multiple':
                        return []
                    else:
                        raise NoSuchElement
                if mode == 'multiple':
                    to_index = perform_search.resultCount
                else:
                    to_index = 1
                node_ids = (await self.execute_method(DOM.GetSearchResults(
                    search_id=perform_search.searchId,
                    from_index=0,
                    to_index=to_index
                ))).nodeIds
            finally:
                await self.execute_method(DOM.DiscardSearchResults(search_id=perform_search.searchId))

            return [await self._make_element(node_id=node_id) for node_id in node_ids]

    async def find_element(self, by: By, value: str) -> Element:
        value = await self._convert_find_by_value(by, value)

        if by == By.XPATH:
            return (await self.find_element_by_xpath(value, mode='single'))[0]
        else:
            return (await self.find_element_by_selector(value, mode='single'))[0]

    async def find_elements(self, by: By, value: str) -> list[Element]:
        value = await self._convert_find_by_value(by, value)

        if by == By.XPATH:
            return await self.find_element_by_xpath(value, mode='multiple')
        else:
            return await self.find_element_by_selector(value, mode='multiple')


class Element(ElementFinder):
    def __init__(
        self,
        session: CDPSession | None = None,
        session_manager: CDPSessionManager | None = None,
        backend_node_id: DOM.BackendNodeId | None = None,
        node: DOM.Node | None = None
    ):
        super().__init__(
            session=session,
            session_manager=session_manager,
            backend_node_id=backend_node_id,
            node=node
        )

    @property
    async def value(self) -> str | None:
        return await self.get_attribute('value')

    @property
    async def tag(self) -> str:
        return (await self.node).nodeName

    @property
    async def class_name(self) -> str | None:
        return await self.get_attribute('class')

    @property
    async def id(self) -> str | None:
        return await self.get_attribute('id')

    @property
    async def is_enabled(self) -> bool:
        disabled = await self.get_attribute('disabled')
        if disabled is None:
            return True
        return False

    @property
    async def text(self) -> str:
        soup = BeautifulSoup(await self.outer_html, 'html.parser')
        return soup.get_text(strip=True)

    @property
    async def bounds(self) -> dict[str, int | float]:
        # box_model = (await self.execute_method(DOM.GetBoxModel(
        #     object_id=await self.object_id
        # ))).model
        #
        # return {
        #     'x': box_model.content[0],
        #     'y': box_model.content[1],
        #     'height': box_model.height,
        #     'width': box_model.width
        # }

        result = (await self.execute_script(
            script="""
                function() {
                    return JSON.stringify(this.getBoundingClientRect());
                }"""
        )).result

        return json.loads(await RuntimeParser.parse_remote_object(self, result))

    @property
    async def outer_html(self) -> str:
        return (await self.execute_method(DOM.GetOuterHTML(
            object_id=await self.object_id
        ))).outerHTML

    @property
    async def attrs(self) -> dict[str, str]:
        return await self.get_attribute()

    async def get_attribute(self, name: str | None = None) -> dict[str, str] | str | None:
        attrs = {}

        _attrs = (await self.node).attributes
        for inx in range(0, len(_attrs), 2):
            if name == _attrs[inx]:
                return _attrs[inx + 1]
            else:
                attrs[_attrs[inx]] = _attrs[inx + 1]

        return None if name is None else attrs

    async def scroll_into_view(self):
        await self.execute_method(DOM.ScrollIntoViewIfNeeded(
            backend_node_id=await self.backend_node_id,
        ))

    async def take_screenshot(
        self,
        path: Path | str | None = None,
        quality: int = 100,
        as_base64: bool = False
    ) -> str | None:
        if path is None and as_base64 is False:
            raise ValueError('Either path or as_base64 must be specified')

        bounds = await self.bounds
        clip = Page.Viewport.model_validate({
            'x': bounds['x'],
            'y': bounds['y'],
            'width': bounds['width'],
            'height': bounds['height'],
            'scale': 1
        })

        img_base64 = (await self.execute_method(Page.CaptureScreenshot(
            format_=get_img_format(path),
            clip=clip,
            quality=quality,
        ))).data

        if as_base64:
            return img_base64

        if path:
            async with aiofiles.open(path, 'wb') as f:
                await f.write(decode_base64_to_bytes(img_base64))

        return None

    async def click(self):
        await self.scroll_into_view()
        ...

    async def input(self, value: str):
        await self.scroll_into_view()
        ...

    async def execute_script(self, script: str):
        return await self.execute_method(
            Runtime.CallFunctionOn(
                object_id=await self.object_id,
                function_declaration=script
            )
        )
