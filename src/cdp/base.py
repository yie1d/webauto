from abc import ABC, abstractmethod


class CDPMethod(ABC):
    """
    基础命令类，所有命令都继承此类
    """
    METHOD = ''

    def __init__(self, *args, **kwargs):
        self._params = {}
        for k, v in kwargs.items():
            if k != 'self' and v is not None:
                self._params[k] = v
        print(self._params)

    @property
    def command(self):
        return {
            'method': self.METHOD,
            'params': self._params,
        }

    @abstractmethod
    async def parse_response(self, response: str):
        ...
