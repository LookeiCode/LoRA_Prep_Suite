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
        if field.isEnabled():
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

        # Custom keyword slots — 4 left, 4 right
        self._default_chips: List[QPushButton] = []
        self._custom_fields: List[QLineEdit] = []
        self._add_btns: List[QPushButton] = []

        kw_header = QHBoxLayout()
        kw_header.addWidget(QLabel("Custom keywords:"))
        kw_header.addStretch(1)
        self._auto_detect_btn = QPushButton("↻  Auto-detect")
        self._auto_detect_btn.setStyleSheet("""
            QPushButton {
                font-size: 13px; font-weight: bold;
                background-color: #1a3a2a; color: #00cc66;
                border: 1px solid #00aa44; border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover { background-color: #1f4a30; }
        """)
        self._auto_detect_btn.setToolTip("Auto-fill from custom crop types in Crop Studio")
        self._auto_detect_btn.clicked.connect(self._auto_detect_keywords)
        kw_header.addWidget(self._auto_detect_btn)
        left.addLayout(kw_header)
        left.addSpacing(6)

        # Two columns of 4
        cols_widget = QWidget()
        cols = QHBoxLayout(cols_widget)
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(12)

        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        for i in range(8):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.setAlignment(Qt.AlignLeft)

            add_btn = QPushButton("+")
            add_btn.setStyleSheet(ADD_BTN_STYLE)
            add_btn.setFocusPolicy(Qt.ClickFocus)
            add_btn.setFixedSize(34, 34)

            field = QLineEdit()
            field.setPlaceholderText(f"Keyword {i + 1}")
            field.setFixedSize(370 if i < 4 else 340, 34)
            field.setEnabled(False)
            field.setStyleSheet("background-color: transparent; border: none; color: transparent;")

            add_btn.clicked.connect(lambda _, f=field, b=add_btn: self._expand_custom(f, b))

            row.addWidget(add_btn)
            row.addWidget(field)

            if i < 4:
                left_col.addWidget(row_widget)
            else:
                right_col.addWidget(row_widget)

            self._custom_fields.append(field)
            self._add_btns.append(add_btn)

        cols.addLayout(left_col)
        cols.addLayout(right_col)
        left.addWidget(cols_widget)
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

        # ── Right panel — terminal log ──
        from PySide6.QtWidgets import QTextEdit
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)

        term_label = QLabel("INJECT LOG")
        term_label.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; color: #00ff66; font-weight: bold; padding: 6px 8px 2px 8px;")
        right.addWidget(term_label)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a;
                color: #00ff66;
                font-family: Consolas, Courier New, monospace;
                font-size: 12px;
                border: 1px solid #1a1a1a;
                padding: 8px;
            }
        """)
        self.terminal.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.terminal.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right.addWidget(self.terminal, 1)

        root.addLayout(left,  2)
        root.addSpacing(16)
        root.addLayout(right, 2)

    def _log(self, text: str, color: str = "#00ff66"):
        self.terminal.append(f'<span style="color:{color}; font-family:Consolas,monospace;">{text}</span>')
        self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())

    def set_crop_studio(self, crop_studio_tab):
        """Called by main window to give injector access to crop studio."""
        self._crop_studio = crop_studio_tab

    def _auto_detect_keywords(self):
        if not hasattr(self, '_crop_studio') or self._crop_studio is None:
            QMessageBox.information(self, "Auto-detect", "No Crop Studio data available.")
            return

        from core.config import CROP_TYPES as ORIGINAL_DEFAULTS
        original_labels = {ct.label for ct in ORIGINAL_DEFAULTS}

        # Any crop type whose label no longer matches the original is custom
        custom_types = [
            ct for ct in self._crop_studio.active_crop_types
            if not ct.is_default or ct.label not in original_labels
        ]

        if not custom_types:
            QMessageBox.information(self, "Auto-detect", "No custom crop types found in Crop Studio.")
            return

        # Reset all custom fields first
        for field, btn in zip(self._custom_fields, self._add_btns):
            self._collapse_custom(field, btn)

        # Fill top-down, left column first then right
        for i, ct in enumerate(custom_types[:8]):
            field = self._custom_fields[i]
            btn = self._add_btns[i]
            self._expand_custom(field, btn)
            # Use the suffix (minus leading _) as the inject keyword
            keyword = ct.suffix.lstrip("_")
            field.setText(keyword)

    # ──────────────────────────────────────────────
    # EXPAND CUSTOM FIELD
    # ──────────────────────────────────────────────
    def _expand_custom(self, field: QLineEdit, btn: QPushButton):
        field.setEnabled(True)
        field.setStyleSheet("")
        field.setFocus()
        btn.setText("−")
        btn.clicked.disconnect()
        btn.clicked.connect(lambda: self._collapse_custom(field, btn))

    def _collapse_custom(self, field: QLineEdit, btn: QPushButton):
        field.setEnabled(False)
        field.clear()
        field.setStyleSheet("background-color: transparent; border: none; color: transparent;")
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

        self.terminal.clear()
        self._log(f"&gt; Starting injection — {len(all_files)} file(s)", "#00aaff")
        self._log(f"&gt; Keywords: {', '.join(keywords)}", "#888888")
        self._log("─" * 48, "#222222")
        self.progress_bar.setMaximum(len(all_files))
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"0 / {len(all_files)}")
        QApplication.processEvents()

        matched_counts:   Dict[str, int] = {kw: 0 for kw in keywords}
        unmatched_files:  List[str]      = []
        errors = 0

        for i, fname in enumerate(all_files):
            stem = os.path.splitext(fname)[0]  # filename without extension
            # Crop name is everything after the last underscore
            # e.g. fullbody1_face -> "face", img_torso_up -> "torso_up"
            # We check the full stem too as fallback for files with no underscore
            parts = stem.split("_")
            crop_segment = "_".join(parts[1:]).lower() if len(parts) > 1 else stem.lower()
            matched_kw = None

            # First try matching against crop segment (after first underscore)
            for kw in keywords:
                if kw in crop_segment:
                    matched_kw = kw
                    break

            # Fallback: match against full stem if no match found
            if not matched_kw:
                full_stem = stem.lower()
                for kw in keywords:
                    if kw in full_stem:
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
                        self._log(f"  {fname}  →  {os.path.basename(target_folder)}/", "#00ff66")
                    except Exception as e:
                        print(f"Inject error on {fname}: {e}")
                        self._log(f"  ✖ ERROR: {fname}", "#ff3333")
                        errors += 1
                else:
                    unmatched_files.append(fname)
                    self._log(f"  ? {fname}  →  unmatched/", "#ff8800")
            else:
                unmatched_files.append(fname)
                self._log(f"  ? {fname}  →  unmatched/", "#ff8800")

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


        self._log("─" * 48, "#222222")
        self._log(f"&gt; Done — {total_moved} injected, {len(unmatched_files)} unmatched", "#00aaff")
        self.status_label.setText("Done.")
        self.btn_inject.setEnabled(True)