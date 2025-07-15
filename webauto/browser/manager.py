from typing import TypeVar

from pydantic import BaseModel

InstanceKey = TypeVar('InstanceKey')
InstanceObj = TypeVar('InstanceObj')


class InstanceManager[InstanceKey, InstanceObj](BaseModel):
    _instances: dict[InstanceKey, InstanceObj] = {}

    def __setitem__(self, key: InstanceKey, value: InstanceObj):
        self._instances[key] = value

    def __delitem__(self, key: InstanceKey):
        del self._instances[key]

    def __getitem__(self, key: InstanceKey) -> InstanceObj:
        return self._instances[key]
