import os
import shutil
from typing import Optional, List, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFileDialog, QMessageBox, QApplication,
    QFrame, QProgressBar, QTextEdit, QSizePolicy,
)
from PIL import Image, ImageOps

from core.config import CROP_TYPES, SUPPORTED_EXTS
from core.pose_detection import PoseDetector

BTN_STYLE = """
    QPushButton {
        font-weight: bold; font-size: 15px;
        border-radius: 6px; border: 2px solid #555;
        background-color: #3a3a3a;
        
    }
    QPushButton:hover   { background-color: #4a4a4a; }
    QPushButton:pressed { background-color: #5a5a5a; }
    QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
"""

RUN_BTN_STYLE = """
    QPushButton {
        font-weight: bold; font-size: 15px;
        border-radius: 6px; border: 2px solid #00cc44;
        background-color: #1a3a22; color: #00ff66;
        
    }
    QPushButton:hover   { background-color: #1f4a2a; }
    QPushButton:pressed { background-color: #256030; }
    QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
"""
TIERS = [
    ("Good",    1.70),
    ("Okay",    2.50),
    ("Risky",   3.50),
    ("Discard", float("inf")),
]
CROP_ORDER = ["full", "thigh", "torso", "face"]


def _get_tier(upscale: float) -> str:
    for label, max_up in TIERS:
        if upscale <= max_up:
            return label
    return "Discard"


def _divider():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color: #444;")
    return line


class FullAutoTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.input_path:   Optional[str] = None
        self.staging_path: Optional[str] = None
        self.output_path:  Optional[str] = None
        self._stop_requested = False
        self.pose = PoseDetector()
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)

        # ── left panel ──────────────────────────────
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignTop)

        self.btn_input = QPushButton("1.  Select Input Folder")
        self.btn_input.clicked.connect(self.pick_input)
        self.input_label = QLabel("Input: (not set)")
        self.input_label.setWordWrap(True)
        self.input_label.setStyleSheet("color: #aaa;")
        left.addWidget(self.btn_input)
        left.addWidget(self.input_label)
        left.addSpacing(10)

        self.btn_staging = QPushButton("2.  Select Staging Folder")
        self.btn_staging.clicked.connect(self.pick_staging)
        self.staging_label = QLabel("Staging: (not set)")
        self.staging_label.setWordWrap(True)
        self.staging_label.setStyleSheet("color: #aaa;")
        left.addWidget(self.btn_staging)
        left.addWidget(self.staging_label)
        left.addSpacing(10)

        self.btn_output = QPushButton("3.  Select LoRA Dataset Folder")
        self.btn_output.clicked.connect(self.pick_output)
        self.output_label = QLabel("Dataset: (not set)")
        self.output_label.setWordWrap(True)
        self.output_label.setStyleSheet("color: #aaa;")
        left.addWidget(self.btn_output)
        left.addWidget(self.output_label)
        left.addSpacing(16)
        left.addWidget(_divider())
        left.addSpacing(16)

        left.addWidget(QLabel("Training resolution:"))
        res_row = QHBoxLayout()
        self.res_combo = QComboBox()
        self.res_combo.addItems(["512", "768", "1024", "Custom"])
        self.res_combo.currentTextChanged.connect(self._on_res_changed)
        self.custom_res = QLineEdit()
        self.custom_res.setPlaceholderText("e.g. 896")
        self.custom_res.setValidator(QIntValidator(64, 4096))
        self.custom_res.hide()
        res_row.addWidget(self.res_combo)
        res_row.addWidget(self.custom_res)
        left.addLayout(res_row)
        left.addSpacing(16)
        left.addWidget(_divider())
        left.addSpacing(16)

        self.btn_run = QPushButton("▶  Run Full Auto Pipeline")
        self.btn_run.setStyleSheet(RUN_BTN_STYLE)
        self.btn_run.setFixedHeight(60)
        self.btn_run.clicked.connect(self.run_pipeline)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setStyleSheet(BTN_STYLE)
        self.btn_stop.setFixedHeight(60)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._request_stop)

        btn_container = QWidget()
        btn_container.setFixedHeight(136)
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(16)
        btn_layout.addWidget(self.btn_run)
        btn_layout.addWidget(self.btn_stop)

        left.addWidget(btn_container)
        left.addSpacing(16)

        self.phase_label = QLabel("")
        self.phase_label.setAlignment(Qt.AlignCenter)
        self.phase_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #00ff66;")

        self.progress_label = QLabel("0 / 0")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #aaa; font-size: 13px;")

        left.addWidget(self.phase_label)
        left.addWidget(self.progress_label)
        left.addWidget(self.progress_bar)
        left.addSpacing(6)
        left.addWidget(self.status_label)
        left.addStretch(1)

        left_widget = QWidget()
        left_widget.setFixedWidth(810)
        left_widget.setLayout(left)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)

        term_label = QLabel("PIPELINE LOG")
        term_label.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; color: #00ff66; font-weight: bold; padding: 6px 8px 2px 8px;")
        right.addWidget(term_label)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a; color: #00ff66;
                font-family: Consolas, Courier New, monospace;
                font-size: 12px; border: 1px solid #1a1a1a; padding: 8px;
            }
        """)
        self.terminal.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.terminal.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right.addWidget(self.terminal, 1)

        root.addWidget(left_widget)
        root.addSpacing(16)
        root.addLayout(right, 2)

    # ── log ─────────────────────────────────────────
    def _log(self, text: str, color: str = "#00ff66"):
        self.terminal.append(f'<span style="color:{color}; font-family:Consolas,monospace;">{text}</span>')
        self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())
        QApplication.processEvents()

    def _log_phase(self, text: str):
        self._log("", "#111111")
        self._log("━" * 50, "#333333")
        self._log(f"  {text}", "#00aaff")
        self._log("━" * 50, "#333333")
        self.phase_label.setText(text)
        QApplication.processEvents()

    def _on_res_changed(self, text):
        self.custom_res.setVisible(text == "Custom")

    def _get_resolution(self) -> Optional[int]:
        text = self.res_combo.currentText()
        if text == "Custom":
            val = self.custom_res.text().strip()
            return int(val) if val.isdigit() and int(val) >= 64 else None
        return int(text)

    def _request_stop(self):
        self._stop_requested = True
        self.btn_stop.setText("Stopping…")
        self.btn_stop.setEnabled(False)
        self._log("⚠  Stop requested…", "#ff8800")

    def _set_running(self, running: bool):
        self.btn_run.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        if not running:
            self.btn_stop.setText("Stop")

    # ── pickers ─────────────────────────────────────
    def pick_input(self):
        d = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if not d: return
        self.input_path = d
        self.input_label.setText(f"Input: {d}")
        self.input_label.setStyleSheet("color: #e0e0e0;")

    def pick_staging(self):
        d = QFileDialog.getExistingDirectory(self, "Select Staging Folder")
        if not d: return
        self.staging_path = d
        self.staging_label.setText(f"Staging: {d}")
        self.staging_label.setStyleSheet("color: #e0e0e0;")

    def pick_output(self):
        d = QFileDialog.getExistingDirectory(self, "Select LoRA Dataset Folder")
        if not d: return
        self.output_path = d
        self.output_label.setText(f"Dataset: {d}")
        self.output_label.setStyleSheet("color: #e0e0e0;")

    # ── pipeline ────────────────────────────────────
    def run_pipeline(self):
        if not self.input_path:
            QMessageBox.warning(self, "No input", "Select an input folder first."); return
        if not self.staging_path:
            QMessageBox.warning(self, "No staging", "Select a staging folder first."); return
        if not self.output_path:
            QMessageBox.warning(self, "No dataset", "Select your LoRA dataset folder first."); return
        res = self._get_resolution()
        if not res:
            QMessageBox.warning(self, "No resolution", "Set a valid training resolution."); return

        self._stop_requested = False
        self._set_running(True)
        self.terminal.clear()
        self._log("&gt; Full Auto Pipeline starting", "#00aaff")
        self._log(f"&gt; Input:   {self.input_path}", "#888888")
        self._log(f"&gt; Staging: {self.staging_path}", "#888888")
        self._log(f"&gt; Dataset: {self.output_path}", "#888888")
        self._log(f"&gt; Resolution: {res}px", "#888888")

        try:
            sets = self._phase_crop(self.staging_path)
            if self._stop_requested or sets is None: self._abort(); return
            passed = self._phase_signal(sets, res)
            if self._stop_requested or passed is None: self._abort(); return
            self._phase_inject(passed)
            if self._stop_requested: self._abort(); return
            self._phase_rename()
            self._log_phase("✔  Pipeline Complete")
            self._log(f"&gt; Done! Dataset: {self.output_path}", "#00ff66")
            self.status_label.setText("Done.")
            self.phase_label.setText("✔ Complete")
        except Exception as e:
            self._log(f"✖ Fatal error: {e}", "#ff3333")
            self.status_label.setText("Error — check log.")

        self._set_running(False)

    # ── phase 1 ─────────────────────────────────────
    def _phase_crop(self, staging: str) -> Optional[Dict[str, List[str]]]:
        self._log_phase("Phase 1 / 4 — Auto Cropping")
        images = sorted([
            os.path.join(self.input_path, f)
            for f in os.listdir(self.input_path)
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
        ])
        if not images:
            self._log("✖ No images found.", "#ff3333"); return None
        self.progress_bar.setMaximum(len(images))
        self.progress_bar.setValue(0)
        sets: Dict[str, List[str]] = {}
        for i, img_path in enumerate(images):
            if self._stop_requested: return None
            stem = os.path.splitext(os.path.basename(img_path))[0]
            boxes = self.pose.compute_sequential_boxes(img_path)
            if not boxes:
                self._log(f"  ⚠ No pose: {os.path.basename(img_path)}", "#ff8800")
            else:
                try:
                    pil = ImageOps.exif_transpose(Image.open(img_path))
                    set_files = []
                    for k in CROP_ORDER:
                        if k not in boxes: continue
                        l, t, r, b = boxes[k]
                        out = os.path.join(staging, f"{stem}_{k}_C.png")
                        pil.crop((l, t, r, b)).save(out, format="PNG")
                        set_files.append(out)
                    sets[stem] = set_files
                    self._log(f"  ✂ {os.path.basename(img_path)}  →  {len(set_files)} crops", "#00ff66")
                except Exception as e:
                    self._log(f"  ✖ {os.path.basename(img_path)}: {e}", "#ff3333")
            self.progress_bar.setValue(i + 1)
            self.progress_label.setText(f"{i + 1} / {len(images)}")
            QApplication.processEvents()
        self._log(f"&gt; {len(sets)} set(s) cropped", "#00aaff")
        return sets

    # ── phase 2 ─────────────────────────────────────
    def _phase_signal(self, sets: Dict[str, List[str]], res: int) -> Optional[Dict[str, List[str]]]:
        self._log_phase("Phase 2 / 4 — Signal Check & Culling")
        self.progress_bar.setMaximum(len(sets))
        self.progress_bar.setValue(0)
        passed: Dict[str, List[str]] = {}
        culled = 0
        total_discards = 0

        TIER_COLOR = {"Good": "#00ff66", "Okay": "#ffd000", "Risky": "#ff8800", "Discard": "#ff3333"}
        TIER_LETTER = {"Good": "G", "Okay": "O", "Risky": "R", "Discard": "D"}

        for i, (stem, files) in enumerate(sets.items()):
            if self._stop_requested: return None

            file_tiers = []
            for fpath in files:
                try:
                    with Image.open(fpath) as pil:
                        w, h = pil.size
                    tier = _get_tier(res / max(min(w, h), 1))
                except:
                    tier = "Discard"
                parts = os.path.splitext(os.path.basename(fpath))[0].split("_")
                crop_key = parts[-2] if len(parts) >= 3 else "?"
                file_tiers.append((fpath, crop_key, tier))

            # always delete Discard files, count Risky
            risky_count = 0
            kept = []
            discarded = []
            for fpath, crop_key, tier in file_tiers:
                if tier == "Discard":
                    discarded.append((fpath, crop_key, tier))
                    try: os.remove(fpath)
                    except: pass
                    total_discards += 1
                else:
                    kept.append((fpath, crop_key, tier))
                    if tier == "Risky":
                        risky_count += 1

            good_okay = sum(1 for _, _, t in kept if t in ("Good", "Okay"))

            # cull entire set if fewer than 3 good/okay remain or more than 1 risky
            if good_okay < 3 or risky_count > 1:
                for fpath, _, _ in kept:
                    try: os.remove(fpath)
                    except: pass
                culled += 1
                self._log(f"  ✖ CULLED: {stem}  ({good_okay} good/okay, {risky_count} risky)", "#ff3333")
            else:
                passed[stem] = [fpath for fpath, _, _ in kept]

                # build colored grade string — all crops including discards
                grade_parts = []
                for _, crop_key, tier in kept + discarded:
                    color = TIER_COLOR[tier]
                    letter = TIER_LETTER[tier]
                    grade_parts.append(f'<span style="color:{color}">{crop_key}:{letter}</span>')
                grades_html = ", ".join(grade_parts)

                # name color = tier of the average upscale ratio across kept crops
                avg_upscale = sum(
                    res / max(min(Image.open(fp).size), 1)
                    for fp, _, _ in kept
                ) / len(kept)
                avg_tier = _get_tier(avg_upscale)
                name_color = TIER_COLOR[avg_tier]

                self.terminal.append(
                    f'<span style="color:{name_color}; font-family:Consolas,monospace;">  ✔ PASSED: {stem}  [</span>'
                    f'{grades_html}'
                    f'<span style="color:{name_color}; font-family:Consolas,monospace;">]</span>'
                )
                self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())

            self.progress_bar.setValue(i + 1)
            self.progress_label.setText(f"{i + 1} / {len(sets)}")
            QApplication.processEvents()

        self._log(f"&gt; {len(passed)} passed, {culled} culled", "#00aaff")
        all_grades: Dict[str, int] = {}
        for files in passed.values():
            for fpath in files:
                try:
                    with Image.open(fpath) as pil:
                        w, h = pil.size
                    tier = _get_tier(res / max(min(w, h), 1))
                except:
                    tier = "Discard"
                all_grades[tier] = all_grades.get(tier, 0) + 1
        if total_discards:
            all_grades["Discard"] = all_grades.get("Discard", 0) + total_discards
        grade_str = "  ".join(f"{k}: {v}" for k, v in all_grades.items())
        self._log(f"&gt; Grades — {grade_str}", "#888888")
        return passed

    # ── phase 3 ─────────────────────────────────────
    def _phase_inject(self, passed: Dict[str, List[str]]):
        self._log_phase("Phase 3 / 4 — Injecting into Dataset")
        all_files = [f for files in passed.values() for f in files]
        self.progress_bar.setMaximum(len(all_files))
        self.progress_bar.setValue(0)
        keywords = [ct.key for ct in CROP_TYPES]
        moved = 0
        unmatched = []
        for i, fpath in enumerate(all_files):
            if self._stop_requested: return
            fname = os.path.basename(fpath)
            parts = os.path.splitext(fname)[0].split("_")
            seg = parts[-2].lower() if len(parts) >= 3 else ""
            kw = next((k for k in keywords if k in seg), None)
            if kw:
                target = next((
                    os.path.join(self.output_path, n)
                    for n in os.listdir(self.output_path)
                    if os.path.isdir(os.path.join(self.output_path, n)) and kw in n.lower()
                ), None)
                if target:
                    dest = os.path.join(target, fname)
                    j = 1
                    while os.path.exists(dest):
                        dest = os.path.join(target, f"{os.path.splitext(fname)[0]}_{j}.png")
                        j += 1
                    shutil.move(fpath, dest)
                    moved += 1
                    self._log(f"  {fname}  →  {os.path.basename(target)}/", "#00ff66")
                else:
                    unmatched.append(fpath)
                    self._log(f"  ? {fname}  →  no subfolder", "#ff8800")
            else:
                unmatched.append(fpath)
                self._log(f"  ? {fname}  →  unmatched", "#ff8800")
            self.progress_bar.setValue(i + 1)
            self.progress_label.setText(f"{i + 1} / {len(all_files)}")
            QApplication.processEvents()
        if unmatched:
            ud = os.path.join(self.output_path, "unmatched")
            os.makedirs(ud, exist_ok=True)
            for fpath in unmatched:
                if os.path.exists(fpath):
                    shutil.move(fpath, os.path.join(ud, os.path.basename(fpath)))
        self._log(f"&gt; {moved} injected, {len(unmatched)} unmatched", "#00aaff")

    # ── phase 4 ─────────────────────────────────────
    def _phase_rename(self):
        self._log_phase("Phase 4 / 4 — Renaming & Captions")
        subfolders = [
            os.path.join(self.output_path, n)
            for n in os.listdir(self.output_path)
            if os.path.isdir(os.path.join(self.output_path, n)) and n != "unmatched"
        ]
        total = 0
        for subfolder in subfolders:
            if self._stop_requested: return
            sfname = os.path.basename(subfolder)
            parts = sfname.split("_", 1)
            prefix = parts[1] if len(parts) > 1 and parts[0].isdigit() else sfname
            images = sorted([
                os.path.join(subfolder, f)
                for f in os.listdir(subfolder)
                if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
            ], key=lambda p: os.path.basename(p).lower())
            if not images: continue
            self.progress_bar.setMaximum(len(images))
            self.progress_bar.setValue(0)
            temp_map = {}
            for i, src in enumerate(images):
                tmp = os.path.join(subfolder, f"__tmp_{i}.png")
                os.rename(src, tmp)
                cap = os.path.splitext(src)[0] + ".txt"
                if os.path.exists(cap):
                    os.rename(cap, os.path.join(subfolder, f"__tmp_{i}.txt"))
                temp_map[i] = (tmp, src)
            for i, (tmp, orig) in temp_map.items():
                final = os.path.join(subfolder, f"{prefix}_{i + 1}_C.png")
                os.rename(tmp, final)
                self._log(f"  ✎ {os.path.basename(orig)}  →  {sfname}/{prefix}_{i + 1}_C.png", "#00ccff")
                cap_tmp = os.path.join(subfolder, f"__tmp_{i}.txt")
                cap_final = os.path.join(subfolder, f"{prefix}_{i + 1}_C.txt")
                if os.path.exists(cap_tmp):
                    os.rename(cap_tmp, cap_final)
                else:
                    open(cap_final, "w").close()
                self._log(f"  + caption  →  {prefix}_{i + 1}.txt", "#ffaa00")
                total += 1
                self.progress_bar.setValue(i + 1)
                self.progress_label.setText(f"{i + 1} / {len(temp_map)}")
                QApplication.processEvents()
        self._log(f"&gt; {total} files renamed", "#00aaff")

    def _abort(self):
        self._log("━" * 50, "#333333")
        self._log("⚠  Stopped.", "#ff8800")
        self.phase_label.setText("Stopped")
        self.status_label.setText("Stopped.")
        self._set_running(False)