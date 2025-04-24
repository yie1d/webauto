import platform
import stat
from abc import ABC, abstractmethod
from pathlib import Path

from src.logger import logger


class Options(ABC):
    def __init__(
        self,
        executable_path: str | Path = '',
        headless: bool = False,
        user_data_dir: str | Path = '',
        arguments: list[str] | None = None,
    ):
        self._executable_path = executable_path.as_posix() if isinstance(executable_path, Path) else executable_path
        self._headless = headless
        self._user_data_dir = user_data_dir.as_posix() if isinstance(user_data_dir, Path) else user_data_dir
        self._arguments = arguments if arguments is not None else []

    @property
    def executable_path(self) -> str:
        return self._executable_path

    @executable_path.setter
    def executable_path(self, value: str | Path) -> None:
        self._executable_path = value.as_posix() is isinstance(value, Path) and value

    @property
    def arguments(self) -> list[str]:
        return self._arguments

    @arguments.setter
    def arguments(self, value: list[str]) -> None:
        self._arguments = value

    @property
    def headless(self) -> bool:
        return self._headless

    @headless.setter
    def headless(self, value: bool) -> None:
        self._headless = value

    @property
    def user_data_dir(self) -> str:
        return self._user_data_dir

    @user_data_dir.setter
    def user_data_dir(self, value: str | Path) -> None:
        self._user_data_dir = value.as_posix() is isinstance(value, Path) and value

    def add_argument(self, argument: str) -> None:
        if argument not in self._arguments:
            self._arguments.append(argument)
        else:
            logger.warning(f'Argument {argument} already added.')

    def remove_argument(self, argument: str) -> None:
        if argument in self._arguments:
            self._arguments.remove(argument)

    @staticmethod
    def _validate_browser_paths(paths: list[str]) -> str:
        for path in paths:
            _path = Path(path)
            if _path.exists() and _path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                return path

    def add_default_arguments(self):
        self.add_argument('--no-first-run')
        self.add_argument('--no-default-browser-check')

    @abstractmethod
    def get_default_executable_path(self) -> str:  # pragma: no cover
        ...


class ChromeOptions(Options):
    def add_default_arguments(self):
        super().add_default_arguments()
        self.add_argument('--remote-allow-origins=*')

    def get_default_executable_path(self) -> str:
        os_name = platform.system()

        browser_paths = {
            'Windows': [
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            ],
            'Linux': [
                '/usr/bin/google-chrome',
            ],
            'Darwin': [
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            ],
        }

        browser_path = browser_paths.get(os_name)

        if not browser_path:
            raise ValueError('Unsupported OS')

        return self._validate_browser_paths(browser_path)
