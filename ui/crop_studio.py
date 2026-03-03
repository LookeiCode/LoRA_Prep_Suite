import io
import os
import time
from typing import Optional, List

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPixmap, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QButtonGroup, QLineEdit, QProgressBar,
    QFileDialog, QMessageBox, QApplication,
)
from PIL import Image, ImageOps

from core.config import CROP_TYPES, DEFAULT_TRAINING_RESOLUTION, SUPPORTED_EXTS
from core.pose_detection import PoseDetector
from ui.canvas import ImageCanvas
from ui.advanced_crop_settings import AdvancedCropSettingsDialog


class CropTile(QPushButton):
    def __init__(self, crop_type, parent=None):
        super().__init__(crop_type.label, parent)
        self.crop_type = crop_type
        self.completed = False
        self.setCheckable(True)
        self.setMinimumHeight(36)
        self.update_style()

    def update_style(self):
        base   = self.crop_type.color.name()
        border = ("5px solid #00ff00" if self.completed
                  else "4px solid white" if self.isChecked()
                  else "2px solid #222")
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
        self.blockSignals(True)
        self.completed = state
        self.setText(f"{self.crop_type.label} ✔" if state else self.crop_type.label)
        self.update_style()
        self.blockSignals(False)


class CropStudioTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.training_resolution = DEFAULT_TRAINING_RESOLUTION
        self.input_dir:  Optional[str] = None
        self.output_dir: Optional[str] = None
        self.images:     List[str]     = []
        self.index:      int           = 0
        self.current_image_path: Optional[str] = None

        # Instance-level crop types — can be customised at runtime
        import copy
        self.active_crop_types = copy.deepcopy(CROP_TYPES)
        self.current_crop_type = self.active_crop_types[0]

        self.pose = PoseDetector()
        self.canvas = ImageCanvas()
        self.canvas._quality_callback = self.update_crop_quality

        # Per-image completed state memory: {image_path: set of crop_type.key}
        self._completed_map: dict = {}
        # Track which images auto-advance has already fired for
        self._advanced_for: set = set()

        self._build_ui()
        self._build_auto_state()
        self.apply_mode_ui()

    # ──────────────────────────────────────────────
    # UI BUILD
    # ──────────────────────────────────────────────
    def _build_ui(self):
        # ── Folder controls ──
        from PySide6.QtWidgets import QSizePolicy as SP
        self.input_label  = QLabel("Input: (not set)")
        self.output_label = QLabel("Output: (not set)")
        self.input_label.setWordWrap(False)
        self.output_label.setWordWrap(False)
        self.input_label.setFixedHeight(20)
        self.output_label.setFixedHeight(20)
        self.input_label.setSizePolicy(SP.Ignored, SP.Fixed)
        self.output_label.setSizePolicy(SP.Ignored, SP.Fixed)
        self.btn_input  = QPushButton("Select Input Folder")
        self.btn_output = QPushButton("Select Output Folder")
        self.btn_input.clicked.connect(self.pick_input_folder)
        self.btn_output.clicked.connect(self.pick_output_folder)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["Keep original", "PNG", "JPG"])
        self.format_combo.setFocusPolicy(Qt.ClickFocus)
        self.format_combo.activated.connect(lambda: self.window().setFocus())
        self.auto_advance   = QCheckBox("Auto-advance after all crops complete")
        self.use_subfolders = QCheckBox("Auto-create subfolders per crop type")
        self.use_subfolders.setChecked(True)

        self.status_label = QLabel("No images loaded.")
        self.status_label.setStyleSheet("color: #EAEAEA;")
        self.status_label.setFixedHeight(20)
        self.status_label.setWordWrap(False)
        self.status_label.setSizePolicy(SP.Ignored, SP.Fixed)

        # ── Tile buttons built in _build_left_widget ──
        self.tile_buttons: List[CropTile] = []
        self.tile_group = QButtonGroup(self)

        # ── Signal strength ──
        self.signal_title = QLabel("Framing Signal Strength")
        self.signal_title.setAlignment(Qt.AlignCenter)
        self.signal_title.setStyleSheet("font-weight: bold;")
        self.signal_title.setToolTip(
            "Upscale factor = training_target / shortest_side.\n"
            "Lower upscale = clearer signal for training."
        )
        self.quality_indicator = QLabel()
        self.quality_indicator.setFixedSize(40, 40)
        self.quality_indicator.setStyleSheet("background-color: gray; border-radius: 20px;")
        self.dimension_label = QLabel("—")
        self.dimension_label.setAlignment(Qt.AlignCenter)
        self.dimension_label.setWordWrap(True)
        self.dimension_label.setFixedWidth(220)
        self.dimension_label.setFixedHeight(52)

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
        self.manual_mode_cb.stateChanged.connect(self.on_mode_toggled)
        self.auto_mode_cb.stateChanged.connect(self.on_mode_toggled)

        # ── Auto buttons ──
        btn_style = """
            QPushButton {
                font-weight: bold; font-size: 15px;
                border-radius: 6px; border: 2px solid #555;
                background-color: #3a3a3a;
            }
            QPushButton:hover   { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #5a5a5a; }
            QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
        """
        self._stop_style_idle   = btn_style
        self._stop_style_active = """
            QPushButton {
                background-color: #cc2200; color: white;
                font-weight: bold; font-size: 15px;
                border-radius: 6px; border: 2px solid #ff4422;
            }
            QPushButton:hover { background-color: #dd3311; }
        """
        self.auto_start_btn = QPushButton("Start Cropping")
        self.auto_start_btn.setMinimumHeight(60)
        self.auto_start_btn.setStyleSheet(btn_style)
        self.auto_start_btn.clicked.connect(self.start_auto_cropping)

        self._stop_requested = False
        self.auto_stop_btn = QPushButton("Stop Cropping")
        self.auto_stop_btn.setMinimumHeight(60)
        self.auto_stop_btn.setEnabled(False)
        self.auto_stop_btn.setStyleSheet(self._stop_style_idle)
        self.auto_stop_btn.clicked.connect(self.request_stop_cropping)

        self.auto_progress_text = QLabel("0 / 0")
        self.auto_progress_text.setAlignment(Qt.AlignCenter)
        self.auto_progress_text.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.auto_progress = QProgressBar()
        self.auto_progress.setMinimum(0)
        self.auto_progress.setValue(0)
        self.auto_progress.setMinimumHeight(22)
        self.auto_eta_label = QLabel("ETA: —")
        self.auto_eta_label.setAlignment(Qt.AlignCenter)
        self.auto_eta_label.setStyleSheet("font-size: 15px;")

        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(250)
        self.auto_timer.timeout.connect(self._tick_eta_countdown)

        # ── Nav buttons ──
        self.btn_prev   = QPushButton("◀ Prev (Q)")
        self.btn_cancel = QPushButton("Cancel Crop (Esc)")
        self.btn_save   = QPushButton("Save Crop (S)")
        self.btn_next   = QPushButton("Next ▶ (W)")
        self.btn_prev.clicked.connect(self.prev_image)
        self.btn_next.clicked.connect(self.next_image)
        self.btn_cancel.clicked.connect(self.canvas.clear_selection)
        self.btn_save.clicked.connect(self.save_crop)

        # ── Nav layout ──
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


        # ── Left panel — permanent, never rebuilt ──
        # Tile container has a FIXED height forever. Buttons resize to fill it.
        MAX_TILES = 8
        self._all_tiles: List[CropTile] = []
        self._tile_layout = QVBoxLayout()
        self._tile_layout.setContentsMargins(0, 0, 6, 0)
        self._tile_layout.setSpacing(4)

        from core.config import CropType as CT
        from PySide6.QtGui import QColor as QC
        placeholder = CT("__placeholder__", "", "", QC(0,0,0), True)
        padded = list(self.active_crop_types) + [placeholder] * (MAX_TILES - len(self.active_crop_types))

        for i, ct in enumerate(padded):
            tile = CropTile(ct)
            tile.setFixedHeight(60)
            if i < len(self.active_crop_types):
                if i == 0:
                    tile.setChecked(True)
                    self.canvas.set_crop_color(ct.color)
                tile.clicked.connect(self.handle_tile_click)
                self.tile_group.addButton(tile, i)
                self.tile_buttons.append(tile)
            else:
                tile.hide()
            self._tile_layout.addWidget(tile)
            self._all_tiles.append(tile)

        self.tile_container = QWidget()
        self.tile_container.setLayout(self._tile_layout)
        self.tile_container.setFixedHeight(280)

        self.manual_section = QWidget()
        ml = QVBoxLayout(self.manual_section)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(self.tile_container)
        ml.addSpacing(14)
        ml.addWidget(self.signal_title)
        ml.addWidget(self.quality_indicator, alignment=Qt.AlignCenter)
        ml.addWidget(self.dimension_label)
        ml.addSpacing(10)
        ml.addWidget(self.training_target_label)
        ml.addWidget(self.training_target_combo)
        ml.addWidget(self.custom_training_input)

        self.auto_section = QWidget()
        al = QVBoxLayout(self.auto_section)
        al.setContentsMargins(0, 0, 0, 0)
        al.addWidget(self.auto_start_btn)
        al.addSpacing(6)
        al.addWidget(self.auto_stop_btn)
        al.addSpacing(10)
        al.addWidget(self.auto_progress_text)
        al.addWidget(self.auto_progress)
        al.addSpacing(6)
        al.addWidget(self.auto_eta_label)
        al.addStretch(1)
        self.auto_section.hide()

        left_panel = QVBoxLayout()
        left_panel.addWidget(self.manual_section)
        left_panel.addWidget(self.auto_section)
        left_panel.addStretch(1)
        left_panel.addWidget(self.manual_mode_cb)
        left_panel.addWidget(self.auto_mode_cb)
        left_panel.addSpacing(8)

        self.left_widget = QWidget()
        self.left_widget.setLayout(left_panel)
        self.left_widget.setFixedWidth(220)

        center_panel = QVBoxLayout()
        center_panel.addWidget(self.canvas, stretch=1)

        right_panel = QVBoxLayout()
        right_panel.addWidget(self.status_label)
        right_panel.addSpacing(8)
        right_panel.addLayout(nav_layout)
        right_panel.addStretch(1)

        folder_container = QWidget()
        folder_layout = QVBoxLayout(folder_container)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.addWidget(self.btn_input)
        folder_layout.addWidget(self.input_label)
        folder_layout.addSpacing(6)
        folder_layout.addWidget(self.btn_output)
        folder_layout.addWidget(self.output_label)
        right_panel.addWidget(folder_container)
        right_panel.addSpacing(8)

        self.btn_adv_settings = QPushButton("Advanced Crop Settings")
        self.btn_adv_settings.setStyleSheet("""
            QPushButton {
                font-size: 13px; font-weight: bold;
                background-color: #2e2e2e; border: 1px solid #555;
                border-radius: 4px; padding: 8px;
            }
            QPushButton:hover { background-color: #3a3a3a; }
        """)
        self.btn_adv_settings.clicked.connect(self.open_advanced_settings)
        right_panel.addWidget(self.btn_adv_settings)

        self.root_layout = QHBoxLayout(self)
        self.root_layout.setSizeConstraint(QHBoxLayout.SetNoConstraint)
        self.root_layout.addWidget(self.left_widget)
        self.root_layout.addLayout(center_panel, 5)
        self.root_layout.addLayout(right_panel, 2)

    def _rebuild_tiles(self):
        """Update tile buttons in-place. Container is fixed height — tiles resize to fill it."""
        for tile in self.tile_buttons:
            self.tile_group.removeButton(tile)
        self.tile_group = QButtonGroup(self)
        self.tile_group.setExclusive(True)
        self.tile_buttons = []

        tile_count = len(self.active_crop_types)
        CONTAINER_H = 280
        SPACING = 4
        tile_height = (CONTAINER_H - SPACING * (tile_count - 1)) // tile_count
        self.tile_container.setFixedHeight(CONTAINER_H)

        for i, tile in enumerate(self._all_tiles):
            if i < tile_count:
                ct = self.active_crop_types[i]
                tile.crop_type = ct
                tile.completed = False
                tile.setText(ct.label)
                tile.setMinimumHeight(tile_height)
                tile.setMaximumHeight(tile_height)
                tile.setChecked(i == 0)
                tile.update_style()
                tile.show()
                try:
                    tile.clicked.disconnect()
                except RuntimeError:
                    pass
                tile.clicked.connect(self.handle_tile_click)
                self.tile_group.addButton(tile, i)
                self.tile_buttons.append(tile)
                if i == 0:
                    self.canvas.set_crop_color(ct.color)
            else:
                tile.hide()

        self.current_crop_type = self.active_crop_types[0]
        self._completed_map.clear()
        self._advanced_for.clear()
        self.apply_mode_ui()

    def _build_auto_state(self):
        self.auto_current_index    = 0
        self.auto_boxes            = None
        self.auto_step             = 0
        self.auto_running          = False
        self.auto_completed_images = 0
        self.auto_eta_locked       = False
        self.auto_remaining_secs   = 0.0
        self.auto_start_time: Optional[float] = None

        self.auto_anim_timer = QTimer(self)
        self.auto_anim_timer.timeout.connect(self.auto_step_forward)

    # ──────────────────────────────────────────────
    # MODE UI
    # ──────────────────────────────────────────────
    def on_mode_toggled(self):
        sender = self.sender()
        if self.manual_mode_cb.isChecked() and self.auto_mode_cb.isChecked():
            if sender == self.manual_mode_cb:
                self.auto_mode_cb.setChecked(False)
            else:
                self.manual_mode_cb.setChecked(False)
        if not self.manual_mode_cb.isChecked() and not self.auto_mode_cb.isChecked():
            self.manual_mode_cb.setChecked(True)

        # Warn once if switching to auto with custom crop types present
        if self.auto_mode_cb.isChecked() and self.sender() == self.auto_mode_cb:
            has_custom = any(not ct.is_default for ct in self.active_crop_types)
            if has_custom:
                QMessageBox.information(
                    self, "Auto Mode — Default Crops Only",
                    "Auto mode only runs on the four default crop types "
                    "(Face, Torso Up, Thigh Up, Full Body).\n\n"
                    "Your custom crop buttons won't be included in the "
                    "automatic cropping sequence, but their colors will "
                    "still appear when saving manually."
                )

        self.apply_mode_ui()

    # ──────────────────────────────────────────────
    # ADVANCED CROP SETTINGS
    # ──────────────────────────────────────────────
    def open_advanced_settings(self):
        dlg = AdvancedCropSettingsDialog(self.active_crop_types, parent=self)
        result = dlg.exec()
        QApplication.processEvents()
        self.window().activateWindow()
        self.window().raise_()
        if result and dlg.result_types:
            self.active_crop_types = dlg.result_types
            self.current_crop_type = self.active_crop_types[0]
            self._rebuild_tiles()

    def apply_mode_ui(self):
        if self.manual_mode_cb.isChecked():
            self.manual_section.show()
            self.auto_section.hide()
            self.canvas.set_interaction_enabled(True)
            self.update_crop_quality()
            # Restore auto-advance checkbox to user control
            self.auto_advance.setEnabled(True)
            self.auto_advance.setStyleSheet("")
        else:
            self.manual_section.hide()
            self.auto_section.show()
            self.canvas.set_interaction_enabled(False)
            self.canvas.clear_selection()
            # In auto mode, advance is always on and cannot be turned off
            self.auto_advance.setChecked(True)
            self.auto_advance.setEnabled(False)
            self.auto_advance.setStyleSheet("""
                QCheckBox { color: #aaa; }
                QCheckBox::indicator { border: 1px solid #444; background-color: #1a1a1a; }
                QCheckBox::indicator:checked { background-color: #444; border: 1px solid #555; }
            """)

    # ──────────────────────────────────────────────
    # NAV LOCK
    # ──────────────────────────────────────────────
    def _set_nav_locked(self, locked: bool):
        for btn in (self.btn_prev, self.btn_next, self.btn_save, self.btn_cancel):
            btn.setEnabled(not locked)
            if locked:
                btn.setStyleSheet("background-color: #222; color: #555; border: 1px solid #333; padding: 6px;")
            else:
                btn.setStyleSheet("")

    # ──────────────────────────────────────────────
    # ETA TICK
    # ──────────────────────────────────────────────
    def _tick_eta_countdown(self):
        if not self.auto_running:
            return
        elapsed  = time.perf_counter() - self._eta_start_time
        remaining = max(0.0, self._eta_total_secs - elapsed)
        mins = int(remaining) // 60
        secs = int(remaining) % 60
        self.auto_eta_label.setText(f"ETA: {mins:02d}:{secs:02d}")

    # ──────────────────────────────────────────────
    # STOP
    # ──────────────────────────────────────────────
    def request_stop_cropping(self):
        self._stop_requested = True
        self.auto_stop_btn.setText("Stopping…")
        self.auto_stop_btn.setStyleSheet(self._stop_style_active)
        self.auto_stop_btn.setEnabled(False)

    def _finish_auto_run(self, completed: bool):
        self.auto_running    = False
        self._stop_requested = False
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
        self.auto_eta_locked       = True
        self.auto_remaining_secs   = 0.0

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

        # Silent timing pass across entire dataset
        t0 = time.perf_counter()
        valid_count = 0
        for path in self.images:
            self.pose.compute_sequential_boxes(path)
            valid_count += 1
            QApplication.processEvents()
        total_detect_time = time.perf_counter() - t0

        anim_and_save_overhead = 1.5  # seconds per image
        avg_per_image              = (total_detect_time / max(valid_count, 1)) + anim_and_save_overhead
        self.auto_remaining_secs   = avg_per_image * total
        self._eta_total_secs       = self.auto_remaining_secs
        self._eta_start_time       = time.perf_counter()

        mins = int(self.auto_remaining_secs) // 60
        secs = int(self.auto_remaining_secs) % 60
        self.auto_eta_label.setText(f"ETA: {mins:02d}:{secs:02d}")
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

        image_path = self.images[self.auto_current_index]
        self.index = self.auto_current_index
        self.show_image_at_index()

        boxes = self.pose.compute_sequential_boxes(image_path)
        if not boxes:
            self.auto_current_index += 1
            self.auto_progress.setValue(self.auto_current_index)
            self.auto_progress_text.setText(f"{self.auto_current_index} / {len(self.images)}")
            QApplication.processEvents()
            self.process_next_image()
            return

        self.auto_boxes = boxes
        self.auto_step  = 0
        self.auto_anim_timer.start(200)

    def auto_step_forward(self):
        crop_order = ["fullbody", "thigh", "torso", "face"]
        if self.auto_step >= len(crop_order):
            self.auto_anim_timer.stop()
            self.save_auto_crops(self.images[self.auto_current_index])
            self.auto_completed_images += 1
            self.auto_current_index    += 1
            self.auto_progress.setValue(self.auto_current_index)
            self.auto_progress_text.setText(f"{self.auto_current_index} / {len(self.images)}")
            QApplication.processEvents()
            self.process_next_image()
            return

        crop_key = crop_order[self.auto_step]
        for ct in CROP_TYPES:
            if ct.key == crop_key:
                self.canvas.set_crop_color(ct.color)
                break
        self.show_overlay_box(self.auto_boxes[crop_key])
        self.auto_step += 1

    # ──────────────────────────────────────────────
    # OVERLAY + SAVE
    # ──────────────────────────────────────────────
    def show_overlay_box(self, box):
        left, top, right, bottom = box
        ow, oh = self.canvas._img_size_px
        if not ow or not oh:
            return
        self.canvas.set_overlay_box_normalized(
            left / ow, top / oh, right / ow, bottom / oh
        )

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
        files = sorted(
            [os.path.join(self.input_dir, f) for f in os.listdir(self.input_dir)
             if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS],
            key=lambda p: os.path.basename(p).lower()
        )
        self.images = files
        self.index  = 0
        self._completed_map = {}
        self._advanced_for  = set()
        if not self.images:
            self.current_image_path = None
            self.canvas.set_image(QPixmap(), (1, 1))
            self.status_label.setText("No supported images found.")
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

        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        pm = QPixmap()
        pm.loadFromData(buf.getvalue(), "PNG")

        # Scale pixmap to fit canvas so Qt never uses native image size for layout
        pm = pm.scaled(640, 540, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.canvas.set_image(pm, (ow, oh))
        self.status_label.setText(
            f"Image {self.index + 1}/{len(self.images)} — {os.path.basename(path)} ({ow}×{oh})"
        )
        # Restore per-image completed state from memory
        completed_keys = self._completed_map.get(path, set())
        for b in self.tile_buttons:
            b.mark_completed(b.crop_type.key in completed_keys)
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
            QMessageBox.warning(self, "No crop", "Draw a crop rectangle first.")
            return

        src_path = self.current_image_path
        base     = os.path.splitext(os.path.basename(src_path))[0]
        src_ext  = os.path.splitext(src_path)[1].lower()

        fmt = self.format_combo.currentText()
        if fmt == "Keep original":
            out_ext    = src_ext
            out_format = "PNG" if out_ext == ".png" else "JPEG"
        elif fmt == "PNG":
            out_ext, out_format = ".png", "PNG"
        else:
            out_ext, out_format = ".jpg", "JPEG"

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
            if out_format == "JPEG" and cropped.mode not in ("RGB", "L"):
                cropped = cropped.convert("RGB")
            kwargs = {"quality": 95, "subsampling": 0, "optimize": True} if out_format == "JPEG" else {"optimize": True}

            # Collision avoidance — find a free filename
            if os.path.exists(out_path):
                stem   = os.path.splitext(out_name)[0]
                folder = os.path.dirname(out_path)
                i = 2
                while True:
                    candidate = os.path.join(folder, f"{stem}_{i}{out_ext}")
                    if not os.path.exists(candidate):
                        out_path = candidate
                        break
                    i += 1

            cropped.save(out_path, format=out_format, **kwargs)

            for b in self.tile_buttons:
                if b.crop_type == self.current_crop_type:
                    b.mark_completed(True)

            # Persist completed state for this image
            path = self.current_image_path
            if path not in self._completed_map:
                self._completed_map[path] = set()
            self._completed_map[path].add(self.current_crop_type.key)

        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return

        self.canvas.clear_selection()

        # Auto-advance only when every crop tile is marked done,
        # and only once per image — never re-fires if you go back
        if self.auto_advance.isChecked():
            all_done = all(b.completed for b in self.tile_buttons)
            path     = self.current_image_path
            if all_done and path not in self._advanced_for:
                self._advanced_for.add(path)
                self.next_image()

    # ──────────────────────────────────────────────
    # CROP TYPE + SIGNAL STRENGTH
    # ──────────────────────────────────────────────
    def handle_tile_click(self):
        idx = self.tile_group.id(self.sender())
        self.current_crop_type = self.active_crop_types[idx]
        self.canvas.set_crop_color(self.current_crop_type.color)
        for b in self.tile_buttons:
            b.blockSignals(True)
            b.update_style()
            b.blockSignals(False)
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
        target   = max(1, int(self.training_resolution))
        upscale  = target / shortest
        color    = ("#00ff00" if upscale <= 1.70 else
                    "#ffd000" if upscale <= 2.50 else
                    "#ff8800" if upscale <= 3.50 else "#ff0000")
        self.quality_indicator.setStyleSheet(f"background-color: {color}; border-radius: 20px;")
        self.dimension_label.setText(f"{width} × {height}\nUpscale → {upscale:.2f}×  (to {target}px)")

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
        if text.strip().isdigit():
            val = int(text.strip())
            if val >= 64:
                self.training_resolution = val
                self.update_crop_quality()

    # ──────────────────────────────────────────────
    # KEYBINDS (forwarded from main window)
    # ──────────────────────────────────────────────
    def handle_key(self, key) -> bool:
        from PySide6.QtCore import Qt as _Qt
        if key == _Qt.Key_1: self.select_crop_type(0); return True
        if key == _Qt.Key_2: self.select_crop_type(1); return True
        if key == _Qt.Key_3: self.select_crop_type(2); return True
        if key == _Qt.Key_4: self.select_crop_type(3); return True
        if key == _Qt.Key_5 and len(self.active_crop_types) > 4: self.select_crop_type(4); return True
        if key == _Qt.Key_6 and len(self.active_crop_types) > 5: self.select_crop_type(5); return True
        if key == _Qt.Key_7 and len(self.active_crop_types) > 6: self.select_crop_type(6); return True
        if key == _Qt.Key_8 and len(self.active_crop_types) > 7: self.select_crop_type(7); return True
        if key == _Qt.Key_Q: self.prev_image();              return True
        if key == _Qt.Key_W: self.next_image();              return True
        if key == _Qt.Key_S: self.save_crop();               return True
        if key == _Qt.Key_Escape: self.canvas.clear_selection(); return True
        return False

    def select_crop_type(self, idx: int):
        if 0 <= idx < len(self.tile_buttons):
            self.tile_buttons[idx].setChecked(True)
            self.current_crop_type = self.active_crop_types[idx]
            self.canvas.set_crop_color(self.current_crop_type.color)
            for b in self.tile_buttons:
                b.update_style()
            self.update_crop_quality()