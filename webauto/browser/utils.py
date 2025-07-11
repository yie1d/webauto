import base64
from pathlib import Path
from typing import Literal

from cdpkit.connection import CDPSessionExecutor
from cdpkit.logger import logger
from cdpkit.protocol import Runtime


def decode_base64_to_bytes(image: str) -> bytes:
    return base64.b64decode(image.encode('utf-8'))


def get_path_ext(path: Path | str | None) -> str | None:
    if path is None:
        return None

    if isinstance(path, str):
        path = Path(path)
    elif isinstance(path, Path):
        pass
    else:
        raise TypeError(f'Invalid path type {type(path)}, only support str and Path type')

    return path.suffix.lower().removeprefix('.')


def get_img_format(path: Path | str | None) -> Literal['jpeg', 'png', 'webp'] | None:
    ext = get_path_ext(path)

    if ext in ['jpeg', 'png', 'webp']:
        return ext
    else:
        raise TypeError(f'Invalid image format: {ext}, only jpeg, png, webp are supported')


class RuntimeParser:
    @classmethod
    async def parse_remote_object(
        cls,
        session_executor: CDPSessionExecutor,
        remote_object: Runtime.RemoteObject
    ) -> Runtime.RemoteObjectId | list[Runtime.RemoteObjectId] | None:
        match remote_object.type:
            case 'object':
                match remote_object.subtype:
                    case 'node':
                        return remote_object.objectId
                    case 'array':
                        query_properties = (await session_executor.execute_method(Runtime.GetProperties(
                            object_id=remote_object.objectId
                        ))).result

                        res = []
                        for query_property in query_properties:
                            # 只取数字索引
                            if query_property.name.isdigit():
                                query_property_result = await cls.parse_remote_object(
                                    session_executor,
                                    query_property.value
                                )

                                if isinstance(query_property_result, Runtime.RemoteObjectId):
                                    res.append(query_property_result)
                                else:
                                    logger.warning(f'query_property: {query_property.model_dump()}')
                        return res
                    case 'null':
                        return None
                    case _:
                        raise Exception(f"It needs to be implemented {remote_object.model_dump()}")
            case 'string' | 'number':
                return remote_object.value
            case _:
                raise Exception(f"It needs to be implemented {remote_object.model_dump()}")
