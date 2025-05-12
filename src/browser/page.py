
from cdpkit.connection import CDPSessionManager
from cdpkit.protocol import Target
from cdpkit.protocol.base import RESULT_TYPE, CDPEvent, CDPMethod


class PageSession:
    def __init__(
        self,
        session_manager: CDPSessionManager,
        target_id: Target.TargetID
    ):
        self._target_id = target_id
        self._session = session_manager.get_session(target_id)

    def __str__(self):
        return f'PageSession(target_id={self._target_id})'

    def __repr__(self) -> str:
        return str(self)

    async def on(self, event: type[CDPEvent], callback: callable, temporary: bool = False) -> int:
        return await self._session.event_handler.register_callback(
            event.event_name, callback, temporary
        )

    async def execute_method(self, cdp_method: CDPMethod[RESULT_TYPE], timeout: int = 60) -> RESULT_TYPE:
        return await self._session.execute(
            cdp_method,
            timeout
        )
