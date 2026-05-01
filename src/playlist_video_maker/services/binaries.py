from __future__ import annotations

import os
import sys
from pathlib import Path
from shutil import which


REQUIRED_BINARIES = ("ffmpeg", "ffprobe")

WINDOWS_BINARY_DIRECTORIES = (
    Path.home() / "ffmpeg" / "bin",
    Path("C:/ffmpeg/bin"),
    Path("C:/Program Files/ffmpeg/bin"),
    Path("C:/Program Files (x86)/ffmpeg/bin"),
)


def binary_env_var(name: str) -> str:
    return f"{name.upper()}_PATH"


def binary_names(name: str) -> tuple[str, ...]:
    if sys.platform.startswith("win"):
        return (name, f"{name}.exe")
    return (name,)


def resolve_binary_path(name: str) -> str | None:
    for candidate in binary_names(name):
        resolved = which(candidate)
        if resolved is not None:
            return resolved

    env_value = os.environ.get(binary_env_var(name), "").strip()
    if env_value:
        env_path = Path(env_value)
        if env_path.exists() and env_path.is_file():
            return str(env_path)

    if not sys.platform.startswith("win"):
        return None

    for directory in WINDOWS_BINARY_DIRECTORIES:
        for candidate in binary_names(name):
            path = directory / candidate
            if path.exists() and path.is_file():
                return str(path)

    return None


def find_missing_binaries() -> list[str]:
    return [name for name in REQUIRED_BINARIES if resolve_binary_path(name) is None]
