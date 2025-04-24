# pylint: disable=invalid-name
import json
from typing import Any, Literal

from pydantic import BaseModel

from src.cdp import Browser, Page
from src.cdp.base import CDPMethod

"""
###################################################
                    Types
###################################################
"""
SessionID = str
TargetID = str
TargetFilter = list[dict[str, Any]]
WindowState = Literal['normal', 'minimized', 'maximized', 'fullscreen']


class TargetInfo(BaseModel):
    targetId: TargetID
    type: str
    title: str
    url: str
    attached: bool
    openerId: TargetID | None = None
    canAccessOpener: bool
    openerFrameId: Page.FrameId | None = None
    browserContextId: Browser.BrowserContextID | None = None
    subtype: str | None = None


class FilterEntry(BaseModel):
    exclude: bool | None = None
    type: str | None = None


class RemoteLocation(BaseModel):
    host: str
    port: int


"""
###################################################
                    Methods
###################################################
"""


class createTarget(CDPMethod):
    METHOD = 'Target.createTarget'

    def __init__(
        self,
        *,
        url: str,
        left: int | None = None,
        top: int | None = None,
        width: int | None = None,
        height: int | None = None,
        windowState: WindowState | None = None,
        browserContextId: Browser.BrowserContextID | None = None,
        enableBeginFrameControl: bool = False,
        newWindow: bool = False
    ):
        super().__init__(
            url=url,
            left=left,
            top=top,
            width=width,
            height=height,
            windowState=windowState,
            browserContextId=browserContextId,
            enableBeginFrameControl=enableBeginFrameControl,
            newWindow=newWindow
        )

    async def parse_response(self, response: str) -> TargetID:
        return json.loads(response)['targetId']


class getTargets(CDPMethod):
    METHOD = 'Target.getTargets'

    def __init__(self, *, _filter: TargetFilter | None = None):
        super().__init__(filter=_filter)

    async def parse_response(self, response: str) -> list[TargetInfo]:
        resp_json = json.loads(response)
        return [TargetInfo(**target_info) for target_info in resp_json.get('targetInfos', [])]
