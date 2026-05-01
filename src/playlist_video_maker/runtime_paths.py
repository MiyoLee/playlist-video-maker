from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            meipass_path = Path(meipass)
            if (meipass_path / "resources").exists():
                return meipass_path

        executable_dir = Path(sys.executable).resolve().parent
        if (executable_dir / "resources").exists():
            return executable_dir
        return executable_dir

    return Path(__file__).resolve().parents[2]


def resources_dir() -> Path:
    return app_root() / "resources"


def bundled_fonts_dir() -> Path:
    return resources_dir() / "fonts"
