from cdpkit.protocol import Runtime
from cdpkit.connection import CDPSessionExecutor


from src.logger import logger

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
                                query_property_result = await cls.parse_remote_object(session_executor, query_property.value)

                                if isinstance(query_property_result, Runtime.RemoteObjectId):
                                    res.append(query_property_result)
                                else:
                                    logger.warning(f'query_property: {query_property.model_dump()}')
                        return res
                    case 'null':
                        return None
                    case _:
                        raise Exception(f"It needs to be implemented {remote_object.model_dump()}")
            case 'number':
                return remote_object.value
            case 'function':
                raise Exception(f"It needs to be implemented {remote_object.model_dump()}")
            case _:
                raise Exception(f"It needs to be implemented {remote_object.model_dump()}")
