from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from playlist_video_maker.main import main


ERROR_LOG_DIR = Path.home() / "PlayList" / "playlist-video-maker-logs"


def write_startup_error_log() -> Path:
    ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = ERROR_LOG_DIR / f"startup-error-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    log_path.write_text(traceback.format_exc(), encoding="utf-8")
    return log_path


def notify_startup_error(log_path: Path) -> None:
    message = (
        "Playlist Video Maker failed to start.\n\n"
        f"A startup log was saved to:\n{log_path}"
    )

    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "Playlist Video Maker", 0x10)
            return
        except Exception:
            pass

    print(message, file=sys.stderr)


def main_entry() -> int:
    try:
        return main()
    except Exception:
        log_path = write_startup_error_log()
        notify_startup_error(log_path)
        raise


if __name__ == "__main__":
    raise SystemExit(main_entry())
