import io
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap
from PySide6.QtWidgets import QWidget

from core.config import CROP_TYPES


class ImageCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setMinimumSize(640, 480)

        self._pixmap:              Optional[QPixmap]          = None
        self._img_size_px:         Optional[Tuple[int, int]]  = None
        self._draw_rect:           Optional[QRectF]           = None
        self._dragging:            bool                       = False
        self._drag_start:          Optional[QPointF]          = None
        self._drag_end:            Optional[QPointF]          = None
        self._crop_color:          QColor                     = CROP_TYPES[0].color
        self._interaction_enabled: bool                       = True

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
        self._dragging   = False
        self._drag_start = None
        self._drag_end   = None
        self.update()
        self._notify_quality()

    def has_image(self) -> bool:
        return (
            self._pixmap is not None
            and self._img_size_px is not None
            and not self._pixmap.isNull()
        )

    def set_image(self, pixmap: QPixmap, original_size_px: Tuple[int, int]):
        self._pixmap      = pixmap
        self._img_size_px = original_size_px
        self.clear_selection()
        self.update()
        self._notify_quality()

    def _image_draw_rect(self) -> Optional[QRectF]:
        if not self._pixmap or self._pixmap.isNull():
            return None
        w, h     = self.width(), self.height()
        pm_w     = self._pixmap.width()
        pm_h     = self._pixmap.height()
        if pm_w <= 0 or pm_h <= 0 or w <= 0 or h <= 0:
            return None
        scale  = min(w / pm_w, h / pm_h)
        draw_w = pm_w * scale
        draw_h = pm_h * scale
        return QRectF((w - draw_w) / 2, (h - draw_h) / 2, draw_w, draw_h)

    def _selection_rect(self) -> Optional[QRectF]:
        if self._drag_start is None or self._drag_end is None:
            return None
        x1, y1 = self._drag_start.x(), self._drag_start.y()
        x2, y2 = self._drag_end.x(),   self._drag_end.y()
        return QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1))

    def _clamp_to_rect(self, p: QPointF, r: QRectF) -> QPointF:
        return QPointF(
            min(max(p.x(), r.left()), r.right()),
            min(max(p.y(), r.top()),  r.bottom()),
        )

    def mousePressEvent(self, event):
        if not self._interaction_enabled or event.button() != Qt.LeftButton:
            return
        if not self.has_image():
            return
        dr = self._image_draw_rect()
        if not dr:
            return
        pos = QPointF(event.position())
        if not dr.contains(pos):
            return
        self._dragging   = True
        pos              = self._clamp_to_rect(pos, dr)
        self._drag_start = pos
        self._drag_end   = pos
        self.update()
        self._notify_quality()

    def mouseMoveEvent(self, event):
        if not self._dragging or not self.has_image():
            return
        dr = self._image_draw_rect()
        if not dr:
            return
        self._drag_end = self._clamp_to_rect(QPointF(event.position()), dr)
        self.update()
        self._notify_quality()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self._dragging:
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

        dr = self._image_draw_rect()
        self._draw_rect = dr
        painter.drawPixmap(dr, self._pixmap, QRectF(self._pixmap.rect()))

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

        dr      = self._draw_rect
        ow, oh  = self._img_size_px
        left    = max(sel.left(),   dr.left())
        top     = max(sel.top(),    dr.top())
        right   = min(sel.right(),  dr.right())
        bottom  = min(sel.bottom(), dr.bottom())

        if right <= left or bottom <= top:
            return None

        sx = ow / dr.width()
        sy = oh / dr.height()

        cl = max(0,        min(int(round((left   - dr.left()) * sx)), ow - 1))
        ct = max(0,        min(int(round((top    - dr.top())  * sy)), oh - 1))
        cr = max(cl + 1,   min(int(round((right  - dr.left()) * sx)), ow))
        cb = max(ct + 1,   min(int(round((bottom - dr.top())  * sy)), oh))

        return (cl, ct, cr, cb)
