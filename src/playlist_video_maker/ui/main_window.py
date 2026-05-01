from __future__ import annotations

import unicodedata
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from playlist_video_maker.models import (
    CAPTION_SOURCE_FILENAME,
    CAPTION_SOURCE_MANUAL,
    JobConfig,
    SubtitleStyle,
    TrackInfo,
)
from playlist_video_maker.runtime_paths import bundled_fonts_dir
from playlist_video_maker.services.workflow import PlaylistVideoWorkflow, WorkflowError


DEFAULT_OUTPUT_DIRECTORY = Path.home() / "PlayList"
PREVIEW_WIDTH = 480
PREVIEW_HEIGHT = 270
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
DEFAULT_FONT_FAMILY = "Source Han Sans KR"
DEFAULT_FONT_COLOR = "#FFFFFF"
BUNDLED_FONT_DIR = bundled_fonts_dir()
HORIZONTAL_MARGIN = 10
SETTINGS_ORGANIZATION = "OhMyOpenCode"
SETTINGS_APPLICATION = "PlaylistVideoMaker"
LAST_AUDIO_DIRECTORY_KEY = "paths/last_audio_directory"
LAST_BACKGROUND_DIRECTORY_KEY = "paths/last_background_directory"


def default_output_filename() -> str:
    return f"plaulist_video_{datetime.now().strftime('%Y%m%d')}.mp4"


