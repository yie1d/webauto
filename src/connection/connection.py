import asyncio
import functools
import json
from collections.abc import AsyncIterable
from typing import Any

import aiohttp
import websockets

from src.cdp.base import CDPMethod
from src.logger import logger


def async_ensure_connection(func):
    @functools.wraps(func)
    async def wrapper(self: 'CDPSession', *args, **kwargs):
        await self._ensure_active_connection()
        return await func(self, *args, **kwargs)
    return wrapper


class CDPMessageManager:
    def __init__(self):
        self._pending_messages: dict[int, asyncio.Future] = {}
        self._id: int = 0

    def create_future(self) -> tuple[int, asyncio.Future]:
        self._id += 1
        future = asyncio.Future()
        self._pending_messages[self._id] = future
        return self._id, future

    def remove_pending(self, _id: int):
        if _id in self._pending_messages:
            del self._pending_messages[_id]

    def resolve_command(self, _id: int, response: str):
        if _id in self._pending_messages:
            self._pending_messages[_id].set_result(response)
            self.remove_pending(_id)
        else:
            logger.warning(f'No pending message can be resolve for id {_id}')


class CDPSession:
    def __init__(self, ws_address: str):
        self._ws_address = ws_address

        self._receive_task: asyncio.Task | None = None
        self._ws_connection: websockets.ClientConnection | None = None
        self._message_manager = CDPMessageManager()

    async def _ensure_active_connection(self) -> None:
        if self._ws_connection is None:
            await self.establish_new_connection()

    @property
    def ws_connection(self) -> websockets.ClientConnection:
        if self._ws_connection is None:
            raise Exception("Websocket connection was not established")
        return self._ws_connection

    async def establish_new_connection(self) -> None:
        self._ws_connection = await websockets.connect(
            self._ws_address,
            max_size=1024 * 1024 * 10  # 10MB
        )
        self._receive_task = asyncio.create_task(self._receive_events())

    @async_ensure_connection
    async def ping(self) -> bool:
        try:
            await self.ws_connection.ping()
            return True
        except Exception as e:
            logger.warning(f'Failed to ping: {e}')
            return False

    @async_ensure_connection
    async def execute_command(self, command_method: CDPMethod, timeout: int = 10):
        _id, future = self._message_manager.create_future()

        try:
            command = command_method.command
            command['id'] = _id
            await self.ws_connection.send(json.dumps(command))
            response: str = await asyncio.wait_for(future, timeout)
            return await command_method.parse_response(response)

        except TimeoutError as err:
            self._message_manager.remove_pending(_id)
            raise err
        except websockets.ConnectionClosed as err:
            await self._cleanup()
            raise err

    async def _cleanup(self) -> None:
        if self._ws_connection:
            await self._ws_connection.close()
        self._ws_connection = None

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()

        logger.info('Connection was closed, trying to cleaned up')

    async def _receive_events(self) -> None:
        try:
            async for raw_message in self._incoming_messages():
                logger.debug(f'Received message: {raw_message}')
                await self._process_single_message(raw_message)
        except websockets.ConnectionClosed as e:
            logger.info(f'Connection closed gracefully: {e}')
        except Exception as e:
            logger.error(f'Unexpected error in event loop: {e}')
            raise

    @staticmethod
    async def _parse_raw_message(raw_message: str) -> dict[str, Any] | None:
        try:
            return json.loads(raw_message)
        except json.JSONDecodeError as err:
            logger.warning(f'Failed to parse raw message: {raw_message[:200]}, {err}')
            return None

    @staticmethod
    async def _is_command_message(message: dict[str, Any]) -> bool:
        return isinstance(message.get('id'), int)

    async def _handle_command_message(self, message: dict[str, Any]) -> None:
        logger.debug(f'Processing command response: {message["id"]}')
        if message.get('result'):
            self._message_manager.resolve_command(message['id'], json.dumps(message['result']))
        else:
            logger.error(f'Failed to resolve command response: {message}')

    async def _handle_event_message(self, message: dict[str, Any]) -> None:
        # todo
        ...

    async def _process_single_message(self, raw_message: str) -> None:
        message = await self._parse_raw_message(raw_message)
        if message is None:
            return

        if await self._is_command_message(message):
            await self._handle_command_message(message)
        else:
            await self._handle_event_message(message)

    async def _incoming_messages(self) -> AsyncIterable[websockets.Data]:
        while True:
            yield await self.ws_connection.recv()


class CDPSessionManager:
    def __init__(
        self,
        connection_port: int
    ):
        self._connection_port = connection_port
        self._connection_dict = {}

    async def _parse_ws_address(self, page_id: str) -> str:
        if page_id == 'browser':
            return await self.get_browser_ws_address()
        else:
            return f'ws://localhost:{self._connection_port}/devtools/page/{page_id}'

    async def get_browser_ws_address(self) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{self._connection_port}/json/version') as resp:
                    data = await resp.json()
                    return data['webSocketDebuggerUrl']
        except aiohttp.ClientError as err:
            raise Exception(f'Failed to get websocket address: {err}')
        except KeyError as err:
            raise Exception(f'Failed to get websocket address: {err}')

    async def create_session(self, page_id: str = 'browser'):
        if page_id not in self._connection_dict:
            ws_address = await self._parse_ws_address(page_id)
            cdp_session = CDPSession(ws_address)
            self._connection_dict[page_id] = cdp_session
        else:
            cdp_session = self._connection_dict[page_id]

        return cdp_session
