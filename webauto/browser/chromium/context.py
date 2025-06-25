import random
import subprocess
from typing import Annotated, Any

from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import core_schema

from cdpkit.logger import logger
from webauto.browser.options import Options


class BrowserInfo(BaseModel):
    options: Options = Options()
    remote_port: int = random.randint(9222, 9322)

    def model_post_init(self, context: Any, /) -> None:
        self.options.check(self.remote_port)


class _ProcessPopenAnnotation:
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.int_schema(),
            python_schema=core_schema.is_instance_schema(subprocess.Popen),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: {'pid': instance.pid}
            ),
        )


class BrowserProcess(BaseModel):
    browser_info: BrowserInfo
    process: Annotated[subprocess.Popen, _ProcessPopenAnnotation] | None = None

    def run(self):
        if self.process is None:
            self.process = subprocess.Popen(
                [
                    self.browser_info.options.executable_path,
                    *self.browser_info.options.arguments
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

    def stop(self):
        if self.process is not None:
            logger.info('Stopping process')
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                logger.info('process killed')
            self.process = None
