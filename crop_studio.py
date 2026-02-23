import os
import sys
import cv2
import mediapipe as mp
import numpy as np
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QIntValidator
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QFileDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QMessageBox,
    QCheckBox,
    QButtonGroup,
    QTabWidget,
    QLineEdit,
    QProgressBar,
)

from PIL import Image, ImageOps


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg"}

DEFAULT_TRAINING_RESOLUTION = 512


@dataclass(frozen=True)
class CropType:
    key: str
    label: str
    suffix: str
    color: QColor


CROP_TYPES = [
    CropType("face",  "Face",      "_face",  QColor(0, 200, 120)),
    CropType("torso", "Torso Up",  "_torso", QColor(30, 144, 255)),
    CropType("thigh", "Thigh Up",  "_thigh", QColor(255, 215, 0)),
    CropType("full",  "Full Body", "_full",  QColor(220, 20, 60)),
]


class ImageCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setMinimumSize(640, 480)

        self._pixmap: Optional[QPixmap] = None
        self._img_size_px: Optional[Tuple[int, int]] = None
        self._draw_rect: Optional[QRectF] = None

        self._dragging = False
        self._drag_start: Optional[QPointF] = None
        self._drag_end: Optional[QPointF] = None

        self._crop_color = CROP_TYPES[0].color
        self._interaction_enabled = True

    def set_crop_color(self, color: QColor):
        self._crop_color = color
        self.update()

    def set_interaction_enabled(self, enabled: bool):
        self._interaction_enabled = bool(enabled)
        if not self._interaction_enabled:
            self.clear_selection()

    def _notify_quality(self):
        parent = self.window()
        if hasattr(parent, "update_crop_quality"):
            parent.update_crop_quality()

    def clear_selection(self):
        self._dragging = False
        self._drag_start = None
        self._drag_end = None
        self.update()
        self._notify_quality()

    def has_image(self) -> bool:
        return (
            self._pixmap is not None
            and self._img_size_px is not None
            and not self._pixmap.isNull()
        )

    def set_image(self, pixmap: QPixmap, original_size_px: Tuple[int, int]):
        self._pixmap = pixmap
        self._img_size_px = original_size_px
        self.clear_selection()
        self.update()
        self._notify_quality()

    def _image_draw_rect(self) -> Optional[QRectF]:
        if not self._pixmap or self._pixmap.isNull():
            return None

        w = self.width()
        h = self.height()
        pm_w = self._pixmap.width()
        pm_h = self._pixmap.height()

        if pm_w <= 0 or pm_h <= 0 or w <= 0 or h <= 0:
            return None

        scale = min(w / pm_w, h / pm_h)
        draw_w = pm_w * scale
        draw_h = pm_h * scale
        left = (w - draw_w) / 2
        top = (h - draw_h) / 2
        return QRectF(left, top, draw_w, draw_h)

    def _selection_rect(self) -> Optional[QRectF]:
        if self._drag_start is None or self._drag_end is None:
            return None
        x1, y1 = self._drag_start.x(), self._drag_start.y()
        x2, y2 = self._drag_end.x(), self._drag_end.y()
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)
        return QRectF(left, top, right - left, bottom - top)

    def _clamp_point_to_draw_rect(self, p: QPointF, r: QRectF) -> QPointF:
        x = min(max(p.x(), r.left()), r.right())
        y = min(max(p.y(), r.top()), r.bottom())
        return QPointF(x, y)

    def mousePressEvent(self, event):
        if not self._interaction_enabled:
            return
        if event.button() != Qt.LeftButton:
            return
        if not self.has_image():
            return

        draw_rect = self._image_draw_rect()
        if not draw_rect:
            return

        pos = QPointF(event.position())
        if not draw_rect.contains(pos):
            return

        self._dragging = True
        pos = self._clamp_point_to_draw_rect(pos, draw_rect)
        self._drag_start = pos
        self._drag_end = pos
        self.update()
        self._notify_quality()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        if not self.has_image():
            return

        draw_rect = self._image_draw_rect()
        if not draw_rect:
            return

        pos = self._clamp_point_to_draw_rect(QPointF(event.position()), draw_rect)
        self._drag_end = pos
        self.update()
        self._notify_quality()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        self._notify_quality()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 18, 18))

        if not self._pixmap or self._pixmap.isNull():
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(self.rect(), Qt.AlignCenter, "Select an input folder to load images.")
            return

        draw_rect = self._image_draw_rect()
        self._draw_rect = draw_rect

        painter.drawPixmap(draw_rect, self._pixmap, QRectF(self._pixmap.rect()))

        sel = self._selection_rect()
        if sel and sel.width() > 2 and sel.height() > 2:
            fill = QColor(self._crop_color)
            fill.setAlpha(60)
            painter.fillRect(sel, fill)

            pen = QPen(self._crop_color)
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(sel)

    def get_crop_box_in_original_px(self) -> Optional[Tuple[int, int, int, int]]:
        if not self.has_image():
            return None
        if not self._draw_rect:
            self._draw_rect = self._image_draw_rect()
        if not self._draw_rect:
            return None

        sel = self._selection_rect()
        if not sel or sel.width() < 2 or sel.height() < 2:
            return None

        dr = self._draw_rect
        ow, oh = self._img_size_px

        left   = max(sel.left(),   dr.left())
        top    = max(sel.top(),    dr.top())
        right  = min(sel.right(),  dr.right())
        bottom = min(sel.bottom(), dr.bottom())

        if right <= left or bottom <= top:
            return None

        scale_x = ow / dr.width()
        scale_y = oh / dr.height()

        crop_left   = int(round((left   - dr.left()) * scale_x))
        crop_top    = int(round((top    - dr.top())  * scale_y))
        crop_right  = int(round((right  - dr.left()) * scale_x))
        crop_bottom = int(round((bottom - dr.top())  * scale_y))

        crop_left   = max(0, min(crop_left,   ow - 1))
        crop_top    = max(0, min(crop_top,    oh - 1))
        crop_right  = max(crop_left  + 1, min(crop_right,  ow))
        crop_bottom = max(crop_top   + 1, min(crop_bottom, oh))

        return (crop_left, crop_top, crop_right, crop_bottom)


