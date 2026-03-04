import os
import shutil
from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFileDialog, QMessageBox, QApplication,
    QFrame, QProgressBar,
)

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg"}

TIERS = [
    ("Good",    "good",    "#00ff00", 1.70),
    ("Okay",    "okay",    "#ffd000", 2.50),
    ("Risky",   "risky",   "#ff8800", 3.50),
    ("Discard", "discard", "#ff3333", float("inf")),
]

CROP_FOLDERS = {"face", "thigh", "torso", "fullbody"}

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

BTN_RUN_NORMAL = """
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

BTN_RUN_CROPPED = """
    QPushButton {
        font-weight: bold; font-size: 15px;
        border-radius: 6px; border: 2px solid #00cc44;
        background-color: #1a3a22;
        color: #00ff66;
        min-height: 60px;
    }
    QPushButton:hover   { background-color: #1f4a2a; }
    QPushButton:pressed { background-color: #256030; }
    QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
"""

BTN_CONTINUE = """
    QPushButton {
        font-weight: bold; font-size: 15px;
        border-radius: 6px; border: 2px solid #00cc44;
        background-color: #00aa33;
        color: white;
        min-height: 60px;
    }
    QPushButton:hover   { background-color: #00bb44; }
    QPushButton:pressed { background-color: #00cc55; }
"""


def _divider():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color: #444;")
    return line


def _get_tier(upscale: float):
    for label, folder, color, max_up in TIERS:
        if upscale <= max_up:
            return label, folder, color
    return TIERS[-1][0], TIERS[-1][1], TIERS[-1][2]


def _compute_grade(counts: dict, total: int) -> tuple:
    if total == 0:
        return "?", "#888", "No images scanned."
    good    = counts.get("Good",    0) / total
    okay    = counts.get("Okay",    0) / total
    risky   = counts.get("Risky",   0) / total
    discard = counts.get("Discard", 0) / total
    clean       = good + okay
    risky_total = risky + discard
    if good >= 0.75:
        return "A+", "#00ff00", "Excellent dataset. Mostly ideal images."
    elif good >= 0.50 and clean >= 0.80:
        return "A",  "#00ff00", "Great dataset. Strong signal across the board."
    elif clean >= 0.75 and discard < 0.05:
        return "B+", "#aaff00", "Good dataset. Mostly usable images."
    elif clean >= 0.60 and discard < 0.10:
        return "B",  "#ffd000", "Decent dataset. A few images worth reviewing."
    elif clean >= 0.40 and risky_total < 0.50:
        return "C",  "#ffd000", "Average dataset. Consider replacing weaker images."
    elif clean >= 0.25 or discard < 0.50:
        return "D",  "#ff8800", "Weak dataset. Many images will hurt training quality."
    else:
        return "F",  "#ff3333", "Poor dataset. Rebuilding the image set is strongly recommended."


def _has_crop_subfolders(path: str) -> bool:
    return any(os.path.isdir(os.path.join(path, f)) for f in CROP_FOLDERS)


def _has_tier_subfolders(path: str) -> bool:
    tier_folders = [f for _, f, _, _ in TIERS]
    return any(os.path.isdir(os.path.join(path, f)) for f in tier_folders)


def _collect_images_from_subfolders(path: str, folders: set) -> List[str]:
    """Collect all images from named subfolders."""
    images = []
    for folder_name in folders:
        sub = os.path.join(path, folder_name)
        if not os.path.isdir(sub):
            continue
        for f in os.listdir(sub):
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS:
                images.append(os.path.join(sub, f))
    return sorted(images, key=lambda p: os.path.basename(p).lower())


class SignalCheckerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path:    Optional[str]  = None
        self._cropped_mode:  bool           = False
        self._awaiting_continue: bool       = False  # True after phase 1 in cropped mode
        self._last_counts:   dict           = {}
        self._last_total:    int            = 0
        self._build_ui()

    # ──────────────────────────────────────────────
    # UI BUILD
    # ──────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)

        # ── Left panel ──
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignTop)

        # Mode toggle row — dot + button + organize checkbox on same line
        mode_row = QHBoxLayout()
        self._mode_dot = QLabel("●")
        self._mode_dot.setStyleSheet("color: #444; font-size: 22px;")
        self._mode_dot.setFixedWidth(28)
        self._mode_btn = QPushButton("Cropped Image Mode")
        self._mode_btn.setCheckable(False)
        self._mode_btn.setStyleSheet("""
            QPushButton {
                font-size: 13px; font-weight: bold;
                background-color: #2e2e2e; border: 1px solid #444;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background-color: #383838; }
        """)
        self._mode_btn.setFocusPolicy(Qt.ClickFocus)
        self._mode_btn.clicked.connect(self._toggle_cropped_mode)
        from PySide6.QtWidgets import QCheckBox
        self._cb_organize = QCheckBox("Organize by signal strength")
        self._cb_organize.setChecked(True)
        mode_row.addWidget(self._mode_dot)
        mode_row.addWidget(self._mode_btn)
        mode_row.addSpacing(16)
        mode_row.addWidget(self._cb_organize)
        mode_row.addStretch(1)
        left.addLayout(mode_row)
        left.addSpacing(12)

        # Folder picker
        self.folder_label = QLabel("Folder: (not set)")
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet("color: #aaa;")
        self.btn_folder = QPushButton("Select Image Folder")
        self.btn_folder.setFocusPolicy(Qt.ClickFocus)
        self.btn_folder.clicked.connect(self.pick_folder)
        left.addWidget(self.btn_folder)
        left.addWidget(self.folder_label)
        left.addSpacing(12)
        left.addWidget(_divider())
        left.addSpacing(12)

        # Training resolution
        left.addWidget(QLabel("Training resolution:"))
        res_row = QHBoxLayout()
        self.res_combo = QComboBox()
        self.res_combo.addItems(["512", "768", "1024", "Custom"])
        self.res_combo.setFocusPolicy(Qt.ClickFocus)
        self.res_combo.currentTextChanged.connect(self._on_res_changed)
        self.custom_res = QLineEdit()
        self.custom_res.setPlaceholderText("e.g. 896")
        self.custom_res.setValidator(QIntValidator(64, 4096))
        self.custom_res.hide()
        res_row.addWidget(self.res_combo)
        res_row.addWidget(self.custom_res)
        left.addLayout(res_row)
        left.addSpacing(12)
        left.addWidget(_divider())
        left.addSpacing(12)

        # Buttons container
        btn_container = QWidget()
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)

        self.btn_run = QPushButton("Run Signal Check")
        self.btn_run.setStyleSheet(BTN_RUN_NORMAL)
        self.btn_run.clicked.connect(self._on_run_clicked)
        btn_layout.addWidget(self.btn_run)

        self.btn_delete_discard = QPushButton("Delete Discard Folder")
        self.btn_delete_discard.setStyleSheet(BTN_STYLE)
        self.btn_delete_discard.setEnabled(False)
        self.btn_delete_discard.clicked.connect(self.delete_discard)
        btn_layout.addWidget(self.btn_delete_discard)

        self.btn_flatten = QPushButton("Flatten Folder")
        self.btn_flatten.setStyleSheet(BTN_STYLE)
        self.btn_flatten.setEnabled(False)
        self.btn_flatten.clicked.connect(self.flatten_folders)
        btn_layout.addWidget(self.btn_flatten)

        left.addWidget(btn_container)
        left.addSpacing(12)

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

        # ── Right panel — results ──
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignTop)
        right.addSpacing(16)

        results_title = QLabel("Results")
        results_title.setStyleSheet("font-weight: bold; font-size: 16px;")
        right.addWidget(results_title)
        right.addSpacing(12)

        self._tier_counts = {}
        for label, folder, color, _ in TIERS:
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 20px;")
            dot.setFixedWidth(28)
            name = QLabel(label)
            name.setStyleSheet("font-size: 14px; font-weight: bold;")
            name.setFixedWidth(80)
            count = QLabel("—")
            count.setStyleSheet("font-size: 14px; color: #ccc;")
            row.addWidget(dot)
            row.addWidget(name)
            row.addWidget(count)
            row.addStretch(1)
            right.addLayout(row)
            right.addSpacing(8)
            self._tier_counts[label] = count

        right.addSpacing(16)
        right.addWidget(_divider())
        right.addSpacing(16)

        grade_title = QLabel("Dataset Grade")
        grade_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        right.addWidget(grade_title)
        right.addSpacing(8)

        grade_row = QHBoxLayout()
        self.grade_letter = QLabel("—")
        self.grade_letter.setStyleSheet("font-size: 52px; font-weight: bold; color: #555;")
        self.grade_letter.setFixedWidth(80)
        self.grade_desc = QLabel("")
        self.grade_desc.setWordWrap(True)
        self.grade_desc.setStyleSheet("color: #aaa; font-size: 13px;")
        grade_row.addWidget(self.grade_letter)
        grade_row.addWidget(self.grade_desc, 1)
        right.addLayout(grade_row)

        right.addSpacing(16)
        right.addWidget(_divider())
        right.addSpacing(16)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #aaa; font-size: 13px;")
        self.summary_label.setWordWrap(True)
        right.addWidget(self.summary_label)
        right.addStretch(1)

        root.addLayout(left,  2)
        root.addSpacing(32)
        root.addLayout(right, 1)

    # ──────────────────────────────────────────────
    # MODE TOGGLE
    # ──────────────────────────────────────────────
    def _toggle_cropped_mode(self):
        self._cropped_mode = not self._cropped_mode
        self._awaiting_continue = False
        if self._cropped_mode:
            self._mode_dot.setStyleSheet("color: #00ff66; font-size: 22px;")
            self.btn_folder.setText("Select Crop Studio Output Folder")
            self.btn_run.setText("Run Cropped Image Signal Check")
            self.btn_run.setStyleSheet(BTN_RUN_CROPPED)
            self._cb_organize.setEnabled(False)
            self._cb_organize.setStyleSheet("""
                QCheckBox { color: #aaa; }
                QCheckBox::indicator { border: 1px solid #444; background-color: #1a1a1a; }
                QCheckBox::indicator:checked { background-color: #444; border: 1px solid #555; }
            """)
        else:
            self._mode_dot.setStyleSheet("color: #444; font-size: 22px;")
            self.btn_folder.setText("Select Image Folder")
            self.btn_run.setText("Run Signal Check")
            self.btn_run.setStyleSheet(BTN_RUN_NORMAL)
            self._cb_organize.setEnabled(True)
            self._cb_organize.setStyleSheet("")
        self.folder_path = None
        self.folder_label.setText("Folder: (not set)")
        self.folder_label.setStyleSheet("color: #aaa;")
        self._reset_results()

    # ──────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────
    def _on_res_changed(self, text):
        self.custom_res.setVisible(text == "Custom")

    def _get_resolution(self) -> Optional[int]:
        text = self.res_combo.currentText()
        if text == "Custom":
            val = self.custom_res.text().strip()
            return int(val) if val.isdigit() and int(val) >= 64 else None
        return int(text)

    def _reset_results(self):
        for w in self._tier_counts.values():
            w.setText("—")
        self.grade_letter.setText("—")
        self.grade_letter.setStyleSheet("font-size: 52px; font-weight: bold; color: #555;")
        self.grade_desc.setText("")
        self.summary_label.setText("")
        self.progress_bar.setValue(0)
        self.progress_label.setText("0 / 0")
        self.status_label.setText("")
        self.btn_delete_discard.setEnabled(False)
        self.btn_flatten.setEnabled(False)

    def _get_images(self) -> List[str]:
        if not self.folder_path:
            return []
        return sorted(
            [os.path.join(self.folder_path, f)
             for f in os.listdir(self.folder_path)
             if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS],
            key=lambda p: os.path.basename(p).lower()
        )

    # ──────────────────────────────────────────────
    # FOLDER PICKER
    # ──────────────────────────────────────────────
    def pick_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not directory:
            return

        # In cropped mode, validate that crop subfolders exist
        if self._cropped_mode:
            if not _has_crop_subfolders(directory):
                QMessageBox.warning(
                    self, "Wrong Folder",
                    "Pick your Crop Studio output folder with the crop type subfolders "
                    "(face, thigh, torso, full)."
                )
                return

        self.folder_path = directory
        self.folder_label.setText(f"Folder: {directory}")
        self.folder_label.setStyleSheet("color: #e0e0e0;")
        self._awaiting_continue = False
        self.btn_run.setText("Run Cropped Image Signal Check" if self._cropped_mode else "Run Signal Check")
        self.btn_run.setStyleSheet(BTN_RUN_CROPPED if self._cropped_mode else BTN_RUN_NORMAL)
        self._reset_results()

        # Enable flatten right away if any subfolders exist
        has_subs = any(
            os.path.isdir(os.path.join(directory, f))
            for f in os.listdir(directory)
        )
        if has_subs:
            self.btn_flatten.setEnabled(True)

        if self._cropped_mode:
            images = _collect_images_from_subfolders(directory, CROP_FOLDERS)
            count  = len(images)
        else:
            images = self._get_images()
            count  = len(images)

        self.progress_bar.setMaximum(max(count, 1))
        self.status_label.setText(f"{count} image(s) found.")
        self.progress_label.setText(f"0 / {count}")

        # Light up buttons if tier or crop subfolders already exist
        tier_folders = [f for _, f, _, _ in TIERS]
        all_known = set(tier_folders) | CROP_FOLDERS
        if any(os.path.isdir(os.path.join(directory, f)) for f in all_known):
            self.btn_flatten.setEnabled(True)
        if os.path.isdir(os.path.join(directory, "discard")):
            self.btn_delete_discard.setEnabled(True)

    # ──────────────────────────────────────────────
    # RUN BUTTON ROUTER
    # ──────────────────────────────────────────────
    def _on_run_clicked(self):
        if self._awaiting_continue:
            self._run_sort_phase()
        elif self._cropped_mode:
            self._run_cropped_phase1()
        else:
            self.run_check()

    # ──────────────────────────────────────────────
    # NORMAL MODE
    # ──────────────────────────────────────────────
    def run_check(self):
        if not self.folder_path:
            QMessageBox.warning(self, "No folder", "Select a folder first.")
            return
        res = self._get_resolution()
        if not res:
            QMessageBox.warning(self, "No resolution", "Enter a valid training resolution.")
            return
        images = self._get_images()
        if not images:
            QMessageBox.warning(self, "No images", "No supported images found.")
            return

        organize = self._cb_organize.isChecked()
        total    = len(images)
        self._scan_and_display(images, res, total, organize=organize, label="analyzed")

        if organize:
            self.btn_delete_discard.setEnabled(True)
            self.btn_flatten.setEnabled(True)

    # ──────────────────────────────────────────────
    # CROPPED MODE — PHASE 1: flatten crop folders + grade
    # ──────────────────────────────────────────────
    def _run_cropped_phase1(self):
        if not self.folder_path:
            QMessageBox.warning(self, "No folder", "Select a folder first.")
            return
        if not _has_crop_subfolders(self.folder_path):
            QMessageBox.warning(
                self, "Wrong Folder",
                "Pick your Crop Studio output folder with the crop type subfolders "
                "(face, thigh, torso, full)."
            )
            return
        res = self._get_resolution()
        if not res:
            QMessageBox.warning(self, "No resolution", "Enter a valid training resolution.")
            return

        # Collect images from crop subfolders
        images = _collect_images_from_subfolders(self.folder_path, CROP_FOLDERS)
        if not images:
            QMessageBox.warning(self, "No images", "No images found in crop subfolders.")
            return

        total = len(images)
        self.status_label.setText("Flattening crop folders and scanning…")
        self.btn_run.setEnabled(False)
        QApplication.processEvents()

        # Flatten crop subfolders into main folder first
        for folder_name in CROP_FOLDERS:
            sub = os.path.join(self.folder_path, folder_name)
            if not os.path.isdir(sub):
                continue
            for fname in os.listdir(sub):
                src  = os.path.join(sub, fname)
                dest = os.path.join(self.folder_path, fname)
                if os.path.exists(dest):
                    base, ext = os.path.splitext(fname)
                    i = 1
                    while os.path.exists(dest):
                        dest = os.path.join(self.folder_path, f"{base}_{i}{ext}")
                        i += 1
                shutil.move(src, dest)
            shutil.rmtree(sub)

        # Re-collect from main folder now that everything is flat
        images = self._get_images()
        total  = len(images)

        # Scan only — no moving yet
        counts = self._scan_and_display(images, res, total, organize=False, label="scanned")
        self._last_counts = counts
        self._last_total  = total

        # Transition to continue state
        self._awaiting_continue = True
        self.btn_run.setText("Continue — Sort into Signal Folders")
        self.btn_run.setStyleSheet(BTN_CONTINUE)
        self.btn_run.setEnabled(True)
        self.status_label.setText("Review the grade above, then click Continue to sort into signal folders.")

    # ──────────────────────────────────────────────
    # CROPPED MODE — PHASE 2: sort into tier folders
    # ──────────────────────────────────────────────
    def _run_sort_phase(self):
        res = self._get_resolution()
        if not res:
            QMessageBox.warning(self, "No resolution", "Enter a valid training resolution.")
            return
        images = self._get_images()
        if not images:
            QMessageBox.warning(self, "No images", "No images found to sort.")
            return

        total = len(images)
        self.btn_run.setEnabled(False)
        self.status_label.setText("Sorting into signal folders…")
        QApplication.processEvents()

        for _, folder, _, _ in TIERS:
            os.makedirs(os.path.join(self.folder_path, folder), exist_ok=True)

        counts = {label: 0 for label, *_ in TIERS}
        errors = 0
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)

        for i, img_path in enumerate(images):
            try:
                from PIL import Image
                with Image.open(img_path) as pil:
                    w, h = pil.size
                upscale          = res / max(min(w, h), 1)
                label, folder, _ = _get_tier(upscale)
                counts[label]   += 1
                dest = os.path.join(self.folder_path, folder, os.path.basename(img_path))
                shutil.move(img_path, dest)
                cap_src = os.path.splitext(img_path)[0] + ".txt"
                if os.path.exists(cap_src):
                    shutil.move(cap_src, os.path.join(self.folder_path, folder, os.path.basename(cap_src)))
            except Exception as e:
                print(f"Sort error on {img_path}: {e}")
                errors += 1

            self.progress_bar.setValue(i + 1)
            self.progress_label.setText(f"{i + 1} / {total}")
            QApplication.processEvents()

        # Update tier counts display
        for label, w in self._tier_counts.items():
            n = counts.get(label, 0)
            w.setText(f"{n} image{'s' if n != 1 else ''}")

        summary = f"Training resolution: {res}px\n{total} image(s) sorted into signal folders."
        if errors:
            summary += f"\n{errors} file(s) could not be processed."
        summary += f"\n\nSubfolders created in:\n{self.folder_path}"
        self.summary_label.setText(summary)
        self.status_label.setText("Done.")

        self._awaiting_continue = False
        self.btn_run.setText("Run Cropped Image Signal Check")
        self.btn_run.setStyleSheet(BTN_RUN_CROPPED)
        self.btn_run.setEnabled(True)
        self.btn_delete_discard.setEnabled(True)
        self.btn_flatten.setEnabled(True)

    # ──────────────────────────────────────────────
    # SHARED SCAN LOGIC
    # ──────────────────────────────────────────────
    def _scan_and_display(self, images: List[str], res: int, total: int,
                          organize: bool, label: str) -> dict:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"0 / {total}")
        self._reset_results()
        self.btn_run.setEnabled(False)
        QApplication.processEvents()

        if organize:
            for _, folder, _, _ in TIERS:
                os.makedirs(os.path.join(self.folder_path, folder), exist_ok=True)

        counts = {lbl: 0 for lbl, *_ in TIERS}
        errors = 0

        for i, img_path in enumerate(images):
            try:
                from PIL import Image
                with Image.open(img_path) as pil:
                    w, h = pil.size
                upscale          = res / max(min(w, h), 1)
                lbl, folder, _   = _get_tier(upscale)
                counts[lbl]     += 1

                if organize:
                    dest = os.path.join(self.folder_path, folder, os.path.basename(img_path))
                    shutil.move(img_path, dest)
                    cap_src = os.path.splitext(img_path)[0] + ".txt"
                    if os.path.exists(cap_src):
                        shutil.move(cap_src, os.path.join(self.folder_path, folder, os.path.basename(cap_src)))
            except Exception as e:
                print(f"Signal check error on {img_path}: {e}")
                errors += 1

            self.progress_bar.setValue(i + 1)
            self.progress_label.setText(f"{i + 1} / {total}")
            QApplication.processEvents()

        # Update tier counts
        for lbl, w in self._tier_counts.items():
            n = counts.get(lbl, 0)
            w.setText(f"{n} image{'s' if n != 1 else ''}")

        # Grade
        letter, color, desc = _compute_grade(counts, total)
        self.grade_letter.setText(letter)
        self.grade_letter.setStyleSheet(f"font-size: 52px; font-weight: bold; color: {color};")
        self.grade_desc.setText(desc)

        action = "sorted into subfolders" if organize else label
        summary = f"Training resolution: {res}px\n{total} image(s) {action}."
        if errors:
            summary += f"\n{errors} file(s) could not be processed."
        if organize:
            summary += f"\n\nSubfolders created in:\n{self.folder_path}"
        self.summary_label.setText(summary)

        if not self._awaiting_continue:
            self.btn_run.setEnabled(True)

        return counts

    # ──────────────────────────────────────────────
    # DELETE DISCARD
    # ──────────────────────────────────────────────
    def delete_discard(self):
        discard_path = os.path.join(self.folder_path, "discard")
        if not os.path.isdir(discard_path):
            QMessageBox.information(self, "Nothing to delete", "No discard folder found.")
            return
        files = os.listdir(discard_path)
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(files)} file(s) in the discard folder?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        shutil.rmtree(discard_path)
        self.status_label.setText("Discard folder deleted.")
        self.btn_delete_discard.setEnabled(False)

    # ──────────────────────────────────────────────
    # FLATTEN — move all files back, remove subfolders
    # ──────────────────────────────────────────────
    def flatten_folders(self):
        # Flatten ALL subfolders, not just known ones
        all_subs = [
            f for f in os.listdir(self.folder_path)
            if os.path.isdir(os.path.join(self.folder_path, f))
        ]
        moved = 0
        for folder_name in all_subs:
            sub = os.path.join(self.folder_path, folder_name)
            for fname in os.listdir(sub):
                src  = os.path.join(sub, fname)
                dest = os.path.join(self.folder_path, fname)
                if os.path.exists(dest):
                    base, ext = os.path.splitext(fname)
                    i = 1
                    while os.path.exists(dest):
                        dest = os.path.join(self.folder_path, f"{base}_{i}{ext}")
                        i += 1
                shutil.move(src, dest)
                moved += 1
            shutil.rmtree(sub)

        self.status_label.setText(f"Flattened — {moved} file(s) moved back to main folder.")
        self.btn_delete_discard.setEnabled(False)
        self.btn_flatten.setEnabled(False)
        self._awaiting_continue = False
        self.btn_run.setText("Run Cropped Image Signal Check" if self._cropped_mode else "Run Signal Check")
        self.btn_run.setStyleSheet(BTN_RUN_CROPPED if self._cropped_mode else BTN_RUN_NORMAL)