# app/renderer.py
# Centralizes Jinja2 environment setup — imported by compose.py and ui.py.

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Undefined, BaseLoader
from pathlib import Path
from storage import channel_dir


def create_jinja_env(macros_dir: Path | None = None) -> Environment:
    """Return a strict Jinja2 environment pointing at the macros folder.

    When ``macros_dir`` is omitted, the currently active channel's macros/
    folder is used (via storage.channel_dir).
    """
    if macros_dir is None:
        macros_dir = channel_dir("macros")
    return Environment(
        loader=FileSystemLoader(str(macros_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def create_permissive_env() -> Environment:
    """Return a permissive Jinja2 environment for rendering SQL template rows.

    Uses ``Undefined`` so that any placeholder without a matching variable
    silently renders as an empty string — backward-compatible with .sql files
    that contain no Jinja2 placeholders at all.
    """
    return Environment(
        loader=BaseLoader(),
        undefined=Undefined,
        keep_trailing_newline=True,
    )