class CropTile(QPushButton):
    def __init__(self, crop_type: CropType, parent=None):
        super().__init__(crop_type.label, parent)
        self.crop_type = crop_type
        self.completed = False
        self.setCheckable(True)
        self.setMinimumHeight(60)
        self.update_style()

    def update_style(self):
        base = self.crop_type.color.name()

        if self.completed:
            border = "5px solid #00ff00"
        elif self.isChecked():
            border = "4px solid white"
        else:
            border = "2px solid #222"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {base};
                color: white;
                font-weight: bold;
                border-radius: 6px;
                border: {border};
            }}
        """)

    def mark_completed(self, state: bool):
        self.completed = state
        if state:
            self.setText(f"{self.crop_type.label} ✔")
        else:
            self.setText(self.crop_type.label)
        self.update_style()


class CropStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoRA Prep Suite — Crop Studio (Phase 1)")
        self.setWindowState(Qt.WindowMaximized)

        self.training_resolution: int = DEFAULT_TRAINING_RESOLUTION

        self.input_dir:  Optional[str] = None
        self.output_dir: Optional[str] = None

        self.images: List[str] = []
        self.index: int = 0
        self.current_image_path: Optional[str] = None

        self.current_crop_type: CropType = CROP_TYPES[0]
        self.canvas = ImageCanvas()

        # ── Folder controls ──
        self.input_label  = QLabel("Input: (not set)")
        self.output_label = QLabel("Output: (not set)")
        self.input_label.setWordWrap(True)
        self.output_label.setWordWrap(True)

        self.btn_input  = QPushButton("Select Input Folder")
        self.btn_output = QPushButton("Select Output Folder")
        self.btn_input.clicked.connect(self.pick_input_folder)
        self.btn_output.clicked.connect(self.pick_output_folder)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["Keep original", "PNG", "JPG"])

        self.auto_advance   = QCheckBox("Auto-advance after Save")
        self.auto_advance.setChecked(False)
        self.use_subfolders = QCheckBox("Auto-create subfolders per crop type")
        self.use_subfolders.setChecked(True)

        self.status_label = QLabel("No images loaded.")
        self.status_label.setStyleSheet("color: #EAEAEA;")

        # ── Crop type tiles ──
        self.tile_buttons: List[CropTile] = []
        self.tile_group = QButtonGroup(self)
        self.tile_group.setExclusive(True)

        for i, ct in enumerate(CROP_TYPES):
            tile = CropTile(ct, self)
            if i == 0:
                tile.setChecked(True)
                self.current_crop_type = ct
                self.canvas.set_crop_color(ct.color)
            tile.clicked.connect(self.handle_tile_click)
            self.tile_group.addButton(tile, i)
            self.tile_buttons.append(tile)

        # ── Signal Strength Indicator ──
        self.signal_title = QLabel("Framing Signal Strength")
        self.signal_title.setAlignment(Qt.AlignCenter)
        self.signal_title.setStyleSheet("font-weight: bold;")
        self.signal_title.setToolTip(
            "This measures *bucket upscaling pressure*.\n"
            "It is NOT a judgment of whether a crop is 'useful'.\n\n"
            "Upscale factor = training_target / shortest_side.\n"
            "Lower upscale = clearer signal for training.\n"
            "Higher upscale = more blur/mush introduced by resizing."
        )

        self.quality_indicator = QLabel()
        self.quality_indicator.setFixedSize(40, 40)
        self.quality_indicator.setStyleSheet("background-color: gray; border-radius: 20px;")

        self.dimension_label = QLabel("—")
        self.dimension_label.setAlignment(Qt.AlignCenter)
        self.dimension_label.setWordWrap(True)
        self.dimension_label.setFixedWidth(220)
        self.dimension_label.setMinimumHeight(52)

        self.training_target_label = QLabel("Training target:")
        self.training_target_combo = QComboBox()
        self.training_target_combo.addItems(["512", "768", "1024", "Custom"])
        self.training_target_combo.setCurrentText(str(DEFAULT_TRAINING_RESOLUTION))
        self.training_target_combo.currentTextChanged.connect(self.on_training_target_changed)

        self.custom_training_input = QLineEdit()
        self.custom_training_input.setPlaceholderText("Enter resolution (e.g. 896)")
        self.custom_training_input.setValidator(QIntValidator(64, 4096))
        self.custom_training_input.hide()
        self.custom_training_input.textChanged.connect(self.on_custom_training_changed)

        # ── Mode toggles ──
        self.manual_mode_cb = QCheckBox("Manual mode")
        self.auto_mode_cb   = QCheckBox("Automatic mode")
        self.manual_mode_cb.setChecked(True)
        self.auto_mode_cb.setChecked(False)
        self.manual_mode_cb.stateChanged.connect(self.on_mode_toggled)
        self.auto_mode_cb.stateChanged.connect(self.on_mode_toggled)

        # ── Auto UI ──
        # Chunky Start button — same height as crop tiles
        self.auto_start_btn = QPushButton("Start Cropping")
        self.auto_start_btn.setMinimumHeight(60)
        self.auto_start_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 15px;
                border-radius: 6px;
                border: 2px solid #555;
                background-color: #3a3a3a;
            }
            QPushButton:hover   { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #5a5a5a; }
            QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
        """)
        self.auto_start_btn.clicked.connect(self.start_auto_cropping)

        # Chunky Stop button — turns red when clicked
        self._stop_requested = False
        self._stop_style_idle = """
            QPushButton {
                font-weight: bold;
                font-size: 15px;
                border-radius: 6px;
                border: 2px solid #555;
                background-color: #3a3a3a;
            }
            QPushButton:hover   { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #5a5a5a; }
            QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
        """
        self._stop_style_active = """
            QPushButton {
                background-color: #cc2200;
                color: white;
                font-weight: bold;
                font-size: 15px;
                border-radius: 6px;
                border: 2px solid #ff4422;
            }
            QPushButton:hover { background-color: #dd3311; }
        """
        self.auto_stop_btn = QPushButton("Stop Cropping")
        self.auto_stop_btn.setMinimumHeight(60)
        self.auto_stop_btn.setEnabled(False)
        self.auto_stop_btn.setStyleSheet(self._stop_style_idle)
        self.auto_stop_btn.clicked.connect(self.request_stop_cropping)

        self.auto_progress_text = QLabel("0 / 0")
        self.auto_progress_text.setAlignment(Qt.AlignCenter)

        self.auto_progress = QProgressBar()
        self.auto_progress.setMinimum(0)
        self.auto_progress.setValue(0)

        self.auto_eta_label = QLabel("ETA: —")
        self.auto_eta_label.setAlignment(Qt.AlignCenter)

        # Wall-clock timer — ticks every second after ETA is locked
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(1000)
        self.auto_timer.timeout.connect(self._tick_eta_countdown)

        # ── Right panel nav buttons ──
        self.btn_prev   = QPushButton("◀ Prev (Q)")
        self.btn_cancel = QPushButton("Cancel Crop (Esc)")
        self.btn_save   = QPushButton("Save Crop (S)")
        self.btn_next   = QPushButton("Next ▶ (W)")

        self.btn_prev.clicked.connect(self.prev_image)
        self.btn_next.clicked.connect(self.next_image)
        self.btn_cancel.clicked.connect(self.canvas.clear_selection)
        self.btn_save.clicked.connect(self.save_crop)

        # Nav layout
        nav_layout = QVBoxLayout()
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_save)
        nav_layout.addWidget(self.btn_cancel)
        nav_layout.addSpacing(20)
        nav_layout.addWidget(QLabel("Output format:"))
        nav_layout.addWidget(self.format_combo)
        nav_layout.addWidget(self.auto_advance)
        nav_layout.addWidget(self.use_subfolders)
        nav_layout.addStretch(1)

        # Folder buttons with padding so they don't hug the panel edges
        folder_container = QWidget()
        folder_layout = QVBoxLayout(folder_container)
        folder_layout.setContentsMargins(8, 0, 8, 0)
        folder_layout.addWidget(self.btn_input)
        folder_layout.addWidget(self.input_label)
        folder_layout.addSpacing(6)
        folder_layout.addWidget(self.btn_output)
        folder_layout.addWidget(self.output_label)
        nav_layout.addWidget(folder_container)
        nav_layout.addSpacing(8)

        # ── Tabs ──
        tabs = QTabWidget()

        crop_root   = QWidget()
        main_layout = QHBoxLayout(crop_root)

        # Left panel
        left_panel = QVBoxLayout()

        # Manual section — original untouched spacing/padding
        self.manual_section = QWidget()
        manual_layout = QVBoxLayout(self.manual_section)
        manual_layout.setContentsMargins(0, 0, 0, 0)

        for tile in self.tile_buttons:
            manual_layout.addWidget(tile)

        manual_layout.addSpacing(14)
        manual_layout.addWidget(self.signal_title)
        manual_layout.addWidget(self.quality_indicator, alignment=Qt.AlignCenter)
        manual_layout.addWidget(self.dimension_label)
        manual_layout.addSpacing(10)
        manual_layout.addWidget(self.training_target_label)
        manual_layout.addWidget(self.training_target_combo)
        manual_layout.addWidget(self.custom_training_input)

        # Auto section
        self.auto_section = QWidget()
        auto_layout = QVBoxLayout(self.auto_section)
        auto_layout.setContentsMargins(0, 0, 0, 0)
        auto_layout.addWidget(self.auto_start_btn)
        auto_layout.addSpacing(6)
        auto_layout.addWidget(self.auto_stop_btn)
        auto_layout.addSpacing(10)
        auto_layout.addWidget(self.auto_progress_text)
        auto_layout.addWidget(self.auto_progress)
        auto_layout.addSpacing(6)
        auto_layout.addWidget(self.auto_eta_label)
        auto_layout.addStretch(1)

        left_panel.addWidget(self.manual_section)
        left_panel.addWidget(self.auto_section)

        # Stretch pushes mode checkboxes to the very bottom — they never move
        left_panel.addStretch(1)
        left_panel.addWidget(self.manual_mode_cb)
        left_panel.addWidget(self.auto_mode_cb)
        left_panel.addSpacing(8)

        self.auto_section.hide()

        # Center panel
        center_panel = QVBoxLayout()
        center_panel.addWidget(self.canvas, stretch=1)

        # Right panel
        right_panel = QVBoxLayout()
        right_panel.addWidget(self.status_label)
        right_panel.addSpacing(8)
        right_panel.addLayout(nav_layout)

        main_layout.addLayout(left_panel,   1)
        main_layout.addLayout(center_panel, 5)
        main_layout.addLayout(right_panel,  2)

        tabs.addTab(crop_root, "Crop Studio")

        # Settings tab — folders now live in right panel
        settings_tab    = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.addStretch(1)
        settings_layout.addWidget(
            QLabel("Input and output folders are in the right panel\nof the Crop Studio tab."),
            alignment=Qt.AlignCenter
        )
        settings_layout.addStretch(1)
        tabs.addTab(settings_tab, "Settings")

        self.setCentralWidget(tabs)

        # ── MediaPipe ──
        self.mp_pose    = mp.solutions.pose
        self.pose_engine = self.mp_pose.Pose(
            static_image_mode=True,
            model_complexity=2,
            enable_segmentation=False
        )

        self.apply_mode_ui()

        # ── Auto state ──
        self.auto_current_index = 0
        self.auto_boxes  = None
        self.auto_step   = 0
        self.auto_running = False

        self.auto_anim_timer = QTimer(self)
        self.auto_anim_timer.timeout.connect(self.auto_step_forward)

        # Timing
        self.auto_start_time:      Optional[float] = None
        self.auto_completed_images: int            = 0
        self.auto_eta_locked:       bool           = False
        self.auto_remaining_secs:   float          = 0.0

    # ──────────────────────────────────────────────
    # ETA TICK  (every 1 second, pure countdown)
    # ──────────────────────────────────────────────
    def _tick_eta_countdown(self):
        if not self.auto_running:
            return
        if not self.auto_eta_locked:
            self.auto_eta_label.setText("ETA: Calculating…")
            return
        self.auto_remaining_secs = max(0.0, self.auto_remaining_secs - 1.0)
        mins = int(self.auto_remaining_secs) // 60
        secs = int(self.auto_remaining_secs) % 60
        self.auto_eta_label.setText(f"ETA: {mins:02d}:{secs:02d}")

    # ──────────────────────────────────────────────
    # MODE UI
    # ──────────────────────────────────────────────
    def on_mode_toggled(self):
        manual = self.manual_mode_cb.isChecked()
        auto   = self.auto_mode_cb.isChecked()
        sender = self.sender()

        if manual and auto:
            if sender == self.manual_mode_cb:
                self.auto_mode_cb.setChecked(False)
            else:
                self.manual_mode_cb.setChecked(False)

        if not self.manual_mode_cb.isChecked() and not self.auto_mode_cb.isChecked():
            self.manual_mode_cb.setChecked(True)

        self.apply_mode_ui()

    def apply_mode_ui(self):
        if self.manual_mode_cb.isChecked():
            self.manual_section.show()
            self.auto_section.hide()
            self.canvas.set_interaction_enabled(True)
            self.update_crop_quality()
        else:
            self.manual_section.hide()
            self.auto_section.show()
            self.canvas.set_interaction_enabled(False)
            self.canvas.clear_selection()

    # ──────────────────────────────────────────────
    # LOCK NAV BUTTONS DURING CROPPING
    # ──────────────────────────────────────────────
    def _set_nav_locked(self, locked: bool):
        for btn in (self.btn_prev, self.btn_next, self.btn_save, self.btn_cancel):
            btn.setEnabled(not locked)
        if locked:
            style = "background-color: #222; color: #555; border: 1px solid #333; padding: 6px;"
            for btn in (self.btn_prev, self.btn_next, self.btn_save, self.btn_cancel):
                btn.setStyleSheet(style)
        else:
            for btn in (self.btn_prev, self.btn_next, self.btn_save, self.btn_cancel):
                btn.setStyleSheet("")

    # ──────────────────────────────────────────────
    # STOP CROPPING
    # ──────────────────────────────────────────────
    def request_stop_cropping(self):
        """User pressed Stop — turn it red and flag the stop."""
        self._stop_requested = True
        self.auto_stop_btn.setText("Stopping…")
        self.auto_stop_btn.setStyleSheet(self._stop_style_active)
        self.auto_stop_btn.setEnabled(False)

    def _finish_auto_run(self, completed: bool):
        """Clean up after a run finishes or is stopped."""
        self.auto_running     = False
        self._stop_requested  = False
        self.auto_timer.stop()
        self.auto_anim_timer.stop()

        self.auto_start_btn.setEnabled(True)
        self.auto_stop_btn.setEnabled(False)
        self.auto_stop_btn.setText("Stop Cropping")
        self.auto_stop_btn.setStyleSheet(self._stop_style_idle)

        self._set_nav_locked(False)

        if completed:
            self.auto_eta_label.setText("ETA: 00:00")
            QMessageBox.information(self, "Done", "Auto cropping complete.")
        else:
            self.auto_eta_label.setText("ETA: —")
            self.auto_progress.setValue(0)
            self.auto_progress_text.setText("0 / 0")
            QMessageBox.information(self, "Stopped", "Auto cropping stopped.")

    # ──────────────────────────────────────────────
    # ──────────────────────────────────────────────
    # START AUTO CROPPING
    # ──────────────────────────────────────────────
    def start_auto_cropping(self):
        if not self.images:
            QMessageBox.warning(self, "No images", "Load an input folder first.")
            return
        if not self.output_dir:
            QMessageBox.warning(self, "No output folder", "Select an output folder first.")
            return

        total = len(self.images)

        self.auto_running          = True
        self._stop_requested       = False
        self.auto_current_index    = 0
        self.auto_completed_images = 0
        self.auto_eta_locked       = True   # locked before we start
        self.auto_remaining_secs   = 0.0
        self.auto_start_time       = time.perf_counter()

        self.auto_start_btn.setEnabled(False)
        self.auto_stop_btn.setEnabled(True)
        self.auto_stop_btn.setText("Stop Cropping")
        self.auto_stop_btn.setStyleSheet(self._stop_style_idle)
        self.auto_eta_label.setText("ETA: Calculating…")
        self.auto_progress_text.setText(f"0 / {total}")
        self.auto_progress.setMaximum(total)
        self.auto_progress.setValue(0)
        self._set_nav_locked(True)
        QApplication.processEvents()

        # ── Time the entire set silently ──
        # Run pose detection on every image with no canvas updates, no saves.
        # This gives a real average per-image time across the whole dataset.
        t0 = time.perf_counter()
        valid_count = 0
        for path in self.images:
            self.compute_sequential_boxes(path)
            valid_count += 1
            QApplication.processEvents()
        total_detect_time = time.perf_counter() - t0

        # Average per-image detection time. Add overhead for the 4-step animation
        # (4 × 200ms), save I/O, and a comfortable buffer so the timer never
        # finishes before the cropping does.
        anim_and_save_overhead = 1.5  # seconds per image
        avg_per_image = (total_detect_time / max(valid_count, 1)) + anim_and_save_overhead
        self.auto_remaining_secs = avg_per_image * total

        mins = int(self.auto_remaining_secs) // 60
        secs = int(self.auto_remaining_secs) % 60
        self.auto_eta_label.setText(f"ETA: {mins:02d}:{secs:02d}")

        # Start the wall-clock countdown ticker NOW, then begin animated cropping
        self.auto_timer.start()
        QApplication.processEvents()
        self.process_next_image()

    # ──────────────────────────────────────────────
    # PROCESS IMAGES
    # ──────────────────────────────────────────────
    def process_next_image(self):
        if self._stop_requested:
            self._finish_auto_run(completed=False)
            return

        if self.auto_current_index >= len(self.images):
            self._finish_auto_run(completed=True)
            return

        # Every image gets the full animated pass
        image_path = self.images[self.auto_current_index]
        self.index = self.auto_current_index
        self.show_image_at_index()

        boxes = self.compute_sequential_boxes(image_path)

        if not boxes:
            self.auto_current_index += 1
            self.auto_progress.setValue(self.auto_current_index)
            self.auto_progress_text.setText(
                f"{self.auto_current_index} / {len(self.images)}"
            )
            QApplication.processEvents()
            self.process_next_image()
            return

        self.auto_boxes = boxes
        self.auto_step  = 0
        self.auto_anim_timer.start(200)

    def auto_step_forward(self):
        crop_order = ["full", "thigh", "torso", "face"]

        if self.auto_step >= len(crop_order):
            self.auto_anim_timer.stop()
            self.save_auto_crops(self.images[self.auto_current_index])

            self.auto_completed_images += 1
            self.auto_current_index    += 1
            self.auto_progress.setValue(self.auto_current_index)
            self.auto_progress_text.setText(
                f"{self.auto_current_index} / {len(self.images)}"
            )

            QApplication.processEvents()
            self.process_next_image()
            return

        crop_key = crop_order[self.auto_step]
        box      = self.auto_boxes[crop_key]

        for ct in CROP_TYPES:
            if ct.key == crop_key:
                self.canvas.set_crop_color(ct.color)
                break

        self.show_overlay_box(box)
        self.auto_step += 1

    # ──────────────────────────────────────────────
    # OVERLAY + SAVE
    # ──────────────────────────────────────────────
    def show_overlay_box(self, box):
        left, top, right, bottom = box

        dr = self.canvas._image_draw_rect()
        if not dr:
            return

        ow, oh   = self.canvas._img_size_px
        scale_x  = dr.width()  / ow
        scale_y  = dr.height() / oh

        x1 = dr.left() + left  * scale_x
        y1 = dr.top()  + top   * scale_y
        x2 = dr.left() + right * scale_x
        y2 = dr.top()  + bottom * scale_y

        self.canvas._drag_start = QPointF(x1, y1)
        self.canvas._drag_end   = QPointF(x2, y2)
        self.canvas.update()

    def save_auto_crops_from(self, image_path: str, boxes: dict):
        for crop_key, crop_box in boxes.items():
            left, top, right, bottom = crop_box
            try:
                pil     = Image.open(image_path)
                pil     = ImageOps.exif_transpose(pil)
                cropped = pil.crop((left, top, right, bottom))

                base     = os.path.splitext(os.path.basename(image_path))[0]
                out_name = f"{base}_{crop_key}_C.png"

                if self.use_subfolders.isChecked():
                    subfolder = os.path.join(self.output_dir, crop_key)
                    os.makedirs(subfolder, exist_ok=True)
                    out_path = os.path.join(subfolder, out_name)
                else:
                    out_path = os.path.join(self.output_dir, out_name)

                cropped.save(out_path, format="PNG")
            except Exception as e:
                print("Auto save failed:", e)

    def save_auto_crops(self, image_path):
        self.save_auto_crops_from(image_path, self.auto_boxes)

    # ──────────────────────────────────────────────
    # MEDIAPIPE
    # ──────────────────────────────────────────────
    def detect_pose_landmarks(self, image_path):
        img = cv2.imread(image_path)
        if img is None:
            return None

        h, w     = img.shape[:2]
        img_rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results  = self.pose_engine.process(img_rgb)

        if not results.pose_landmarks:
            return None

        landmarks = []
        for lm in results.pose_landmarks.landmark:
            landmarks.append((int(lm.x * w), int(lm.y * h)))

        return landmarks, w, h

    def compute_sequential_boxes(self, image_path):
        pose_data = self.detect_pose_landmarks(image_path)
        if not pose_data:
            return None

        landmarks, w, h = pose_data

        nose       = landmarks[0]
        l_shoulder = landmarks[11]
        r_shoulder = landmarks[12]
        l_hip      = landmarks[23]
        r_hip      = landmarks[24]
        l_knee     = landmarks[25]
        r_knee     = landmarks[26]

        xs    = [pt[0] for pt in landmarks]
        min_x = max(0, min(xs))
        max_x = min(w, max(xs))
        pad_x = int((max_x - min_x) * 0.1)
        min_x = max(0, min_x - pad_x)
        max_x = min(w, max_x + pad_x)

        raw_top     = min(pt[1] for pt in landmarks)
        bottom_full = max(pt[1] for pt in landmarks)

        shoulder_width = abs(l_shoulder[0] - r_shoulder[0])
        head_padding   = int(shoulder_width * 0.75)
        top_full       = max(0, raw_top - head_padding)
        body_height    = bottom_full - top_full

        knee_y       = max(l_knee[1], r_knee[1])
        thigh_adjust = int(body_height * 0.10)
        top_thigh    = top_full
        bottom_thigh = max(top_full, knee_y - thigh_adjust)

        hip_y        = max(l_hip[1], r_hip[1])
        torso_adjust = int(body_height * 0.08)
        top_torso    = top_full
        bottom_torso = max(top_full, hip_y - torso_adjust)

        face_size   = int(shoulder_width * 1.2)
        half        = face_size // 2
        face_left   = max(0, nose[0] - half)
        face_right  = min(w, nose[0] + half)
        face_top    = max(0, nose[1] - half)
        face_bottom = min(h, nose[1] + half)

        return {
            "full":  (min_x, top_full,  max_x, bottom_full),
            "thigh": (min_x, top_thigh, max_x, bottom_thigh),
            "torso": (min_x, top_torso, max_x, bottom_torso),
            "face":  (face_left, face_top, face_right, face_bottom),
        }

    # ──────────────────────────────────────────────
    # TRAINING TARGET
    # ──────────────────────────────────────────────
    def on_training_target_changed(self, text: str):
        if text == "Custom":
            self.custom_training_input.show()
            self.custom_training_input.setFocus()
            return
        self.custom_training_input.hide()
        try:
            self.training_resolution = int(text)
        except ValueError:
            self.training_resolution = DEFAULT_TRAINING_RESOLUTION
        self.update_crop_quality()

    def on_custom_training_changed(self, text: str):
        if not text.strip().isdigit():
            return
        val = int(text.strip())
        if val < 64:
            return
        self.training_resolution = val
        self.update_crop_quality()

    # ──────────────────────────────────────────────
    # FOLDER PICKERS
    # ──────────────────────────────────────────────
    def pick_input_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if not directory:
            return
        self.input_dir = directory
        self.input_label.setText(f"Input: {directory}")
        self.load_images()

    def pick_output_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not directory:
            return
        self.output_dir = directory
        self.output_label.setText(f"Output: {directory}")

    # ──────────────────────────────────────────────
    # LOAD / SHOW IMAGES
    # ──────────────────────────────────────────────
    def load_images(self):
        if not self.input_dir or not os.path.isdir(self.input_dir):
            return

        files = []
        for name in os.listdir(self.input_dir):
            _, ext = os.path.splitext(name)
            if ext.lower() in SUPPORTED_EXTS:
                files.append(os.path.join(self.input_dir, name))

        files.sort(key=lambda p: os.path.basename(p).lower())
        self.images = files
        self.index  = 0

        if not self.images:
            self.current_image_path = None
            self.canvas.set_image(QPixmap(), (1, 1))
            self.status_label.setText("No supported images found in input folder.")
            self.update_crop_quality()
            return

        self.show_image_at_index()

    def show_image_at_index(self):
        if not self.images:
            return
        self.index = max(0, min(self.index, len(self.images) - 1))
        path = self.images[self.index]
        self.current_image_path = path

        pil = Image.open(path)
        pil = ImageOps.exif_transpose(pil)
        ow, oh = pil.size

        if pil.mode not in ("RGB", "RGBA"):
            pil = pil.convert("RGB")

        import io
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        pm = QPixmap()
        pm.loadFromData(buf.getvalue(), "PNG")

        self.canvas.set_image(pm, (ow, oh))
        self.status_label.setText(
            f"Image {self.index + 1}/{len(self.images)} — {os.path.basename(path)} ({ow}×{oh})"
        )

        for b in self.tile_buttons:
            b.mark_completed(False)

        self.update_crop_quality()

    # ──────────────────────────────────────────────
    # NAVIGATION
    # ──────────────────────────────────────────────
    def next_image(self):
        if not self.images:
            return
        if self.index < len(self.images) - 1:
            self.index += 1
            self.show_image_at_index()
        else:
            QMessageBox.information(self, "Done", "You reached the last image.")

    def prev_image(self):
        if not self.images:
            return
        if self.index > 0:
            self.index -= 1
            self.show_image_at_index()

    # ──────────────────────────────────────────────
    # MANUAL SAVE
    # ──────────────────────────────────────────────
    def save_crop(self):
        if not self.current_image_path:
            QMessageBox.warning(self, "No image", "Load an input folder first.")
            return
        if not self.output_dir:
            QMessageBox.warning(self, "No output folder", "Select an output folder first.")
            return

        crop_box = self.canvas.get_crop_box_in_original_px()
        if not crop_box:
            QMessageBox.warning(self, "No crop", "Draw a crop rectangle first (click + drag).")
            return

        src_path = self.current_image_path
        base     = os.path.splitext(os.path.basename(src_path))[0]
        src_ext  = os.path.splitext(src_path)[1].lower()

        fmt_choice = self.format_combo.currentText()
        if fmt_choice == "Keep original":
            out_ext    = src_ext
            out_format = "PNG" if out_ext == ".png" else "JPEG"
        elif fmt_choice == "PNG":
            out_ext    = ".png"
            out_format = "PNG"
        else:
            out_ext    = ".jpg"
            out_format = "JPEG"

        out_name = f"{base}{self.current_crop_type.suffix}_C{out_ext}"

        if self.use_subfolders.isChecked():
            subfolder = os.path.join(self.output_dir, self.current_crop_type.key)
            os.makedirs(subfolder, exist_ok=True)
            out_path = os.path.join(subfolder, out_name)
        else:
            out_path = os.path.join(self.output_dir, out_name)

        try:
            pil     = Image.open(src_path)
            pil     = ImageOps.exif_transpose(pil)
            cropped = pil.crop(crop_box)

            if out_format == "JPEG" and cropped.mode in ("RGBA", "LA"):
                cropped = cropped.convert("RGB")
            elif out_format == "JPEG" and cropped.mode not in ("RGB", "L"):
                cropped = cropped.convert("RGB")

            save_kwargs = {}
            if out_format == "JPEG":
                save_kwargs.update({"quality": 95, "subsampling": 0, "optimize": True})
            elif out_format == "PNG":
                save_kwargs.update({"optimize": True})

            if os.path.exists(out_path):
                i = 2
                folder       = os.path.dirname(out_path)
                name_no_ext  = os.path.splitext(out_name)[0]
                while True:
                    candidate = os.path.join(folder, f"{name_no_ext}_{i}{out_ext}")
                    if not os.path.exists(candidate):
                        out_path = candidate
                        break
                    i += 1

            cropped.save(out_path, format=out_format, **save_kwargs)

            for b in self.tile_buttons:
                if b.crop_type == self.current_crop_type:
                    b.mark_completed(True)

        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"Could not save crop.\n\n{e}")
            return

        self.canvas.clear_selection()

        if self.auto_advance.isChecked():
            self.next_image()

    # ──────────────────────────────────────────────
    # CROP TYPE + SIGNAL STRENGTH
    # ──────────────────────────────────────────────
    def handle_tile_click(self):
        button = self.sender()
        idx    = self.tile_group.id(button)
        self.current_crop_type = CROP_TYPES[idx]
        self.canvas.set_crop_color(self.current_crop_type.color)
        for b in self.tile_buttons:
            b.update_style()
        self.update_crop_quality()

    def update_crop_quality(self):
        crop_box = self.canvas.get_crop_box_in_original_px()

        if not crop_box:
            self.quality_indicator.setStyleSheet("background-color: gray; border-radius: 20px;")
            self.dimension_label.setText("—")
            return

        left, top, right, bottom = crop_box
        width    = right - left
        height   = bottom - top
        shortest = max(1, min(width, height))

        target  = max(1, int(self.training_resolution))
        upscale = target / shortest

        if upscale <= 1.70:
            color = "#00ff00"
        elif upscale <= 2.50:
            color = "#ffd000"
        elif upscale <= 3.50:
            color = "#ff8800"
        else:
            color = "#ff0000"

        self.quality_indicator.setStyleSheet(f"background-color: {color}; border-radius: 20px;")
        self.dimension_label.setText(
            f"{width} × {height}\n"
            f"Upscale → {upscale:.2f}×  (to {target}px)"
        )

    # ──────────────────────────────────────────────
    # KEYBINDS
    # ──────────────────────────────────────────────
    def select_crop_type(self, idx: int):
        if idx < 0 or idx >= len(self.tile_buttons):
            return
        button = self.tile_buttons[idx]
        button.setChecked(True)
        self.current_crop_type = CROP_TYPES[idx]
        self.canvas.set_crop_color(self.current_crop_type.color)
        for b in self.tile_buttons:
            b.update_style()
        self.update_crop_quality()

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_1: self.select_crop_type(0); event.accept(); return
        if key == Qt.Key_2: self.select_crop_type(1); event.accept(); return
        if key == Qt.Key_3: self.select_crop_type(2); event.accept(); return
        if key == Qt.Key_4: self.select_crop_type(3); event.accept(); return

        if key == Qt.Key_Q:      self.prev_image();             event.accept(); return
        if key == Qt.Key_W:      self.next_image();             event.accept(); return
        if key == Qt.Key_S:      self.save_crop();              event.accept(); return
        if key == Qt.Key_Escape: self.canvas.clear_selection(); event.accept(); return

        super().keyPressEvent(event)


def apply_dark_theme(app):
    app.setStyleSheet("""
        QWidget {
            background-color: #2b2b2b;
            color: #e0e0e0;
            font-size: 14px;
        }
        QPushButton {
            background-color: #3a3a3a;
            border: 1px solid #555;
            padding: 6px;
        }
        QPushButton:hover   { background-color: #4a4a4a; }
        QPushButton:pressed { background-color: #5a5a5a; }
        QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
        QLabel   { color: #dcdcdc; }
        QComboBox {
            background-color: #3a3a3a;
            border: 1px solid #555;
            padding: 4px;
        }
        QLineEdit {
            background-color: #3a3a3a;
            border: 1px solid #555;
            padding: 4px;
        }
        QCheckBox { spacing: 6px; }
        QGroupBox { border: 1px solid #444; margin-top: 10px; }
        QTabWidget::pane { border: 1px solid #444; }
        QTabBar::tab {
            background: #3a3a3a;
            border: 1px solid #555;
            padding: 8px 14px;
            margin-right: 2px;
        }
        QTabBar::tab:selected { background: #4a4a4a; }
    """)


def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    w = CropStudio()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()