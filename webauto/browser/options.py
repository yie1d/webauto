from pydantic import BaseModel, Field

from cdpkit.exception import ArgumentAlreadyExistsInOptions
from cdpkit.logger import logger


class Options(BaseModel):
    executable_path: str = ''
    headless: bool = False
    user_data_dir: str = ''
    arguments: list[str] = Field(default_factory=list)

    def add_argument(self, argument: str) -> None:
        if not isinstance(argument, str):
            raise TypeError(f'Invalid argument type {type(argument)}, only support str type')

        if argument not in self.arguments:
            self.arguments.append(argument)
        else:
            raise ArgumentAlreadyExistsInOptions(f'Argument already exists: {argument}')

    def remove_argument(self, argument: str) -> None:
        if not isinstance(argument, str):
            raise TypeError(f'Invalid argument type {type(argument)}, only support str type')

        if argument in self.arguments:
            self.arguments.remove(argument)

    def add_default_arguments(self) -> None:
        self.add_argument('--no-first-run')
        self.add_argument('--no-default-browser-check')
        self.add_argument('--enable-experimental-web-platform-features')

    def _delete_options_arguments(
        self,
        options_args_dict: dict[str, str]
    ) -> None:
        need_delete_args = ('--remote-debugging-port',)

        for need_delete_arg in need_delete_args:
            if need_delete_arg in options_args_dict:
                logger.warning(f'The custom *{need_delete_arg}* parameter will be overwritten by '
                               f'the set value')
                self.remove_argument(options_args_dict[need_delete_arg])

    def _set_headless(self, options_args_dict: dict[str, str]) -> None:
        if self.headless:
            headless_arg = '--headless'
            if headless_arg not in options_args_dict:
                self.add_argument(headless_arg)

    def _set_user_data_dir(self, options_args_dict: dict[str, str]) -> None:
        user_data_dir_arg = '--user-data-dir'

        if self.user_data_dir:
            if user_data_dir_arg in options_args_dict:
                self.remove_argument(options_args_dict[user_data_dir_arg])

            self.add_argument(f'{user_data_dir_arg}={self.user_data_dir}')
        else:
            if user_data_dir_arg not in options_args_dict:
                # todo set temp dir
                ...
                # temp_dir = TempDirectoryFactory().create_temp_dir('chromium_user_data_dir-')
                # self.add_argument(f'{user_data_dir_arg}={temp_dir.name}')

    def check(self, remote_port: int):
        options_args_dict = {arg.split('=')[0]: arg for inx, arg in enumerate(self.arguments)}
        self._delete_options_arguments(options_args_dict)

        self._set_headless(options_args_dict)

        self._set_user_data_dir(options_args_dict)

        self.add_default_arguments()

        self.add_argument(f'--remote-debugging-port={remote_port}')
