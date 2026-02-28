import os
import shutil
from typing import Optional, List, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QMessageBox, QApplication, QFrame,
)

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".txt"}
DEFAULT_KEYWORDS = ["face", "torso", "thigh", "fullbody"]

ADD_BTN_STYLE = """
    QPushButton {
        font-weight: bold; font-size: 18px;
        border-radius: 4px; border: 1px solid #555;
        background-color: #2e2e2e; color: #aaa;
        min-width: 34px; max-width: 34px;
        min-height: 34px; max-height: 34px;
        padding: 0px;
    }
    QPushButton:hover { background-color: #3a3a3a; color: #fff; }
"""

INJECT_BTN_STYLE = """
    QPushButton {
        font-weight: bold; font-size: 15px;
        border-radius: 6px; border: 2px solid #555;
        background-color: #3a3a3a;
        min-height: 60px; padding: 0px;
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


def _find_target_folder(output_dir: str, keyword: str) -> Optional[str]:
    """Find a subfolder inside output_dir whose name contains the keyword."""
    kw = keyword.lower()
    for name in os.listdir(output_dir):
        full = os.path.join(output_dir, name)
        if os.path.isdir(full) and kw in name.lower():
            return full
    return None


def _get_active_keywords(custom_fields) -> List[str]:
    keywords = list(DEFAULT_KEYWORDS)
    for field in custom_fields:
        if field.isVisible():
            val = field.text().strip().lower()
            if val:
                keywords.append(val)
    return keywords


class InjectorTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_path: Optional[str] = None
        self.output_path: Optional[str] = None
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)

        # ── Left panel — controls ──
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignTop)

        # Source folder
        self.source_label = QLabel("Source: (not set)")
        self.source_label.setWordWrap(True)
        self.source_label.setStyleSheet("color: #aaa;")
        self.btn_source = QPushButton("Select Source Folder")
        self.btn_source.setFocusPolicy(Qt.ClickFocus)
        self.btn_source.clicked.connect(self.pick_source)
        left.addWidget(self.btn_source)
        left.addWidget(self.source_label)
        left.addSpacing(12)

        # Output folder
        self.output_label = QLabel("Output: (not set)")
        self.output_label.setWordWrap(True)
        self.output_label.setStyleSheet("color: #aaa;")
        self.btn_output = QPushButton("Select Output Folder")
        self.btn_output.setFocusPolicy(Qt.ClickFocus)
        self.btn_output.clicked.connect(self.pick_output)
        left.addWidget(self.btn_output)
        left.addWidget(self.output_label)
        left.addSpacing(16)
        left.addWidget(_divider())
        left.addSpacing(16)

        # Custom keyword slots
        self._default_chips: List[QPushButton] = []  # kept for compat
        self._custom_fields: List[QLineEdit] = []

        left.addWidget(QLabel("Custom keywords:"))
        left.addSpacing(6)

        for i in range(4):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.setAlignment(Qt.AlignLeft)

            add_btn = QPushButton("+")
            add_btn.setStyleSheet(ADD_BTN_STYLE)
            add_btn.setFocusPolicy(Qt.ClickFocus)

            field = QLineEdit()
            field.setPlaceholderText(f"Custom keyword {i + 1}")
            field.setMinimumHeight(34)
            field.hide()

            add_btn.clicked.connect(lambda _, f=field, b=add_btn: self._expand_custom(f, b))

            row.addWidget(add_btn)
            row.addWidget(field)

            left.addWidget(row_widget)
            left.addSpacing(6)

            self._custom_fields.append(field)

        left.addSpacing(16)

        # Inject button
        self.btn_inject = QPushButton("Inject")
        self.btn_inject.setStyleSheet(INJECT_BTN_STYLE)
        self.btn_inject.clicked.connect(self.inject)
        left.addWidget(self.btn_inject)
        left.addSpacing(12)

        # Progress
        from PySide6.QtWidgets import QProgressBar
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

        # ── Right panel — info + results ──
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignTop)
        right.addSpacing(16)

        info_title = QLabel("How it works")
        info_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        right.addWidget(info_title)
        right.addSpacing(8)

        info = QLabel(
            "1. Select a source folder containing mixed cropped images\n"
            "    (e.g. after flattening from Signal Studio).\n\n"
            "2. Select the output folder — your main dataset folder\n"
            "    with subfolders like 10_face, 15_torso, etc.\n\n"
            "3. Toggle which default keywords to inject, and add\n"
            "    custom keywords using the + buttons.\n\n"
            "4. Hit Inject — files are matched by keyword in their\n"
            "    filename to the matching subfolder in the output.\n\n"
            "5. Any file with no matching subfolder is moved into\n"
            "    an 'unmatched' folder in the source for review.\n\n"
            "Caption .txt files are always moved with their image."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaa; font-size: 13px;")
        right.addWidget(info)
        right.addSpacing(16)
        right.addWidget(_divider())
        right.addSpacing(16)

        # Results
        self.results_label = QLabel("")
        self.results_label.setWordWrap(True)
        self.results_label.setStyleSheet("font-size: 13px; color: #ccc;")
        right.addWidget(self.results_label)
        right.addStretch(1)

        root.addLayout(left,  2)
        root.addSpacing(32)
        root.addLayout(right, 1)

    # ──────────────────────────────────────────────
    # EXPAND CUSTOM FIELD
    # ──────────────────────────────────────────────
    def _expand_custom(self, field: QLineEdit, btn: QPushButton):
        field.show()
        btn.setText("−")
        btn.clicked.disconnect()
        btn.clicked.connect(lambda: self._collapse_custom(field, btn))

    def _collapse_custom(self, field: QLineEdit, btn: QPushButton):
        field.hide()
        field.clear()
        btn.setText("+")
        btn.clicked.disconnect()
        btn.clicked.connect(lambda: self._expand_custom(field, btn))

    # ──────────────────────────────────────────────
    # FOLDER PICKERS
    # ──────────────────────────────────────────────
    def pick_source(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if not directory:
            return
        self.source_path = directory
        self.source_label.setText(f"Source: {directory}")
        self.source_label.setStyleSheet("color: #e0e0e0;")

    def pick_output(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not directory:
            return
        self.output_path = directory
        self.output_label.setText(f"Output: {directory}")
        self.output_label.setStyleSheet("color: #e0e0e0;")

    # ──────────────────────────────────────────────
    # INJECT
    # ──────────────────────────────────────────────
    def inject(self):
        if not self.source_path:
            QMessageBox.warning(self, "No source", "Select a source folder first.")
            return
        if not self.output_path:
            QMessageBox.warning(self, "No output", "Select an output folder first.")
            return

        keywords = _get_active_keywords(self._custom_fields)
        if not keywords:
            QMessageBox.warning(self, "No keywords", "Enable at least one keyword.")
            return

        # Collect all image files from source (not subfolders)
        all_files = [
            f for f in os.listdir(self.source_path)
            if os.path.isfile(os.path.join(self.source_path, f))
            and os.path.splitext(f)[1].lower() in SUPPORTED_EXTS - {".txt"}
        ]

        if not all_files:
            QMessageBox.warning(self, "No files", "No image files found in source folder.")
            return

        self.btn_inject.setEnabled(False)
        self.status_label.setText("Injecting…")
        self.results_label.setText("")
        self.progress_bar.setMaximum(len(all_files))
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"0 / {len(all_files)}")
        QApplication.processEvents()

        matched_counts:   Dict[str, int] = {kw: 0 for kw in keywords}
        unmatched_files:  List[str]      = []
        errors = 0

        for i, fname in enumerate(all_files):
            fname_lower = fname.lower()
            matched_kw  = None

            # Find first keyword that matches this filename
            for kw in keywords:
                if kw in fname_lower:
                    matched_kw = kw
                    break

            src = os.path.join(self.source_path, fname)

            if matched_kw:
                target_folder = _find_target_folder(self.output_path, matched_kw)
                if target_folder:
                    try:
                        dest = os.path.join(target_folder, fname)
                        if os.path.exists(dest):
                            base, ext = os.path.splitext(fname)
                            j = 1
                            while os.path.exists(dest):
                                dest = os.path.join(target_folder, f"{base}_{j}{ext}")
                                j += 1
                        shutil.move(src, dest)
                        matched_counts[matched_kw] += 1

                        # Move caption file if present
                        cap = os.path.join(self.source_path, os.path.splitext(fname)[0] + ".txt")
                        if os.path.exists(cap):
                            cap_dest = os.path.join(target_folder, os.path.basename(cap))
                            if os.path.exists(cap_dest):
                                base, _ = os.path.splitext(os.path.basename(cap))
                                ci = 1
                                while os.path.exists(cap_dest):
                                    cap_dest = os.path.join(target_folder, f"{base}_{ci}.txt")
                                    ci += 1
                            shutil.move(cap, cap_dest)
                    except Exception as e:
                        print(f"Inject error on {fname}: {e}")
                        errors += 1
                else:
                    unmatched_files.append(fname)
            else:
                unmatched_files.append(fname)

            self.progress_bar.setValue(i + 1)
            self.progress_label.setText(f"{i + 1} / {len(all_files)}")
            QApplication.processEvents()

        # Move unmatched files to unmatched/ in source
        if unmatched_files:
            unmatched_dir = os.path.join(self.source_path, "unmatched")
            os.makedirs(unmatched_dir, exist_ok=True)
            for fname in unmatched_files:
                src = os.path.join(self.source_path, fname)
                if os.path.exists(src):
                    shutil.move(src, os.path.join(unmatched_dir, fname))
                    # Move caption too
                    cap = os.path.join(self.source_path, os.path.splitext(fname)[0] + ".txt")
                    if os.path.exists(cap):
                        shutil.move(cap, os.path.join(unmatched_dir, os.path.basename(cap)))

        # Build results summary
        total_moved = sum(matched_counts.values())
        lines = [f"✔ Injected {total_moved} file(s) total\n"]
        for kw, count in matched_counts.items():
            if count > 0:
                lines.append(f"  {kw}:  {count} file(s)")
        if unmatched_files:
            lines.append(f"\n⚠  {len(unmatched_files)} unmatched → moved to 'unmatched/' in source")
        if errors:
            lines.append(f"\n✖  {errors} error(s) — check console")

        self.results_label.setText("\n".join(lines))
        self.status_label.setText("Done.")
        self.btn_inject.setEnabled(True)