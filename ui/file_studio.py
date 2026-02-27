import os
from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QProgressBar, QFileDialog,
    QMessageBox, QApplication, QFrame,
)


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg"}

BTN_STYLE = """
    QPushButton {
        font-weight: bold; font-size: 15px;
        border-radius: 6px; border: 2px solid #555;
        background-color: #3a3a3a;
        min-height: 60px;
    }
    QPushButton:hover   { background-color: #4a4a4a; }
    QPushButton:pressed { background-color: #5a5a5a; }
    QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
"""

STOP_STYLE_ACTIVE = """
    QPushButton {
        background-color: #cc2200; color: white;
        font-weight: bold; font-size: 15px;
        border-radius: 6px; border: 2px solid #ff4422;
        min-height: 60px;
    }
    QPushButton:hover { background-color: #dd3311; }
"""


def _divider():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color: #444;")
    return line


class FileStudioTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path:    Optional[str] = None
        self._stop_requested = False
        self._build_ui()

    # ──────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)

        # ── Left panel — controls ──
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignTop)

        # Folder picker
        self.folder_label = QLabel("Folder: (not set)")
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet("color: #aaa;")
        self.btn_folder = QPushButton("Select Folder")
        self.btn_folder.clicked.connect(self.pick_folder)
        left.addWidget(self.btn_folder)
        left.addWidget(self.folder_label)
        left.addSpacing(16)
        left.addWidget(_divider())
        left.addSpacing(16)

        # Base name input
        left.addWidget(QLabel("Base name (prefix):"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g.  face  →  face_1, face_2 …")
        left.addWidget(self.name_input)
        left.addSpacing(12)

        # Format picker
        left.addWidget(QLabel("Output format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Keep original", "PNG", "JPG"])
        left.addWidget(self.format_combo)
        left.addSpacing(12)

        # Options
        self.cb_captions = QCheckBox("Generate blank caption (.txt) files")
        self.cb_captions.setChecked(True)
        left.addWidget(self.cb_captions)
        left.addSpacing(20)
        left.addWidget(_divider())
        left.addSpacing(16)

        # Start / Stop
        self.btn_start = QPushButton("Start Renaming")
        self.btn_start.setStyleSheet(BTN_STYLE)
        self.btn_start.clicked.connect(self.start_renaming)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setStyleSheet(BTN_STYLE)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.request_stop)
        left.addWidget(self.btn_start)
        left.addSpacing(6)
        left.addWidget(self.btn_stop)
        left.addSpacing(16)

        # Progress
        self.progress_label = QLabel("0 / 0")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(22)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #aaa; font-size: 13px;")
        left.addWidget(self.progress_label)
        left.addWidget(self.progress_bar)
        left.addSpacing(6)
        left.addWidget(self.status_label)
        left.addStretch(1)

        # ── Right panel — info ──
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignTop)
        right.addSpacing(16)

        info_title = QLabel("How it works")
        info_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        right.addWidget(info_title)
        right.addSpacing(8)

        info = QLabel(
            "1. Select a folder containing images.\n\n"
            "2. Enter a base name — all images will be renamed\n"
            "    to  basename_1, basename_2, etc.\n\n"
            "3. Choose an output format, or keep originals.\n\n"
            "4. Optionally generate blank .txt caption files\n"
            "    alongside each renamed image.\n\n"
            "5. Re-run on a folder to close gaps after deletions.\n"
            "    Enable 'Rename existing captions' to keep them\n"
            "    paired with their images.\n\n"
            "Files are renamed in place — nothing is deleted."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaa; font-size: 13px;")
        right.addWidget(info)
        right.addStretch(1)

        root.addLayout(left,  2)
        root.addSpacing(32)
        root.addLayout(right, 1)

    # ──────────────────────────────────────────────
    # FOLDER PICKER
    # ──────────────────────────────────────────────
    def pick_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not directory:
            return
        self.folder_path = directory
        self.folder_label.setText(f"Folder: {directory}")
        self.folder_label.setStyleSheet("color: #e0e0e0;")
        images = self._get_images()
        self.progress_label.setText(f"0 / {len(images)}")
        self.progress_bar.setMaximum(max(len(images), 1))
        self.progress_bar.setValue(0)
        self.status_label.setText(f"{len(images)} image(s) found.")

    def _get_images(self) -> List[str]:
        if not self.folder_path:
            return []
        files = [
            os.path.join(self.folder_path, f)
            for f in os.listdir(self.folder_path)
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
        ]
        return sorted(files, key=lambda p: os.path.basename(p).lower())

    # ──────────────────────────────────────────────
    # STOP
    # ──────────────────────────────────────────────
    def request_stop(self):
        self._stop_requested = True
        self.btn_stop.setText("Stopping…")
        self.btn_stop.setStyleSheet(STOP_STYLE_ACTIVE)
        self.btn_stop.setEnabled(False)

    def _finish(self, completed: bool, count: int):
        self._stop_requested = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText("Stop")
        self.btn_stop.setStyleSheet(BTN_STYLE)
        if completed:
            self.status_label.setText(f"Done — {count} file(s) renamed.")
        else:
            self.status_label.setText(f"Stopped — {count} file(s) renamed before stopping.")
            self.progress_bar.setValue(0)
            self.progress_label.setText("0 / 0")

    # ──────────────────────────────────────────────
    # RENAME
    # ──────────────────────────────────────────────
    def start_renaming(self):
        if not self.folder_path:
            QMessageBox.warning(self, "No folder", "Select a folder first.")
            return
        base_name = self.name_input.text().strip()
        if not base_name:
            QMessageBox.warning(self, "No name", "Enter a base name first.")
            return
        images = self._get_images()
        if not images:
            QMessageBox.warning(self, "No images", "No supported images found in that folder.")
            return

        self._stop_requested = False
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_stop.setText("Stop")
        self.btn_stop.setStyleSheet(BTN_STYLE)

        total = len(images)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"0 / {total}")
        self.status_label.setText("Renaming…")
        QApplication.processEvents()

        fmt      = self.format_combo.currentText()
        gen_caps = self.cb_captions.isChecked()

        # ── Pass 1: rename everything to temp names to avoid collisions ──
        # This handles the gap-closing case where e.g. face_5 already exists
        # and would collide before it gets renamed.
        temp_map = {}
        for i, src_path in enumerate(images):
            if self._stop_requested:
                self._finish(completed=False, count=i)
                return

            src_ext = os.path.splitext(src_path)[1].lower()
            out_ext = ".png" if fmt == "PNG" else ".jpg" if fmt == "JPG" else src_ext

            temp_path = os.path.join(self.folder_path, f"__tmp_{i}{out_ext}")

            if fmt == "Keep original" or src_ext == out_ext:
                os.rename(src_path, temp_path)
            else:
                try:
                    from PIL import Image, ImageOps
                    pil = Image.open(src_path)
                    pil = ImageOps.exif_transpose(pil)
                    if fmt == "JPG" and pil.mode not in ("RGB", "L"):
                        pil = pil.convert("RGB")
                    pil.save(temp_path)
                    os.remove(src_path)
                except Exception as e:
                    print(f"Convert failed for {src_path}: {e}")
                    continue

            # Always temp-rename matching caption file if it exists
            cap_src = os.path.splitext(src_path)[0] + ".txt"
            if os.path.exists(cap_src):
                os.rename(cap_src, os.path.join(self.folder_path, f"__tmp_{i}.txt"))

            temp_map[i] = (temp_path, out_ext, src_path)
            QApplication.processEvents()

        # ── Pass 2: rename temp files to final names ──
        for i, (temp_path, out_ext, orig_path) in temp_map.items():
            if self._stop_requested:
                self._finish(completed=False, count=i)
                return

            # Preserve _C suffix if original was a cropped file from Crop Studio
            orig_stem = os.path.splitext(os.path.basename(orig_path))[0]
            crop_suffix = "_C" if orig_stem.endswith("_C") else ""

            final_name = f"{base_name}_{i + 1}{crop_suffix}{out_ext}"
            final_path = os.path.join(self.folder_path, final_name)
            os.rename(temp_path, final_path)

            # Rename caption temp to final
            cap_tmp = os.path.join(self.folder_path, f"__tmp_{i}.txt")
            if os.path.exists(cap_tmp):
                os.rename(cap_tmp, os.path.join(self.folder_path, f"{base_name}_{i + 1}{crop_suffix}.txt"))

            # Generate blank caption if requested and not already present
            if gen_caps:
                cap_path = os.path.join(self.folder_path, f"{base_name}_{i + 1}{crop_suffix}.txt")
                if not os.path.exists(cap_path):
                    open(cap_path, "w").close()

            self.progress_bar.setValue(i + 1)
            self.progress_label.setText(f"{i + 1} / {len(temp_map)}")
            QApplication.processEvents()

        self._finish(completed=True, count=len(temp_map))