class WorkflowWorker(QObject):
    progress_changed = Signal(int, str)
    log_emitted = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, job_config: JobConfig) -> None:
        super().__init__()
        self._workflow = PlaylistVideoWorkflow(job_config)

    def run(self) -> None:
        try:
            result = self._workflow.run(self.progress_changed.emit, self.log_emitted.emit)
        except WorkflowError as exc:
            self.finished.emit(False, str(exc))
            return
        except Exception as exc:
            self.finished.emit(False, f"Unexpected error: {exc}")
            return

        self.finished.emit(result.success, result.message)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        self._bundled_font_families: dict[str, str] = {}
        self._register_bundled_fonts()
        self.setWindowTitle("Playlist Video Maker")
        self.resize(1280, 760)

        self._worker_thread: QThread | None = None
        self._worker: WorkflowWorker | None = None

        self.audio_table = QTableWidget(0, 1)
        self.audio_table.setHorizontalHeaderLabels(["오디오 파일"])
        self.audio_table.horizontalHeader().setStretchLastSection(True)

        self.background_image_input = QLineEdit()
        self.background_image_input.setReadOnly(True)
        self.background_image_button = QPushButton("이미지 선택")
        self.background_image_button.clicked.connect(self.choose_background_image)

        self.add_audio_button = QPushButton("오디오 파일 추가")
        self.add_audio_button.clicked.connect(self.choose_audio_files)
        self.remove_audio_button = QPushButton("선택 항목 제거")
        self.remove_audio_button.clicked.connect(self.remove_selected_audio_rows)

        default_output_directory = DEFAULT_OUTPUT_DIRECTORY
        if not default_output_directory.exists():
            default_output_directory = Path.home()
        self.output_directory_input = QLineEdit(str(default_output_directory))
        self.output_directory_input.setReadOnly(True)
        self.output_directory_button = QPushButton("폴더 선택")
        self.output_directory_button.clicked.connect(self.choose_output_directory)

        self.output_filename_input = QLineEdit(default_output_filename())
        self.output_filename_input.setPlaceholderText(default_output_filename())

        self.top_subtitle_font_size_input = self._create_subtitle_font_size_input()
        self.top_subtitle_font_family_input = self._create_subtitle_font_family_input()
        self.top_subtitle_font_weight_input = self._create_subtitle_font_weight_input()
        self.top_subtitle_alignment_input = self._create_subtitle_alignment_input()
        self.bottom_subtitle_font_size_input = self._create_subtitle_font_size_input()
        self.bottom_subtitle_font_family_input = self._create_subtitle_font_family_input()
        self.bottom_subtitle_font_weight_input = self._create_subtitle_font_weight_input()
        self.bottom_subtitle_alignment_input = self._create_subtitle_alignment_input()
        self.top_subtitle_margin_input = QSpinBox()
        self.top_subtitle_margin_input.setRange(0, 600)
        self.top_subtitle_margin_input.setValue(60)
        self.bottom_subtitle_margin_input = QSpinBox()
        self.bottom_subtitle_margin_input.setRange(0, 600)
        self.bottom_subtitle_margin_input.setValue(60)
        self.top_caption_input = QLineEdit()
        self.top_caption_input.setPlaceholderText("상단 자막을 입력하세요")
        self.top_caption_filename_radio = QRadioButton("음원명 표출")
        self.bottom_caption_input = QLineEdit()
        self.bottom_caption_input.setPlaceholderText("하단 자막을 입력하세요")
        self.bottom_caption_filename_radio = QRadioButton("음원명 표출")
        self.top_subtitle_color_value = DEFAULT_FONT_COLOR
        self.top_subtitle_color_button = QPushButton("색상 선택")
        self.top_subtitle_color_button.clicked.connect(
            lambda _checked=False: self.choose_subtitle_color("top")
        )
        self.top_subtitle_color_preview = self._create_subtitle_color_preview(self.top_subtitle_color_value)
        self.update_subtitle_color_preview("top")
        self.bottom_subtitle_color_value = DEFAULT_FONT_COLOR
        self.bottom_subtitle_color_button = QPushButton("색상 선택")
        self.bottom_subtitle_color_button.clicked.connect(
            lambda _checked=False: self.choose_subtitle_color("bottom")
        )
        self.bottom_subtitle_color_preview = self._create_subtitle_color_preview(self.bottom_subtitle_color_value)
        self.update_subtitle_color_preview("bottom")

        self.preview_label = QLabel()
        self.preview_label.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("border: 1px solid #666; background: #111;")

        self.timeline_button = QPushButton("타임라인 텍스트 만들기")
        self.timeline_button.clicked.connect(self.generate_timeline_text)
        self.timeline_output = QPlainTextEdit()
        self.timeline_output.setReadOnly(True)
        self.timeline_output.setPlaceholderText("타임라인 텍스트가 여기에 표시됩니다.")
        self.timeline_output.setMinimumHeight(100)
        self.timeline_copy_button = QPushButton("복사")
        self.timeline_copy_button.clicked.connect(self.copy_timeline_text)

        self.start_button = QPushButton("시작")
        self.start_button.clicked.connect(self.start_workflow)

        self.progress_label = QLabel("대기 중")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)

        self._setup_layout()
        self._connect_preview_signals()
        self.update_caption_input_state()
        self.refresh_preview()

    def _setup_layout(self) -> None:
        central_widget = QWidget()
        root_layout = QHBoxLayout(central_widget)
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.addRow("트랙 목록", self._build_audio_section())
        form_layout.addRow(
            "배경 이미지",
            self._build_inline_row(self.background_image_input, self.background_image_button),
        )
        form_layout.addRow(
            "출력 폴더",
            self._build_inline_row(self.output_directory_input, self.output_directory_button),
        )
        form_layout.addRow("출력 파일명", self.output_filename_input)
        form_layout.addRow("상단 자막 설정", self._build_subtitle_section(
            "상단 자막",
            self.top_caption_input,
            self.top_caption_filename_radio,
            self.top_subtitle_font_family_input,
            self.top_subtitle_font_weight_input,
            self.top_subtitle_font_size_input,
            self.top_subtitle_alignment_input,
            self.top_subtitle_margin_input,
            self.top_subtitle_color_preview,
            self.top_subtitle_color_button,
        ))
        form_layout.addRow("하단 자막 설정", self._build_subtitle_section(
            "하단 자막",
            self.bottom_caption_input,
            self.bottom_caption_filename_radio,
            self.bottom_subtitle_font_family_input,
            self.bottom_subtitle_font_weight_input,
            self.bottom_subtitle_font_size_input,
            self.bottom_subtitle_alignment_input,
            self.bottom_subtitle_margin_input,
            self.bottom_subtitle_color_preview,
            self.bottom_subtitle_color_button,
        ))

        left_layout.addLayout(form_layout)
        left_layout.addWidget(self.start_button)
        left_layout.addWidget(self.progress_label)
        left_layout.addWidget(self.progress_bar)
        left_layout.addWidget(QLabel("로그"))
        left_layout.addWidget(self.log_output)

        right_layout.addWidget(QLabel("미리보기"))
        right_layout.addWidget(self.preview_label)
        right_layout.addWidget(QLabel("타임라인 텍스트"))
        timeline_button_row = QHBoxLayout()
        timeline_button_row.addWidget(self.timeline_button)
        timeline_button_row.addWidget(self.timeline_copy_button)
        timeline_button_row.addStretch(1)
        right_layout.addLayout(timeline_button_row)
        right_layout.addWidget(self.timeline_output)
        right_layout.addStretch(1)

        root_layout.addLayout(left_layout, 3)
        root_layout.addLayout(right_layout, 2)
        self.setCentralWidget(central_widget)

    def _connect_preview_signals(self) -> None:
        self.audio_table.itemSelectionChanged.connect(self.refresh_preview)
        self.audio_table.itemChanged.connect(self.refresh_preview)
        self.audio_table.model().rowsMoved.connect(self.refresh_preview)
        self.top_subtitle_font_family_input.currentIndexChanged.connect(self.refresh_preview)
        self.top_subtitle_font_weight_input.currentIndexChanged.connect(self.refresh_preview)
        self.top_subtitle_font_size_input.valueChanged.connect(self.refresh_preview)
        self.top_subtitle_font_size_input.editingFinished.connect(self.refresh_preview)
        self.top_subtitle_alignment_input.currentIndexChanged.connect(self.refresh_preview)
        self.bottom_subtitle_font_family_input.currentIndexChanged.connect(self.refresh_preview)
        self.bottom_subtitle_font_weight_input.currentIndexChanged.connect(self.refresh_preview)
        self.bottom_subtitle_font_size_input.valueChanged.connect(self.refresh_preview)
        self.bottom_subtitle_font_size_input.editingFinished.connect(self.refresh_preview)
        self.bottom_subtitle_alignment_input.currentIndexChanged.connect(self.refresh_preview)
        self.top_subtitle_margin_input.valueChanged.connect(self.refresh_preview)
        self.top_subtitle_margin_input.editingFinished.connect(self.refresh_preview)
        self.bottom_subtitle_margin_input.valueChanged.connect(self.refresh_preview)
        self.bottom_subtitle_margin_input.editingFinished.connect(self.refresh_preview)
        self.top_caption_input.textChanged.connect(self.refresh_preview)
        self.bottom_caption_input.textChanged.connect(self.refresh_preview)
        self.top_caption_filename_radio.toggled.connect(self.update_caption_input_state)
        self.bottom_caption_filename_radio.toggled.connect(self.update_caption_input_state)

    def _register_bundled_fonts(self) -> None:
        for font_name in [
            "SourceHanSansKR-ExtraLight.otf",
            "SourceHanSansKR-Light.otf",
            "SourceHanSansKR-Regular.otf",
            "SourceHanSansKR-Medium.otf",
            "SourceHanSansKR-Bold.otf",
            "NotoSansKR-Light.otf",
            "NotoSansKR-Regular.otf",
            "NotoSansKR-DemiLight.otf",
            "NotoSansKR-Black.otf",
        ]:
            font_path = BUNDLED_FONT_DIR / font_name
            if font_path.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    self._bundled_font_families[font_name] = families[0]

    def _build_inline_row(self, line_edit: QLineEdit, button: QPushButton) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return container

    def _build_inline_row(self, widget: QWidget, button: QPushButton) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        layout.addWidget(button)
        return container

    def _build_caption_input_row(self, line_edit: QLineEdit, radio_button: QRadioButton) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(radio_button)
        return container

    def _create_subtitle_color_preview(self, color_value: str) -> QLabel:
        preview = QLabel(color_value)
        preview.setMinimumWidth(90)
        return preview

    def _build_subtitle_color_row(self, color_preview: QLabel, color_button: QPushButton) -> QWidget:
        return self._build_inline_row(color_preview, color_button)

    def _build_subtitle_section(
        self,
        title: str,
        line_edit: QLineEdit,
        radio_button: QRadioButton,
        font_family_input: QComboBox,
        font_weight_input: QComboBox,
        font_size_input: QSpinBox,
        alignment_input: QComboBox,
        margin_input: QSpinBox,
        color_preview: QLabel,
        color_button: QPushButton,
    ) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.addRow("표시 내용", self._build_caption_input_row(line_edit, radio_button))
        form_layout.addRow("폰트", font_family_input)
        form_layout.addRow("웨이트", font_weight_input)
        form_layout.addRow("크기", font_size_input)
        form_layout.addRow("색상", self._build_subtitle_color_row(color_preview, color_button))
        form_layout.addRow("정렬", alignment_input)
        margin_label = "상단 여백" if title == "상단 자막" else "하단 여백"
        form_layout.addRow(margin_label, margin_input)
        layout.addLayout(form_layout)
        return container

    def _create_subtitle_font_size_input(self) -> QSpinBox:
        input_widget = QSpinBox()
        input_widget.setRange(5, 120)
        input_widget.setValue(40)
        return input_widget

    def _create_subtitle_font_family_input(self) -> QComboBox:
        input_widget = QComboBox()
        input_widget.addItems([
            "Source Han Sans KR",
            "Noto Sans KR",
        ])
        input_widget.setCurrentText(DEFAULT_FONT_FAMILY)
        return input_widget

    def _create_subtitle_font_weight_input(self) -> QComboBox:
        input_widget = QComboBox()
        input_widget.addItems([
            "ExtraLight",
            "Light",
            "Regular",
            "Medium",
            "Bold",
        ])
        input_widget.setCurrentText("ExtraLight")
        return input_widget

    def _create_subtitle_alignment_input(self) -> QComboBox:
        input_widget = QComboBox()
        input_widget.addItems(["가운데", "왼쪽", "오른쪽"])
        return input_widget

    def _build_audio_section(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        button_row = QHBoxLayout()
        button_row.addWidget(self.add_audio_button)
        button_row.addWidget(self.remove_audio_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        layout.addWidget(self.audio_table)
        return container

    def choose_audio_files(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "오디오 파일 선택",
            self.last_directory(LAST_AUDIO_DIRECTORY_KEY),
            "Audio Files (*.mp3 *.m4a *.wav *.flac *.aac *.ogg *.opus)",
        )
        if file_paths:
            self.remember_directory(LAST_AUDIO_DIRECTORY_KEY, Path(file_paths[0]).parent)
        for file_path in file_paths:
            self.add_audio_row(Path(file_path))
        self.refresh_preview()

    def add_audio_row(self, path: Path) -> None:
        row = self.audio_table.rowCount()
        self.audio_table.insertRow(row)
        item = QTableWidgetItem(path.name)
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        self.audio_table.setItem(row, 0, item)

    def audio_source_path(self, row: int) -> Path | None:
        item = self.audio_table.item(row, 0)
        if item is None:
            return None

        stored_path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(stored_path, str) and stored_path.strip():
            return Path(stored_path.strip())

        visible_text = item.text().strip()
        if visible_text and (visible_text.startswith("/") or ":" in visible_text):
            return Path(visible_text)
        return None

    def parse_track_name(self, path: Path) -> str:
        return self.normalize_text(path.stem.strip())

    def remove_selected_audio_rows(self) -> None:
        rows = sorted(
            {item.row() for item in self.audio_table.selectedItems()},
            reverse=True,
        )
        for row in rows:
            self.audio_table.removeRow(row)
        self.refresh_preview()

    def choose_background_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "배경 이미지 선택",
            self.last_directory(LAST_BACKGROUND_DIRECTORY_KEY),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if file_path:
            self.remember_directory(LAST_BACKGROUND_DIRECTORY_KEY, Path(file_path).parent)
            self.background_image_input.setText(file_path)
            self.refresh_preview()

    def update_caption_input_state(self, _checked: bool | None = None) -> None:
        self.top_caption_input.setEnabled(not self.top_caption_filename_radio.isChecked())
        self.bottom_caption_input.setEnabled(not self.bottom_caption_filename_radio.isChecked())
        self.refresh_preview()

    def last_directory(self, key: str) -> str:
        stored_value = self._settings.value(key, "")
        directory = Path(stored_value) if isinstance(stored_value, str) and stored_value else Path.home()
        return str(directory if directory.exists() and directory.is_dir() else Path.home())

    def remember_directory(self, key: str, directory: Path) -> None:
        if directory.exists() and directory.is_dir():
            self._settings.setValue(key, str(directory))

    def choose_output_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "출력 폴더 선택",
            self.output_directory_input.text() or str(Path.home()),
        )
        if directory:
            self.output_directory_input.setText(directory)

    def subtitle_color_value(self, position: str) -> str:
        return self.top_subtitle_color_value if position == "top" else self.bottom_subtitle_color_value

    def subtitle_color_widgets(self, position: str) -> tuple[QLabel, QPushButton]:
        if position == "top":
            return self.top_subtitle_color_preview, self.top_subtitle_color_button
        return self.bottom_subtitle_color_preview, self.bottom_subtitle_color_button

    def choose_subtitle_color(self, position: str) -> None:
        color = QColorDialog.getColor(QColor(self.subtitle_color_value(position)), self, "자막 색상 선택")
        if not color.isValid():
            return
        color_value = color.name().upper()
        if position == "top":
            self.top_subtitle_color_value = color_value
        else:
            self.bottom_subtitle_color_value = color_value
        self.update_subtitle_color_preview(position)
        self.refresh_preview()

    def update_subtitle_color_preview(self, position: str) -> None:
        color_value = self.subtitle_color_value(position)
        color_preview, _ = self.subtitle_color_widgets(position)
        text_color = "#000000" if color_value.upper() == "#FFFFFF" else "#FFFFFF"
        color_preview.setText(color_value)
        color_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color_preview.setStyleSheet(
            f"background-color: {color_value}; color: {text_color}; border: 1px solid #666; padding: 4px;"
        )

    def refresh_preview(self) -> None:
        width = max(self.preview_label.width(), PREVIEW_WIDTH)
        height = max(self.preview_label.height(), PREVIEW_HEIGHT)
        canvas = QPixmap(width, height)
        canvas.fill(QColor("#111111"))

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.paint_preview_background(painter, width, height)
        self.paint_preview_caption(painter, width, height)
        painter.end()

        self.preview_label.setPixmap(canvas)

    def paint_preview_background(self, painter: QPainter, width: int, height: int) -> None:
        image_path = self.background_image_input.text().strip()
        if not image_path:
            painter.setPen(QColor("#bbbbbb"))
            painter.drawText(
                0,
                0,
                width,
                height,
                int(Qt.AlignmentFlag.AlignCenter),
                "배경 이미지를 선택하면 미리보기가 표시됩니다.",
            )
            return

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            painter.setPen(QColor("#ff8080"))
            painter.drawText(
                0,
                0,
                width,
                height,
                int(Qt.AlignmentFlag.AlignCenter),
                "이미지를 불러올 수 없습니다.",
            )
            return

        scaled = pixmap.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (width - scaled.width()) // 2
        y = (height - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    def paint_preview_caption(self, painter: QPainter, width: int, height: int) -> None:
        top_text, bottom_text = self.preview_caption_texts()
        preview_scale = min(width / OUTPUT_WIDTH, height / OUTPUT_HEIGHT)

        if top_text:
            top_style = self.preview_subtitle_style("top", preview_scale)
            top_font = QFont(
                self.preview_font_family_name(top_style.font_family, top_style.font_weight),
                top_style.font_size,
            )
            top_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            top_font.setWeight(self.preview_font_weight(top_style.font_weight))
            painter.setFont(top_font)
            top_metrics = painter.fontMetrics()
            painter.setPen(QColor(top_style.font_color))
            self.draw_preview_caption_block(
                painter,
                top_metrics,
                top_text,
                width,
                height,
                top_style,
                position="top",
            )
        if bottom_text:
            bottom_style = self.preview_subtitle_style("bottom", preview_scale)
            bottom_font = QFont(
                self.preview_font_family_name(bottom_style.font_family, bottom_style.font_weight),
                bottom_style.font_size,
            )
            bottom_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            bottom_font.setWeight(self.preview_font_weight(bottom_style.font_weight))
            painter.setFont(bottom_font)
            bottom_metrics = painter.fontMetrics()
            painter.setPen(QColor(bottom_style.font_color))
            self.draw_preview_caption_block(
                painter,
                bottom_metrics,
                bottom_text,
                width,
                height,
                bottom_style,
                position="bottom",
            )

    def draw_preview_caption_block(
        self,
        painter: QPainter,
        metrics,
        text: str,
        width: int,
        height: int,
        style: SubtitleStyle,
        position: str,
    ) -> None:
        wrapped_lines = self.wrap_preview_text(metrics, text, width - (HORIZONTAL_MARGIN * 2))
        line_height = max(1, metrics.height())
        line_spacing = max(1, round(style.font_size / 4))
        block_height = (line_height * len(wrapped_lines)) + (line_spacing * max(0, len(wrapped_lines) - 1))
        if position == "top":
            top_y = style.vertical_margin
        else:
            top_y = max(line_height, height - style.vertical_margin - block_height)

        for index, line in enumerate(wrapped_lines):
            text_width = metrics.horizontalAdvance(line)
            x = self.preview_caption_x(style.alignment, text_width, width)
            y = top_y + ((index + 1) * line_height) + (index * line_spacing)
            painter.drawText(x, y, line)

    def preview_caption_texts(self) -> tuple[str, str]:
        row = self.selected_preview_row()
        if row is None:
            top_text = self.normalize_text(self.top_caption_input.text().strip() or "상단 자막")
            bottom_text = self.normalize_text(self.bottom_caption_input.text().strip() or "곡 제목")
            if self.top_caption_filename_radio.isChecked():
                top_text = "곡 제목"
            if self.bottom_caption_filename_radio.isChecked():
                bottom_text = "곡 제목"
            return (top_text, bottom_text)

        source_path = self.audio_source_path(row) or Path()
        track = TrackInfo(
            index=row,
            source_path=source_path,
            top_caption=self.normalize_text(self.top_caption_input.text().strip()),
            title=self.normalize_text(self.bottom_caption_input.text().strip()),
            artist="",
        )
        top_text = track.resolved_top_caption_text(self.top_caption_source())
        bottom_text = track.resolved_bottom_caption_text(self.bottom_caption_source())
        return (self.normalize_text(top_text), self.normalize_text(bottom_text))

    def top_caption_source(self) -> str:
        return CAPTION_SOURCE_FILENAME if self.top_caption_filename_radio.isChecked() else CAPTION_SOURCE_MANUAL

    def bottom_caption_source(self) -> str:
        return CAPTION_SOURCE_FILENAME if self.bottom_caption_filename_radio.isChecked() else CAPTION_SOURCE_MANUAL

    def selected_preview_row(self) -> int | None:
        selection_model = self.audio_table.selectionModel()
        if selection_model is not None:
            selected_rows = selection_model.selectedRows()
            if selected_rows:
                return selected_rows[0].row()
        if self.audio_table.rowCount() > 0:
            return 0
        return None

    def preview_caption_x(self, alignment: str, text_width: int, width: int) -> int:
        if alignment == "왼쪽":
            return HORIZONTAL_MARGIN
        if alignment == "오른쪽":
            return max(HORIZONTAL_MARGIN, width - text_width - HORIZONTAL_MARGIN)
        return max(0, (width - text_width) // 2)

    def normalize_text(self, value: str) -> str:
        return unicodedata.normalize("NFC", value)

    def preview_font_weight(self, font_weight: str) -> QFont.Weight:
        weight_map = {
            "ExtraLight": QFont.Weight.ExtraLight,
            "Light": QFont.Weight.Light,
            "Regular": QFont.Weight.Normal,
            "Medium": QFont.Weight.Medium,
            "Bold": QFont.Weight.Bold,
        }
        return weight_map.get(font_weight, QFont.Weight.ExtraLight)

    def preview_font_family_name(self, family_name: str, font_weight: str) -> str:
        if family_name == "Source Han Sans KR":
            weight_map = {
                "ExtraLight": "SourceHanSansKR-ExtraLight.otf",
                "Light": "SourceHanSansKR-Light.otf",
                "Regular": "SourceHanSansKR-Regular.otf",
                "Medium": "SourceHanSansKR-Medium.otf",
                "Bold": "SourceHanSansKR-Bold.otf",
            }
            font_file = weight_map.get(font_weight, "SourceHanSansKR-ExtraLight.otf")
            return self._bundled_font_families.get(font_file, DEFAULT_FONT_FAMILY)

        if family_name != "Noto Sans KR":
            return family_name

        weight_map = {
            "Light": "NotoSansKR-Light.otf",
            "Regular": "NotoSansKR-Regular.otf",
            "DemiLight": "NotoSansKR-DemiLight.otf",
            "Black": "NotoSansKR-Black.otf",
        }
        font_file = weight_map.get(font_weight, "NotoSansKR-Light.otf")
        return self._bundled_font_families.get(font_file, DEFAULT_FONT_FAMILY)

    def preview_subtitle_style(self, position: str, preview_scale: float) -> SubtitleStyle:
        if position == "top":
            font_family = self.top_subtitle_font_family_input.currentText()
            font_weight = self.top_subtitle_font_weight_input.currentText()
            font_size = self.top_subtitle_font_size_input.value()
            alignment = self.top_subtitle_alignment_input.currentText()
            vertical_margin = self.top_subtitle_margin_input.value()
        else:
            font_family = self.bottom_subtitle_font_family_input.currentText()
            font_weight = self.bottom_subtitle_font_weight_input.currentText()
            font_size = self.bottom_subtitle_font_size_input.value()
            alignment = self.bottom_subtitle_alignment_input.currentText()
            vertical_margin = self.bottom_subtitle_margin_input.value()

        return SubtitleStyle(
            font_family=font_family,
            font_weight=font_weight,
            font_size=max(1, round(font_size * preview_scale)),
            font_color=self.subtitle_color_value(position),
            vertical_margin=max(0, round(vertical_margin * preview_scale)),
            alignment=alignment,
        )

    def wrap_preview_text(self, metrics, text: str, max_width: int) -> list[str]:
        wrapped_lines: list[str] = []
        for paragraph in text.splitlines() or [text]:
            current = ""
            for character in paragraph:
                candidate = f"{current}{character}"
                if current and metrics.horizontalAdvance(candidate) > max_width:
                    wrapped_lines.append(current)
                    current = character
                else:
                    current = candidate
            if current:
                wrapped_lines.append(current)
            elif not paragraph:
                wrapped_lines.append("")
        return wrapped_lines or [""]

    def start_workflow(self) -> None:
        if self._worker_thread is not None:
            QMessageBox.information(self, "작업 진행 중", "이미 작업이 실행 중입니다.")
            return

        if self.audio_table.rowCount() == 0:
            QMessageBox.warning(self, "오디오 없음", "오디오 파일을 하나 이상 추가해 주세요.")
            return

        background_path = self.background_image_input.text().strip()
        if not background_path:
            QMessageBox.warning(self, "이미지 없음", "배경 이미지를 먼저 선택해 주세요.")
            return

        tracks: list[TrackInfo] = []
        for row in range(self.audio_table.rowCount()):
            source_path = self.audio_source_path(row)
            if source_path is None:
                continue
            tracks.append(
                TrackInfo(
                    index=row,
                    source_path=source_path,
                    top_caption=self.normalize_text(self.top_caption_input.text().strip()),
                    artist="",
                    title=self.normalize_text(self.bottom_caption_input.text().strip()),
                )
            )

        job_config = JobConfig(
            tracks=tracks,
            background_image=Path(background_path),
            output_directory=Path(self.output_directory_input.text().strip()),
            output_filename=self.output_filename_input.text().strip(),
            resolution_width=OUTPUT_WIDTH,
            resolution_height=OUTPUT_HEIGHT,
            top_caption_source=self.top_caption_source(),
            bottom_caption_source=self.bottom_caption_source(),
            top_subtitle_style=SubtitleStyle(
                font_family=self.top_subtitle_font_family_input.currentText(),
                font_weight=self.top_subtitle_font_weight_input.currentText(),
                font_size=self.top_subtitle_font_size_input.value(),
                font_color=self.top_subtitle_color_value,
                vertical_margin=self.top_subtitle_margin_input.value(),
                alignment=self.top_subtitle_alignment_input.currentText(),
            ),
            bottom_subtitle_style=SubtitleStyle(
                font_family=self.bottom_subtitle_font_family_input.currentText(),
                font_weight=self.bottom_subtitle_font_weight_input.currentText(),
                font_size=self.bottom_subtitle_font_size_input.value(),
                font_color=self.bottom_subtitle_color_value,
                vertical_margin=self.bottom_subtitle_margin_input.value(),
                alignment=self.bottom_subtitle_alignment_input.currentText(),
            ),
        )

        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.progress_label.setText("작업 시작 중")
        self.append_log("작업을 시작합니다...")
        self.set_running_state(True)

        self._worker_thread = QThread(self)
        self._worker = WorkflowWorker(job_config)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress_changed.connect(self.update_progress)
        self._worker.log_emitted.connect(self.append_log)
        self._worker.finished.connect(self.handle_workflow_finished)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self.cleanup_worker)

        self._worker_thread.start()

    def update_progress(self, percent: int, message: str) -> None:
        self.progress_bar.setValue(percent)
        self.progress_label.setText(message)

    def append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)

    def handle_workflow_finished(self, success: bool, message: str) -> None:
        self.append_log(message)
        title = "완료" if success else "실패"
        dialog = QMessageBox.information if success else QMessageBox.critical
        dialog(self, title, message)
        if not success:
            self.reset_progress_ui("대기 중")

    def cleanup_worker(self) -> None:
        self.set_running_state(False)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._worker_thread is not None:
            self._worker_thread.deleteLater()
            self._worker_thread = None

    def reset_progress_ui(self, label: str) -> None:
        self.progress_bar.setValue(0)
        self.progress_label.setText(label)

    def set_running_state(self, is_running: bool) -> None:
        self.start_button.setEnabled(not is_running)
        self.add_audio_button.setEnabled(not is_running)
        self.remove_audio_button.setEnabled(not is_running)
        self.background_image_button.setEnabled(not is_running)
        self.output_directory_button.setEnabled(not is_running)
        self.audio_table.setEnabled(not is_running)
        self.output_filename_input.setEnabled(not is_running)
        self.top_subtitle_font_family_input.setEnabled(not is_running)
        self.top_subtitle_font_weight_input.setEnabled(not is_running)
        self.top_subtitle_font_size_input.setEnabled(not is_running)
        self.top_subtitle_alignment_input.setEnabled(not is_running)
        self.bottom_subtitle_font_family_input.setEnabled(not is_running)
        self.bottom_subtitle_font_weight_input.setEnabled(not is_running)
        self.bottom_subtitle_font_size_input.setEnabled(not is_running)
        self.bottom_subtitle_alignment_input.setEnabled(not is_running)
        self.top_subtitle_color_button.setEnabled(not is_running)
        self.bottom_subtitle_color_button.setEnabled(not is_running)
        self.top_subtitle_margin_input.setEnabled(not is_running)
        self.bottom_subtitle_margin_input.setEnabled(not is_running)
        self.top_caption_input.setEnabled((not is_running) and (not self.top_caption_filename_radio.isChecked()))
        self.bottom_caption_input.setEnabled((not is_running) and (not self.bottom_caption_filename_radio.isChecked()))
        self.top_caption_filename_radio.setEnabled(not is_running)
        self.bottom_caption_filename_radio.setEnabled(not is_running)
        self.timeline_button.setEnabled(not is_running)
        self.timeline_copy_button.setEnabled(not is_running)

    def generate_timeline_text(self) -> None:
        if self.audio_table.rowCount() == 0:
            QMessageBox.warning(self, "오디오 없음", "오디오 파일을 하나 이상 추가해 주세요.")
            return

        from playlist_video_maker.services.workflow import get_audio_duration

        lines: list[str] = []
        current_time = 0.0

        for row in range(self.audio_table.rowCount()):
            source = self.audio_source_path(row)
            if source is None:
                continue
            track = TrackInfo(
                index=row,
                source_path=source,
                top_caption=self.normalize_text(self.top_caption_input.text().strip()),
                title=self.normalize_text(self.bottom_caption_input.text().strip()),
                artist="",
            )
            try:
                duration = get_audio_duration(source)
            except Exception:
                duration = 0.0

            minutes = int(current_time // 60)
            seconds = int(current_time % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            caption = track.resolved_bottom_caption_text(self.bottom_caption_source())
            lines.append(f"{time_str} {caption}".rstrip())

            current_time += duration

        self.timeline_output.setPlainText("\n".join(lines))

    def copy_timeline_text(self) -> None:
        text = self.timeline_output.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            QMessageBox.information(self, "복사 완료", "타임라인 텍스트가 클립보드에 복사되었습니다.")
