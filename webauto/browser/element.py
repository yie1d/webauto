from __future__ import annotations

from typing import Literal

from pydantic import PrivateAttr

from cdpkit.connection import CDPSessionExecutor
from cdpkit.exception import NoSuchElement, ParamsMustSpecified
from cdpkit.protocol import DOM, Runtime
from webauto.browser.constants import By
from webauto.browser.utils import RuntimeParser


class ElementFinder(CDPSessionExecutor):
    backend_node_id: DOM.BackendNodeId | None = None

    _object_id: Runtime.RemoteObjectId | None = PrivateAttr(default=None)

    @property
    async def node(self):
        if self.backend_node_id is None:
            _node = (await self.execute_method(
                DOM.GetDocument(depth=0)
            )).root
            self.backend_node_id = _node.backendNodeId
        else:
            _node = (await self.execute_method(
                DOM.DescribeNode(backend_node_id=self.backend_node_id)
            ))
        return _node

    @property
    async def object_id(self) -> Runtime.RemoteObjectId:
        if self._object_id is None:
            self._object_id = (await self.execute_method(DOM.ResolveNode(
                backend_node_id=self.backend_node_id
            ))).object.objectId
        return self._object_id

    @property
    async def node_id(self) -> DOM.NodeId:
        return (await self.node).nodeId

    def update(self, backend_node_id: DOM.BackendNodeId | None):
        if backend_node_id:
            self.backend_node_id = backend_node_id
            self._object_id = None

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
                raise ParamsMustSpecified('node_id or node must be specified')
            elif node_id == 0:
                raise NoSuchElement
            node = (await self.execute_method(DOM.DescribeNode(node_id=node_id))).node

        return Element(
            session=self._session,
            session_manager=self._session_manager,
            backend_node_id=node.backendNodeId
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
    # todo
    ...
