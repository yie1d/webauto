import base64
from pathlib import Path
from typing import Literal


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
