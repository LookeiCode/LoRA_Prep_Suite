import os
import sys
from dataclasses import dataclass
from typing import Optional, List, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QAction
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
    QGroupBox,
    QButtonGroup,
    QRadioButton,
)

from PIL import Image, ImageOps


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg"}


@dataclass(frozen=True)
class CropType:
    key: str
    label: str
    suffix: str
    color: QColor


CROP_TYPES = [
    CropType("full",  "Full Body", "_full",  QColor(220, 20, 60)),   # red-ish
    CropType("thigh", "Thigh Up",  "_thigh", QColor(255, 215, 0)),   # yellow
    CropType("torso", "Torso Up",  "_torso", QColor(30, 144, 255)),  # blue
    CropType("face",  "Face",      "_face",  QColor(0, 200, 120)),   # green
]


class ImageCanvas(QWidget):
    """
    Paints:
      - the scaled image centered inside the widget
      - a draggable selection rectangle (clamped to the image area)
    Provides:
      - get_crop_box_in_original_px() -> (left, top, right, bottom) in original image pixels
    """

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumSize(640, 480)

        self._pixmap: Optional[QPixmap] = None
        self._img_size_px: Optional[Tuple[int, int]] = None  # (w, h) of the original image after EXIF transpose

        # Display rect where pixmap is drawn (computed each paint)
        self._draw_rect: Optional[QRectF] = None

        # Selection
        self._dragging = False
        self._drag_start: Optional[QPointF] = None
        self._drag_end: Optional[QPointF] = None

        self._crop_color = CROP_TYPES[0].color  # default red

    def set_crop_color(self, color: QColor):
        self._crop_color = color
        self.update()

    def clear_selection(self):
        self._dragging = False
        self._drag_start = None
        self._drag_end = None
        self.update()

    def has_image(self) -> bool:
        return self._pixmap is not None and self._img_size_px is not None

    def set_image(self, pixmap: QPixmap, original_size_px: Tuple[int, int]):
        self._pixmap = pixmap
        self._img_size_px = original_size_px
        self.clear_selection()
        self.update()

    def _image_draw_rect(self) -> Optional[QRectF]:
        if not self._pixmap:
            return None

        w = self.width()
        h = self.height()
        pm_w = self._pixmap.width()
        pm_h = self._pixmap.height()

        if pm_w <= 0 or pm_h <= 0 or w <= 0 or h <= 0:
            return None

        # scale to fit while preserving aspect
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

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self._dragging:
            return
        self._dragging = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 18, 18))

        if not self._pixmap:
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(self.rect(), Qt.AlignCenter, "Select an input folder to load images.")
            return

        draw_rect = self._image_draw_rect()
        self._draw_rect = draw_rect

        # Draw image
        painter.drawPixmap(draw_rect, self._pixmap, QRectF(self._pixmap.rect()))

        # Draw selection
        sel = self._selection_rect()
        if sel and sel.width() > 2 and sel.height() > 2:
            # semi-transparent fill
            fill = QColor(self._crop_color)
            fill.setAlpha(60)
            painter.fillRect(sel, fill)

            pen = QPen(self._crop_color)
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(sel)

    def get_crop_box_in_original_px(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Returns crop box (left, top, right, bottom) in ORIGINAL image pixels.
        Selection is clamped to drawn image area.
        """
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

        # clamp selection to draw rect (extra safety)
        left = max(sel.left(), dr.left())
        top = max(sel.top(), dr.top())
        right = min(sel.right(), dr.right())
        bottom = min(sel.bottom(), dr.bottom())

        if right <= left or bottom <= top:
            return None

        # map from display coords -> original px
        scale_x = ow / dr.width()
        scale_y = oh / dr.height()

        crop_left = int(round((left - dr.left()) * scale_x))
        crop_top = int(round((top - dr.top()) * scale_y))
        crop_right = int(round((right - dr.left()) * scale_x))
        crop_bottom = int(round((bottom - dr.top()) * scale_y))

        # clamp to valid bounds
        crop_left = max(0, min(crop_left, ow - 1))
        crop_top = max(0, min(crop_top, oh - 1))
        crop_right = max(crop_left + 1, min(crop_right, ow))
        crop_bottom = max(crop_top + 1, min(crop_bottom, oh))

        return (crop_left, crop_top, crop_right, crop_bottom)


class CropStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoRA Prep Suite — Crop Studio (Phase 1)")
        self.setWindowState(Qt.WindowMaximized)

        self.input_dir: Optional[str] = None
        self.output_dir: Optional[str] = None

        self.images: List[str] = []
        self.index: int = 0
        self.current_image_path: Optional[str] = None

        self.current_crop_type: CropType = CROP_TYPES[0]

        self.canvas = ImageCanvas()

        # --- Top controls (folders + status) ---
        self.input_label = QLabel("Input: (not set)")
        self.output_label = QLabel("Output: (not set)")

        btn_input = QPushButton("Select Input Folder")
        btn_output = QPushButton("Select Output Folder")

        btn_input.clicked.connect(self.pick_input_folder)
        btn_output.clicked.connect(self.pick_output_folder)

        # --- Crop type radio buttons ---
        crop_group_box = QGroupBox("Crop Type")
        crop_layout = QHBoxLayout()
        self.crop_button_group = QButtonGroup(self)
        self.crop_button_group.setExclusive(True)

        for i, ct in enumerate(CROP_TYPES):
            rb = QRadioButton(f"{ct.label} ({ct.suffix})")
            if i == 0:
                rb.setChecked(True)
            # tiny color cue using stylesheet
            rb.setStyleSheet(
                f"QRadioButton::indicator {{ width: 14px; height: 14px; }}"
                f"QRadioButton {{ color: #EAEAEA; }}"
            )
            self.crop_button_group.addButton(rb, i)
            crop_layout.addWidget(rb)

        crop_group_box.setLayout(crop_layout)
        self.crop_button_group.idClicked.connect(self.on_crop_type_changed)

        # --- Output format dropdown ---
        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "Keep original",
            "PNG",
            "JPG",
        ])

        self.auto_advance = QCheckBox("Auto-advance after Save")
        self.auto_advance.setChecked(False)

        # --- Navigation + actions ---
        self.status_label = QLabel("No images loaded.")
        self.status_label.setStyleSheet("color: #EAEAEA;")

        btn_prev = QPushButton("◀ Prev")
        btn_next = QPushButton("Next ▶")
        btn_reset = QPushButton("Reset Crop")
        btn_save = QPushButton("Save Crop (S)")
        btn_skip = QPushButton("Skip (N)")

        btn_prev.clicked.connect(self.prev_image)
        btn_next.clicked.connect(self.next_image)
        btn_reset.clicked.connect(self.canvas.clear_selection)
        btn_save.clicked.connect(self.save_crop)
        btn_skip.clicked.connect(self.next_image)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(btn_prev)
        nav_layout.addWidget(btn_next)
        nav_layout.addSpacing(20)
        nav_layout.addWidget(btn_reset)
        nav_layout.addWidget(btn_save)
        nav_layout.addWidget(btn_skip)
        nav_layout.addStretch(1)
        nav_layout.addWidget(QLabel("Output format:"))
        nav_layout.addWidget(self.format_combo)
        nav_layout.addSpacing(12)
        nav_layout.addWidget(self.auto_advance)

        # --- Main layout ---
        top_layout = QVBoxLayout()
        folder_row = QHBoxLayout()
        folder_row.addWidget(btn_input)
        folder_row.addWidget(btn_output)
        folder_row.addStretch(1)

        top_layout.addLayout(folder_row)
        top_layout.addWidget(self.input_label)
        top_layout.addWidget(self.output_label)
        top_layout.addWidget(crop_group_box)
        top_layout.addWidget(self.status_label)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.addLayout(top_layout)
        root_layout.addWidget(self.canvas, stretch=1)
        root_layout.addLayout(nav_layout)

        self.setCentralWidget(root)

        # --- Keyboard shortcuts via actions ---
        act_save = QAction(self)
        act_save.setShortcut("S")
        act_save.triggered.connect(self.save_crop)
        self.addAction(act_save)

        act_next = QAction(self)
        act_next.setShortcut("N")
        act_next.triggered.connect(self.next_image)
        self.addAction(act_next)

        act_reset = QAction(self)
        act_reset.setShortcut("Backspace")
        act_reset.triggered.connect(self.canvas.clear_selection)
        self.addAction(act_reset)

        # set initial crop color
        self.canvas.set_crop_color(self.current_crop_type.color)

    # ------------------ Folder pickers ------------------

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

    # ------------------ Loading images ------------------

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
        self.index = 0

        if not self.images:
            self.current_image_path = None
            self.canvas.set_image(QPixmap(), (1, 1))
            self.status_label.setText("No supported images found in input folder.")
            return

        self.show_image_at_index()

    def show_image_at_index(self):
        if not self.images:
            return
        self.index = max(0, min(self.index, len(self.images) - 1))
        path = self.images[self.index]
        self.current_image_path = path

        # Load with PIL for correct EXIF orientation and true original size
        pil = Image.open(path)
        pil = ImageOps.exif_transpose(pil)  # fixes rotated JPEGs
        ow, oh = pil.size

        # Convert PIL -> QPixmap
        # Ensure we use RGB/RGBA in a safe way:
        if pil.mode not in ("RGB", "RGBA"):
            pil = pil.convert("RGB")

        # Save into bytes? We'll do a quick in-memory conversion using PIL and Qt via temp approach
        # (simple and reliable for phase 1)
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

    # ------------------ Crop type changes ------------------

    def on_crop_type_changed(self, idx: int):
        self.current_crop_type = CROP_TYPES[idx]
        self.canvas.set_crop_color(self.current_crop_type.color)

    # ------------------ Navigation ------------------

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

    # ------------------ Saving crops ------------------

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
        base = os.path.splitext(os.path.basename(src_path))[0]
        src_ext = os.path.splitext(src_path)[1].lower()

        fmt_choice = self.format_combo.currentText()
        if fmt_choice == "Keep original":
            out_ext = src_ext
            out_format = "PNG" if out_ext == ".png" else "JPEG"
        elif fmt_choice == "PNG":
            out_ext = ".png"
            out_format = "PNG"
        else:  # "JPG"
            out_ext = ".jpg"
            out_format = "JPEG"

        out_name = f"{base}{self.current_crop_type.suffix}{out_ext}"
        out_path = os.path.join(self.output_dir, out_name)

        try:
            pil = Image.open(src_path)
            pil = ImageOps.exif_transpose(pil)
            cropped = pil.crop(crop_box)

            # If saving as JPG, ensure RGB
            if out_format == "JPEG" and cropped.mode in ("RGBA", "LA"):
                cropped = cropped.convert("RGB")
            elif out_format == "JPEG" and cropped.mode not in ("RGB", "L"):
                cropped = cropped.convert("RGB")

            save_kwargs = {}
            if out_format == "JPEG":
                save_kwargs.update({"quality": 95, "subsampling": 0, "optimize": True})
            elif out_format == "PNG":
                save_kwargs.update({"optimize": True})

            # Avoid accidental overwrite:
            if os.path.exists(out_path):
                # Make a unique name
                i = 2
                while True:
                    candidate = os.path.join(self.output_dir, f"{base}{self.current_crop_type.suffix}_{i}{out_ext}")
                    if not os.path.exists(candidate):
                        out_path = candidate
                        break
                    i += 1

            cropped.save(out_path, format=out_format, **save_kwargs)

        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"Could not save crop.\n\n{e}")
            return

        # keep selection or reset? (I recommend reset so you don’t accidentally reuse it)
        self.canvas.clear_selection()

        # status update
        self.status_label.setText(
            f"Saved: {os.path.basename(out_path)}  |  {self.index + 1}/{len(self.images)} — {os.path.basename(src_path)}"
        )

        if self.auto_advance.isChecked():
            self.next_image()


def main():
    app = QApplication(sys.argv)
    w = CropStudio()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()