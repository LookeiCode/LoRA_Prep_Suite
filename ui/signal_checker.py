import os
import shutil
from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFileDialog, QMessageBox, QApplication,
    QFrame, QProgressBar, QCheckBox,
)

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg"}

TIERS = [
    ("Ideal",   "ideal",   "#00ff00", 1.70),
    ("Okay",    "okay",    "#ffd000", 2.50),
    ("Risky",   "risky",   "#ff8800", 3.50),
    ("Discard", "discard", "#ff3333", float("inf")),
]

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

    ideal   = counts.get("Ideal",   0) / total
    okay    = counts.get("Okay",    0) / total
    risky   = counts.get("Risky",   0) / total
    discard = counts.get("Discard", 0) / total

    clean = ideal + okay
    risky_total = risky + discard

    if ideal >= 0.75:
        return "A+", "#00ff00", "Excellent dataset. Mostly ideal images."
    elif ideal >= 0.50 and clean >= 0.80:
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


class SignalCheckerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path: Optional[str] = None
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)

        # ── Left panel — controls ──
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignTop)

        self.folder_label = QLabel("Folder: (not set)")
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet("color: #aaa;")
        self.btn_folder = QPushButton("Select Image Folder")
        self.btn_folder.setFocusPolicy(Qt.ClickFocus)
        self.btn_folder.clicked.connect(self.pick_folder)
        left.addWidget(self.btn_folder)
        left.addWidget(self.folder_label)
        left.addSpacing(16)
        left.addWidget(_divider())
        left.addSpacing(16)

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
        left.addSpacing(16)

        self.cb_organize = QCheckBox("Organize images into subfolders by tier")
        self.cb_organize.setChecked(True)
        left.addWidget(self.cb_organize)
        left.addSpacing(20)
        left.addWidget(_divider())
        left.addSpacing(16)

        self.btn_run = QPushButton("Run Signal Check")
        self.btn_run.setStyleSheet(BTN_STYLE)
        self.btn_run.clicked.connect(self.run_check)
        left.addWidget(self.btn_run)
        left.addSpacing(6)

        self.btn_delete_discard = QPushButton("Delete Discard Folder")
        self.btn_delete_discard.setStyleSheet(BTN_STYLE)
        self.btn_delete_discard.setEnabled(False)
        self.btn_delete_discard.clicked.connect(self.delete_discard)
        left.addWidget(self.btn_delete_discard)
        left.addSpacing(6)

        self.btn_flatten = QPushButton("Flatten — Move All Back & Remove Subfolders")
        self.btn_flatten.setStyleSheet(BTN_STYLE)
        self.btn_flatten.setEnabled(False)
        self.btn_flatten.clicked.connect(self.flatten_folders)
        left.addWidget(self.btn_flatten)
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

        # Tier rows
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

        # Dataset grade
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

    def _on_res_changed(self, text):
        self.custom_res.setVisible(text == "Custom")

    def _get_resolution(self) -> Optional[int]:
        text = self.res_combo.currentText()
        if text == "Custom":
            val = self.custom_res.text().strip()
            return int(val) if val.isdigit() and int(val) >= 64 else None
        return int(text)

    def pick_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if not directory:
            return
        self.folder_path = directory
        self.folder_label.setText(f"Folder: {directory}")
        self.folder_label.setStyleSheet("color: #e0e0e0;")
        images = self._get_images()
        self.progress_bar.setMaximum(max(len(images), 1))
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"0 / {len(images)}")
        self.status_label.setText(f"{len(images)} image(s) found.")
        for w in self._tier_counts.values():
            w.setText("—")
        self.grade_letter.setText("—")
        self.grade_letter.setStyleSheet("font-size: 52px; font-weight: bold; color: #555;")
        self.grade_desc.setText("")
        self.summary_label.setText("")
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

        organize = self.cb_organize.isChecked()
        total    = len(images)

        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"0 / {total}")
        self.status_label.setText("Scanning…")
        self.btn_run.setEnabled(False)
        for w in self._tier_counts.values():
            w.setText("—")
        self.grade_letter.setText("—")
        self.grade_letter.setStyleSheet("font-size: 52px; font-weight: bold; color: #555;")
        self.grade_desc.setText("")
        self.summary_label.setText("")
        QApplication.processEvents()

        if organize:
            for _, folder, _, _ in TIERS:
                os.makedirs(os.path.join(self.folder_path, folder), exist_ok=True)

        counts = {label: 0 for label, *_ in TIERS}
        errors = 0
        for i, img_path in enumerate(images):
            try:
                from PIL import Image
                with Image.open(img_path) as pil:
                    w, h = pil.size
                upscale          = res / max(min(w, h), 1)
                label, folder, _ = _get_tier(upscale)
                counts[label]   += 1

                if organize:
                    dest = os.path.join(self.folder_path, folder, os.path.basename(img_path))
                    shutil.move(img_path, dest)
                    # Move matching caption file if it exists
                    cap_src = os.path.splitext(img_path)[0] + ".txt"
                    if os.path.exists(cap_src):
                        cap_dest = os.path.join(self.folder_path, folder, os.path.basename(cap_src))
                        shutil.move(cap_src, cap_dest)

            except Exception as e:
                print(f"Signal check error on {img_path}: {e}")
                errors += 1

            self.progress_bar.setValue(i + 1)
            self.progress_label.setText(f"{i + 1} / {total}")
            QApplication.processEvents()

        # Update tier counts
        for label, w in self._tier_counts.items():
            n = counts.get(label, 0)
            w.setText(f"{n} image{'s' if n != 1 else ''}")

        # Dataset grade
        letter, color, desc = _compute_grade(counts, total)
        self.grade_letter.setText(letter)
        self.grade_letter.setStyleSheet(f"font-size: 52px; font-weight: bold; color: {color};")
        self.grade_desc.setText(desc)

        # Summary
        action = "sorted into subfolders" if organize else "analyzed (not moved)"
        summary = f"Training resolution: {res}px\n{total} image(s) {action}."
        if errors:
            summary += f"\n{errors} file(s) could not be processed."
        if organize:
            summary += f"\n\nSubfolders created in:\n{self.folder_path}"
        self.summary_label.setText(summary)
        self.status_label.setText("Done.")
        self.btn_run.setEnabled(True)
        if organize:
            self.btn_delete_discard.setEnabled(True)
            self.btn_flatten.setEnabled(True)

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
        tier_folders = [f for _, f, _, _ in TIERS]
        moved = 0
        for folder_name in tier_folders:
            sub = os.path.join(self.folder_path, folder_name)
            if not os.path.isdir(sub):
                continue
            for fname in os.listdir(sub):
                src  = os.path.join(sub, fname)
                dest = os.path.join(self.folder_path, fname)
                if os.path.exists(dest):
                    # Avoid collision — append _1, _2 etc
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