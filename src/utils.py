import base64
import shutil
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from src.logger import logger
from src.singleton import SingletonMeta


class TempDirectoryFactory(metaclass=SingletonMeta):
    INITIALIZED = False

    def __init__(self):
        if not self.INITIALIZED:
            self.INITIALIZED = True
            self._temp_dirs = []
            self._temp_dir_factory = TemporaryDirectory

    def create_temp_dir(self, prefix: str | None = None):
        temp_dir = self._temp_dir_factory(prefix=prefix, delete=False)
        self._temp_dirs.append(temp_dir)
        return temp_dir

    @staticmethod
    def _retry_process_file(func: callable, path: str, retry_times: int = 10):
        retry_time = 0
        while retry_times < 0 or retry_time < retry_times:
            retry_time += 1
            try:
                func(path)
                logger.info(f'Retry process file {path}, {retry_times}')
                break
            except PermissionError:
                time.sleep(0.1)
        else:
            raise PermissionError

    def _handle_cleanup_error(self, func: callable, path: str, exc_info: tuple):
        matches = ('CrashpadMetrics-active.pma', )
        exc_type, exc_value, _ = exc_info

        if exc_type is PermissionError:
            if Path(path).name in matches:
                try:
                    self._retry_process_file(func, path)
                    return
                except PermissionError:
                    raise exc_value
        elif exc_type in (OSError, FileNotFoundError):
            return
        raise exc_value

    def clean_up(self):
        for temp_dir in self._temp_dirs:
            shutil.rmtree(temp_dir.name, onerror=self._handle_cleanup_error)


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

    return path.suffix.lower()
