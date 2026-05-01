from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from playlist_video_maker.models import CAPTION_SOURCE_MANUAL, JobConfig, SubtitleStyle, TrackInfo
from playlist_video_maker.runtime_paths import bundled_fonts_dir
from playlist_video_maker.services.binaries import find_missing_binaries, resolve_binary_path


def get_audio_duration(file_path: Path) -> float:
    command = [
        resolve_binary_path("ffprobe") or "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(file_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        error_output = (result.stderr or "").strip()
        raise WorkflowError(f"길이 확인 실패: {error_output}")
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


BUNDLED_FONT_DIR = bundled_fonts_dir()
HORIZONTAL_MARGIN = 10
ERROR_LOG_DIR = Path.home() / "PlayList" / "playlist-video-maker-logs"


ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]


@dataclass(slots=True)
class WorkflowResult:
    success: bool
    message: str


class WorkflowError(RuntimeError):
    pass


class PlaylistVideoWorkflow:
    def __init__(self, job_config: JobConfig) -> None:
        self.job_config = job_config
        self.output_path = job_config.next_available_output_path()
        self.ffmpeg_binary = resolve_binary_path("ffmpeg") or "ffmpeg"
        self.ffprobe_binary = resolve_binary_path("ffprobe") or "ffprobe"

    def run(self, progress: ProgressCallback, log: LogCallback) -> WorkflowResult:
        self._validate(progress)

        with tempfile.TemporaryDirectory(prefix="playlist-video-maker-") as temp_dir:
            workspace = Path(temp_dir)
            normalized_dir = workspace / "normalized"
            subtitle_dir = workspace / "subtitles"
            output_dir = workspace / "output"
            normalized_dir.mkdir()
            subtitle_dir.mkdir()
            output_dir.mkdir()

            progress(20, "오디오 길이 확인 중")
            tracks = self._probe_tracks(log)

            progress(40, "오디오 정규화 중")
            normalized_files = self._normalize_tracks(tracks, normalized_dir, log)

            progress(60, "오디오 이어붙이는 중")
            combined_audio = output_dir / "combined.m4a"
            total_duration = self._concat_tracks(normalized_files, combined_audio, log)

            progress(75, "자막 준비 중")
            caption_images = self._render_caption_images(tracks, subtitle_dir, log)

            progress(90, "최종 영상 렌더링 중")
            self._render_video(combined_audio, tracks, caption_images, total_duration, log)

        progress(100, "완료")
        return WorkflowResult(
            success=True,
            message=f"영상 생성 완료: {self.output_path}",
        )

    def _validate(self, progress: ProgressCallback) -> None:
        progress(5, "실행 환경 확인 중")
        missing_binaries = find_missing_binaries()
        if missing_binaries:
            guidance = "PATH에서 ffmpeg/ffprobe를 찾을 수 없습니다."
            if os.name == "nt":
                guidance += " Windows에서는 ffmpeg/bin 폴더를 PATH에 추가하거나 FFMPEG_PATH, FFPROBE_PATH 환경 변수를 설정해 주세요."
            raise WorkflowError(
                "필수 실행 파일이 없습니다: " + ", ".join(missing_binaries) + "\n" + guidance
            )

        progress(10, "입력값 확인 중")
        if not self.job_config.tracks:
            raise WorkflowError("오디오 파일을 하나 이상 추가해 주세요.")
        if not self.job_config.background_image.exists():
            raise WorkflowError("배경 이미지 파일을 찾을 수 없습니다.")
        if not self.job_config.output_directory.exists():
            raise WorkflowError("출력 폴더를 찾을 수 없습니다.")
        for track in self.job_config.tracks:
            if not track.source_path.exists():
                raise WorkflowError(
                    f"오디오 파일을 찾을 수 없습니다: {track.source_path}"
                )

    def _probe_tracks(self, log: LogCallback) -> list[TrackInfo]:
        tracks: list[TrackInfo] = []
        for track in self.job_config.tracks:
            command = [
                self.ffprobe_binary,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(track.source_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                error_output = (result.stderr or "").strip()
                raise WorkflowError(
                    f"{track.source_path.name} 길이 확인 실패: {error_output}"
                )
            payload = json.loads(result.stdout)
            duration = float(payload["format"]["duration"])
            tracks.append(
                TrackInfo(
                    index=track.index,
                    source_path=track.source_path,
                    top_caption=track.top_caption,
                    title=track.title,
                    artist=track.artist,
                    duration_seconds=duration,
                )
            )
            log(f"길이 확인 완료: {track.source_path.name} ({duration:.2f}초)")
        return tracks

    def _normalize_tracks(
        self,
        tracks: list[TrackInfo],
        normalized_dir: Path,
        log: LogCallback,
    ) -> list[Path]:
        normalized_files: list[Path] = []
        total = max(len(tracks), 1)
        for position, track in enumerate(tracks, start=1):
            output_path = normalized_dir / f"{position:03d}.wav"
            command = [
                self.ffmpeg_binary,
                "-y",
                "-i",
                str(track.source_path),
                "-vn",
                "-ac",
                "2",
                "-ar",
                "44100",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ]
            self._run_command(command, log, f"오디오 정규화 완료 {position}/{total}")
            normalized_files.append(output_path)
        return normalized_files

    def _concat_tracks(
        self,
        normalized_files: list[Path],
        combined_audio: Path,
        log: LogCallback,
    ) -> float:
        concat_file = combined_audio.parent / "concat.txt"
        concat_lines = [f"file '{self._escape_concat_path(path)}'" for path in normalized_files]
        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
        command = [
            self.ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(combined_audio),
        ]
        self._run_command(command, log, "Concatenated audio")

        probe_command = [
            self.ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(combined_audio),
        ]
        result = subprocess.run(
            probe_command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error_output = (result.stderr or "").strip()
            raise WorkflowError(
                f"합쳐진 오디오 길이 확인 실패: {error_output}"
            )
        payload = json.loads(result.stdout)
        duration = float(payload["format"]["duration"])
        log(f"합쳐진 오디오 길이: {duration:.2f}초")
        return duration

    def _write_ass_subtitles(self, tracks: list[TrackInfo], subtitle_file: Path) -> None:
        top_style = self.job_config.top_subtitle_style
        bottom_style = self.job_config.bottom_subtitle_style
        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {self.job_config.resolution_width}",
            f"PlayResY: {self.job_config.resolution_height}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            (
                f"Style: TopCaption,{top_style.font_family},"
                f"{top_style.font_size},{self._ass_primary_colour(top_style.font_color)},&H000000FF,&H00101010,&H64000000,"
                "0,0,0,0,100,100,0,0,1,2,0,"
                f"{self._ass_alignment_value(top_style.alignment)},48,48,{top_style.vertical_margin},1"
            ),
            (
                f"Style: BottomCaption,{bottom_style.font_family},"
                f"{bottom_style.font_size},{self._ass_primary_colour(bottom_style.font_color)},&H000000FF,&H00101010,&H64000000,"
                "0,0,0,0,100,100,0,0,1,2,0,"
                f"{self._ass_alignment_value(bottom_style.alignment)},48,48,{bottom_style.vertical_margin},1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        current_start = 0.0
        for track in tracks:
            start = self._format_ass_time(current_start)
            current_start += track.duration_seconds
            end = self._format_ass_time(current_start)
            top_text = track.resolved_top_caption_text(self.job_config.top_caption_source)
            bottom_text = track.resolved_bottom_caption_text(self.job_config.bottom_caption_source)
            if top_text:
                lines.append(f"Dialogue: 0,{start},{end},TopCaption,,0,0,0,,{self._escape_ass_text(top_text)}")
            text = self._escape_ass_text(bottom_text)
            lines.append(f"Dialogue: 0,{start},{end},BottomCaption,,0,0,0,,{text}")

        subtitle_file.write_text("\n".join(lines), encoding="utf-8")

    def _render_video(
        self,
        combined_audio: Path,
        tracks: list[TrackInfo],
        caption_images: list[Path],
        total_duration: float,
        log: LogCallback,
    ) -> None:
        output_path = self.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        segment_dir = output_path.parent / f".{output_path.stem}-segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        segment_paths = self._render_video_segments(segment_dir, tracks, caption_images, log)
        combined_video = segment_dir / "combined-video.mp4"
        self._concat_video_segments(segment_paths, combined_video, log)
        self._mux_final_output(combined_video, combined_audio, output_path, total_duration, log)
        shutil.rmtree(segment_dir, ignore_errors=True)
        log(f"임시 세그먼트 정리 완료: {segment_dir.name}")
        log(f"렌더링 완료: {output_path.name}")

    def _render_video_segments(
        self,
        segment_dir: Path,
        tracks: list[TrackInfo],
        caption_images: list[Path],
        log: LogCallback,
    ) -> list[Path]:
        segment_paths: list[Path] = []
        for track, caption_image in zip(tracks, caption_images, strict=True):
            segment_path = segment_dir / f"segment-{track.index:03d}.mp4"
            command = [
                self.ffmpeg_binary,
                "-y",
                "-loop",
                "1",
                "-i",
                str(self.job_config.background_image),
                "-loop",
                "1",
                "-i",
                str(caption_image),
                "-filter_complex",
                self._segment_overlay_filter(),
                "-map",
                "[vout]",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-tune",
                "stillimage",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                "-t",
                f"{track.duration_seconds:.3f}",
                str(segment_path),
            ]
            self._run_command(command, log, f"세그먼트 렌더링 완료: {segment_path.name}")
            segment_paths.append(segment_path)
        return segment_paths

    def _concat_video_segments(
        self,
        segment_paths: list[Path],
        combined_video: Path,
        log: LogCallback,
    ) -> None:
        concat_file = combined_video.parent / "segments.txt"
        concat_lines = [f"file '{self._escape_concat_path(path)}'" for path in segment_paths]
        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
        command = [
            self.ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(combined_video),
        ]
        self._run_command(command, log, f"영상 세그먼트 병합 완료: {combined_video.name}")

    def _mux_final_output(
        self,
        combined_video: Path,
        combined_audio: Path,
        output_path: Path,
        total_duration: float,
        log: LogCallback,
    ) -> None:
        command = [
            self.ffmpeg_binary,
            "-y",
            "-i",
            str(combined_video),
            "-i",
            str(combined_audio),
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-shortest",
            "-t",
            f"{total_duration:.3f}",
            str(output_path),
        ]
        self._run_command(command, log, f"최종 출력 mux 완료: {output_path.name}")

    def _segment_overlay_filter(self) -> str:
        return (
            "[0:v]"
            f"scale={self.job_config.resolution_width}:{self.job_config.resolution_height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={self.job_config.resolution_width}:{self.job_config.resolution_height}:"
            "(ow-iw)/2:(oh-ih)/2,setsar=1[bg];"
            "[bg][1:v]overlay=0:0:eof_action=repeat:shortest=0:repeatlast=1,"
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,format=yuv420p[vout]"
        )

    def _render_caption_images(
        self,
        tracks: list[TrackInfo],
        subtitle_dir: Path,
        log: LogCallback,
    ) -> list[Path]:
        caption_images: list[Path] = []
        canvas_width = self.job_config.resolution_width
        canvas_height = self.job_config.resolution_height
        top_style = self.job_config.top_subtitle_style
        bottom_style = self.job_config.bottom_subtitle_style
        top_font = self._load_font(
            top_style.font_family,
            top_style.font_weight,
            top_style.font_size,
        )
        bottom_font = self._load_font(
            bottom_style.font_family,
            bottom_style.font_weight,
            bottom_style.font_size,
        )
        top_text_color = self._parse_hex_color(top_style.font_color)
        bottom_text_color = self._parse_hex_color(bottom_style.font_color)

        for track in tracks:
            image = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            top_line_spacing = max(4, top_style.font_size // 4)
            bottom_line_spacing = max(4, bottom_style.font_size // 4)
            top_text = track.resolved_top_caption_text(self.job_config.top_caption_source)
            bottom_text = track.resolved_bottom_caption_text(self.job_config.bottom_caption_source)
            if top_text:
                self._draw_caption_block(
                    draw,
                    top_text,
                    top_font,
                    top_text_color,
                    canvas_width,
                    canvas_height,
                    top_line_spacing,
                    top_style,
                    position="top",
                )
            self._draw_caption_block(
                draw,
                unicodedata.normalize("NFC", bottom_text),
                bottom_font,
                bottom_text_color,
                canvas_width,
                canvas_height,
                bottom_line_spacing,
                bottom_style,
                position="bottom",
            )
            caption_path = subtitle_dir / f"caption-{track.index:03d}.png"
            image.save(caption_path)
            caption_images.append(caption_path)
            log(f"자막 이미지 생성 완료: {caption_path.name}")

        return caption_images

    def _draw_caption_block(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        text_color: tuple[int, int, int, int],
        canvas_width: int,
        canvas_height: int,
        line_spacing: int,
        style: SubtitleStyle,
        position: str,
    ) -> None:
        wrapped_lines = self._wrap_text(draw, text, font, canvas_width - (HORIZONTAL_MARGIN * 2))
        line_height = self._line_height(draw, font)
        block_height = (line_height * len(wrapped_lines)) + (line_spacing * max(0, len(wrapped_lines) - 1))
        if position == "top":
            top_y = style.vertical_margin
        else:
            top_y = max(0, canvas_height - style.vertical_margin - block_height)

        for index, line in enumerate(wrapped_lines):
            line_width = self._text_width(draw, line, font)
            x_position = self._caption_x_position(line_width, style)
            y_position = top_y + index * (line_height + line_spacing)
            draw.text(
                (x_position, y_position),
                line,
                font=font,
                fill=text_color,
            )

    def _caption_x_position(self, text_width: int, style: SubtitleStyle) -> int:
        alignment = style.alignment
        if alignment in {"left", "왼쪽"}:
            return HORIZONTAL_MARGIN
        if alignment in {"right", "오른쪽"}:
            return max(HORIZONTAL_MARGIN, self.job_config.resolution_width - text_width - HORIZONTAL_MARGIN)
        return max(0, (self.job_config.resolution_width - text_width) // 2)

    def _ass_alignment_value(self, alignment: str) -> int:
        alignment_map = {
            "left": 1,
            "왼쪽": 1,
            "center": 2,
            "가운데": 2,
            "right": 3,
            "오른쪽": 3,
        }
        return alignment_map.get(alignment, 2)

    def _ass_primary_colour(self, font_color: str) -> str:
        red, green, blue, _ = self._parse_hex_color(font_color)
        return f"&H00{blue:02X}{green:02X}{red:02X}"

    def _load_font(
        self,
        font_family: str,
        font_weight: str,
        font_size: int,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        font_candidates = self._font_candidates(font_family, font_weight)
        for candidate in font_candidates:
            path = Path(candidate)
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), font_size)
                except OSError:
                    continue
        return ImageFont.load_default()

    def _font_candidates(self, font_family: str, font_weight: str) -> list[str]:
        noto_weight_map = {
            "Light": "NotoSansKR-Light.otf",
            "Regular": "NotoSansKR-Regular.otf",
            "DemiLight": "NotoSansKR-DemiLight.otf",
            "Black": "NotoSansKR-Black.otf",
        }
        source_han_weight_map = {
            "ExtraLight": "SourceHanSansKR-ExtraLight.otf",
            "Light": "SourceHanSansKR-Light.otf",
            "Regular": "SourceHanSansKR-Regular.otf",
            "Medium": "SourceHanSansKR-Medium.otf",
            "Bold": "SourceHanSansKR-Bold.otf",
        }
        font_map = {
            "Source Han Sans KR": [
                str(BUNDLED_FONT_DIR / source_han_weight_map.get(font_weight, "SourceHanSansKR-ExtraLight.otf")),
                str(BUNDLED_FONT_DIR / "SourceHanSansKR-ExtraLight.otf"),
                str(BUNDLED_FONT_DIR / "SourceHanSansKR-Light.otf"),
            ],
            "Noto Sans KR": [
                str(BUNDLED_FONT_DIR / noto_weight_map.get(font_weight, "NotoSansKR-Regular.otf")),
                str(BUNDLED_FONT_DIR / "NotoSansKR-Regular.otf"),
            ],
            "Malgun Gothic": [
                "C:/Windows/Fonts/malgun.ttf",
                "C:/Windows/Fonts/malgunbd.ttf",
            ],
            "Arial": [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
            ],
            "Arial Unicode MS": [
                "C:/Windows/Fonts/ARIALUNI.TTF",
                "C:/Windows/Fonts/arial.ttf",
            ],
        }
        fallback = [
            str(BUNDLED_FONT_DIR / source_han_weight_map.get(font_weight, "SourceHanSansKR-ExtraLight.otf")),
            str(BUNDLED_FONT_DIR / "SourceHanSansKR-ExtraLight.otf"),
            str(BUNDLED_FONT_DIR / noto_weight_map.get(font_weight, "NotoSansKR-Regular.otf")),
            str(BUNDLED_FONT_DIR / "NotoSansKR-Regular.otf"),
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/ARIALUNI.TTF",
        ]
        return font_map.get(font_family, []) + fallback

    def _wrap_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        wrapped_lines: list[str] = []
        for paragraph in text.splitlines() or [text]:
            current = ""
            for character in paragraph:
                candidate = f"{current}{character}"
                if current and self._text_width(draw, candidate, font) > max_width:
                    wrapped_lines.append(current)
                    current = character
                else:
                    current = candidate
            if current:
                wrapped_lines.append(current)
            elif not paragraph:
                wrapped_lines.append("")
        return wrapped_lines or [""]

    def _text_width(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> int:
        bbox = draw.textbbox((0, 0), text or " ", font=font)
        return bbox[2] - bbox[0]

    def _line_height(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> int:
        bbox = draw.textbbox((0, 0), "가", font=font)
        return max(1, bbox[3] - bbox[1])

    def _parse_hex_color(self, value: str | None) -> tuple[int, int, int, int]:
        cleaned = (value or "").strip().lstrip("#")
        if len(cleaned) != 6:
            return (255, 255, 255, 255)
        try:
            red = int(cleaned[0:2], 16)
            green = int(cleaned[2:4], 16)
            blue = int(cleaned[4:6], 16)
        except ValueError:
            return (255, 255, 255, 255)
        return (red, green, blue, 255)

    def _run_command(
        self,
        command: list[str],
        log: LogCallback,
        success_message: str,
    ) -> None:
        log("$ " + " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        stdout_output = (result.stdout or "").strip()
        if stdout_output:
            log(stdout_output)
        if result.returncode != 0:
            error_output = (result.stderr or "").strip()
            error_message = error_output or f"Command failed: {' '.join(command)}"
            error_log_path = self._write_error_log(command, result.stdout, result.stderr)
            log(error_message)
            log(f"상세 로그 저장 위치: {error_log_path}")
            raise WorkflowError(
                "ffmpeg 실행에 실패했습니다.\n"
                f"상세 로그 파일: {error_log_path}"
            )
        stderr_output = (result.stderr or "").strip()
        if stderr_output:
            log(stderr_output)
        log(success_message)

    def _write_error_log(self, command: list[str], stdout: str, stderr: str) -> Path:
        ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = ERROR_LOG_DIR / f"ffmpeg-error-{timestamp}.log"
        content = [
            "COMMAND:",
            " ".join(command),
            "",
            "STDOUT:",
            stdout or "",
            "",
            "STDERR:",
            stderr or "",
        ]
        log_path.write_text("\n".join(content), encoding="utf-8")
        return log_path

    def _format_ass_time(self, seconds: float) -> str:
        total_centiseconds = round(seconds * 100)
        centiseconds = total_centiseconds % 100
        total_seconds = total_centiseconds // 100
        seconds_part = total_seconds % 60
        total_minutes = total_seconds // 60
        minutes = total_minutes % 60
        hours = total_minutes // 60
        return f"{hours}:{minutes:02d}:{seconds_part:02d}.{centiseconds:02d}"

    def _escape_ass_text(self, text: str) -> str:
        return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")

    def _escape_concat_path(self, path: Path) -> str:
        return str(path).replace("'", r"'\\''")
