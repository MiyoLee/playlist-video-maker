from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


CAPTION_SOURCE_FILENAME = "파일명 그대로"
CAPTION_SOURCE_MANUAL = "직접 입력"


def default_output_filename() -> str:
    return f"plaulist_video_{datetime.now().strftime('%Y%m%d')}.mp4"


@dataclass(slots=True)
class TrackInfo:
    index: int
    source_path: Path
    top_caption: str
    title: str
    artist: str
    duration_seconds: float = 0.0

    @property
    def bottom_caption_text(self) -> str:
        title = unicodedata.normalize("NFC", self.title.strip())
        artist = unicodedata.normalize("NFC", self.artist.strip())
        if artist:
            return unicodedata.normalize("NFC", f"{artist} - {title}")
        return title

    @property
    def caption_text(self) -> str:
        return self.bottom_caption_text or self.filename_caption_text

    @property
    def top_caption_text(self) -> str:
        return unicodedata.normalize("NFC", self.top_caption.strip())

    @property
    def filename_caption_text(self) -> str:
        return unicodedata.normalize("NFC", self.source_path.stem.strip())

    def resolved_top_caption_text(self, source: str) -> str:
        if source == CAPTION_SOURCE_FILENAME:
            return self.filename_caption_text
        return self.top_caption_text

    def resolved_bottom_caption_text(self, source: str) -> str:
        if source == CAPTION_SOURCE_FILENAME:
            return self.filename_caption_text
        return self.bottom_caption_text


@dataclass(slots=True)
class SubtitleStyle:
    font_family: str
    font_weight: str
    font_size: int
    font_color: str
    vertical_margin: int
    alignment: str


@dataclass(slots=True)
class JobConfig:
    tracks: list[TrackInfo]
    background_image: Path
    output_directory: Path
    output_filename: str
    resolution_width: int
    resolution_height: int
    top_caption_source: str
    bottom_caption_source: str
    top_subtitle_style: SubtitleStyle
    bottom_subtitle_style: SubtitleStyle

    def output_path(self) -> Path:
        filename = self.output_filename.strip() or default_output_filename()
        if not filename.lower().endswith(".mp4"):
            filename = f"{filename}.mp4"
        return self.output_directory / filename

    def next_available_output_path(self) -> Path:
        output_path = self.output_path()
        if not output_path.exists():
            return output_path

        stem = output_path.stem
        suffix = output_path.suffix
        counter = 1
        while True:
            candidate = output_path.with_name(f"{stem} ({counter}){suffix}")
            if not candidate.exists():
                return candidate
            counter += 1
