from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Literal

import aiofiles
from pydantic import PrivateAttr

from cdpkit.connection import CDPSessionExecutor
from cdpkit.exception import ElementNotFileInput, NoSuchElement, ParamsMustSpecified
from cdpkit.protocol import DOM, Input, Page, Runtime
from webauto.browser.constants import By, JsScripts
from webauto.browser.utils import RuntimeParser, decode_base64_to_bytes, get_img_format


class ElementFinder(CDPSessionExecutor):
    backend_node_id: DOM.BackendNodeId | None = None

    _object_id: Runtime.RemoteObjectId | None = PrivateAttr(default=None)

    @property
    async def node(self):
        if self.backend_node_id is None:
            _node = (await self.execute_method(
                DOM.GetDocument(depth=0)
            )).root
        else:
            _node = (await self.execute_method(
                DOM.DescribeNode(backend_node_id=self.backend_node_id)
            )).node
        return _node

    @property
    async def object_id(self) -> Runtime.RemoteObjectId:
        if self._object_id is None and self.backend_node_id:
            self._object_id = (await self.execute_method(DOM.ResolveNode(
                backend_node_id=self.backend_node_id
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
                raise ParamsMustSpecified('node_id or node must be specified')
            elif node_id == 0:
                raise NoSuchElement
            node = (await self.execute_method(DOM.DescribeNode(node_id=node_id))).node

        return Element(
            session=self.session,
            session_manager=self.session_manager,
            backend_node_id=node.backendNodeId
        )

    async def find_element_by_selector(self, selector: str) -> Element:
        elements = await self._find_element_by_selector(selector)
        if not elements:
            raise NoSuchElement
        return elements[0]

    async def find_elements_by_selector(self, selector: str) -> list[Element]:
        return await self._find_element_by_selector(selector, mode='multiple')

    async def _find_element_by_selector(
        self,
        selector: str,
        mode: Literal['single', 'multiple'] = 'single'
    ) -> list[Element]:
        if mode == 'multiple':
            node_ids = (await self.execute_method(
                DOM.QuerySelectorAll(node_id=await self.node_id, selector=selector)
            )).nodeIds
        else:
            node_ids = [(await self.execute_method(
                DOM.QuerySelector(node_id=await self.node_id, selector=selector)
            )).nodeId]

        return [await self._make_element(node_id=node_id) for node_id in node_ids]

    async def find_element_by_xpath(self, xpath: str) -> Element:
        elements = await self._find_element_by_xpath(xpath)
        if not elements:
            raise NoSuchElement
        return elements[0]

    async def find_elements_by_xpath(self, xpath: str) -> list[Element]:
        return await self._find_element_by_xpath(xpath, mode='multiple')

    async def _find_element_by_xpath(
        self,
        xpath: str,
        mode: Literal['single', 'multiple'] = 'single'
    ) -> list[Element]:
        xpath = xpath.replace('"', '\\"')

        if mode == 'multiple':
            function_declaration = JsScripts.find_elements_by_xpath(xpath, is_document=self.backend_node_id is None)
        else:
            function_declaration = JsScripts.find_element_by_xpath(xpath, is_document=self.backend_node_id is None)

        object_ids = await self.execute_script(function_declaration)

        if object_ids is None:
            return []

        elements = []
        for object_id in object_ids:
            node = (await self.execute_method(DOM.DescribeNode(object_id=object_id))).node
            if node.nodeId == 0:
                await self.node
                node.nodeId = (await self.execute_method(DOM.PushNodesByBackendIdsToFrontend(
                    backend_node_ids=[node.backendNodeId]
                ))).nodeIds[0]
            elements.append(await self._make_element(node=node))
        return elements

    async def find_element(self, by: By, value: str) -> Element:
        value = await self._convert_find_by_value(by, value)

        if by == By.XPATH:
            return await self.find_element_by_xpath(value)
        else:
            return await self.find_element_by_selector(value)

    async def find_elements(self, by: By, value: str) -> list[Element]:
        value = await self._convert_find_by_value(by, value)

        if by == By.XPATH:
            return await self.find_elements_by_xpath(value)
        else:
            return await self.find_elements_by_selector(value)

    async def execute_script(self, script: str):
        script = script.strip(' \n')
        if 'this' in script:
            execute_resp = (await self.execute_method(
                Runtime.CallFunctionOn(
                    function_declaration=script,
                    object_id=await self.object_id
                )
            ))
        else:
            if re.search('^function.*};?$', script, re.DOTALL):
                script = f'({script})()'
            execute_resp = (await self.execute_method(
                Runtime.Evaluate(
                    expression=script
                )
            ))

        return await RuntimeParser.parse_remote_object(self, remote_object=execute_resp.result)


class Element(ElementFinder):
    @property
    async def parent(self) -> Element:
        parent_id = (await self.node).parentId
        if parent_id is None:
            raise NoSuchElement
        return await self._make_element(node_id=parent_id)

    @property
    async def value(self) -> str | None:
        return await self.get_attribute('value')

    @property
    async def tag(self) -> str:
        return (await self.node).nodeName.lower()

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
        return await self.execute_script(
            script=JsScripts.text_content()
        )

    @property
    async def bounds(self) -> dict[str, int | float]:
        return json.loads(await self.execute_script(
            script=JsScripts.get_bounding_client_rect()
        ))

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
            backend_node_id=self.backend_node_id,
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

        bounds = await self.bounds
        center = (
            bounds['x'] + bounds['width'] / 2,
            bounds['y'] + bounds['height'] / 2
        )

        await self.execute_method(Input.DispatchMouseEvent(
            type_='mousePressed',
            x=round(center[0], 2),
            y=round(center[1], 2),
            button=Input.MouseButton.LEFT,
            click_count=1
        ))

        await asyncio.sleep(.1)

        await self.execute_method(Input.DispatchMouseEvent(
            type_='mouseReleased',
            x=round(center[0], 2),
            y=round(center[1], 2),
            button=Input.MouseButton.LEFT,
            click_count=1
        ))

    async def input(self, value: str):
        await self.scroll_into_view()

        await self.execute_method(Input.InsertText(text=value))

    async def set_input_files(self, files: list[str]):
        if self.tag != 'input' or self.get_attribute('type') != 'file':
            raise ElementNotFileInput('Element is not a file input. '
                                      'Please use Tab.expect_file_chooser to handle file chooser')
        await self.execute_method(DOM.SetFileInputFiles(files=files, backend_node_id=self.backend_node_id))
