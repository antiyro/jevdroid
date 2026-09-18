"""Opt-in metadata-only JSONL traces. No screenshots, UI text, or credentials."""

import json
import os
from pathlib import Path
from typing import Any, Self


class JsonlTrace:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._file = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self._file.close()

    def __call__(self, event: dict[str, Any]) -> None:
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()
