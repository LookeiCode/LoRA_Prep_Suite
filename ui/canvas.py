from typing import Optional, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap
from PySide6.QtWidgets import QWidget

from core.config import CROP_TYPES


class ImageCanvas(QWidget):
    """
    Selection is stored as normalized image-space coords (0.0-1.0)
    so it survives canvas resizes, dropdown clicks, layout shifts, etc.
    """
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setFixedSize(640, 540)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self._pixmap:              Optional[QPixmap]         = None
        self._img_size_px:         Optional[Tuple[int, int]] = None
        self._dragging:            bool                      = False
        self._crop_color:          QColor                    = CROP_TYPES[0].color
        self._interaction_enabled: bool                      = True
        self._quality_callback                               = None

        # Selection stored in normalized image space (0.0–1.0)
        self._sel_x1: Optional[float] = None
        self._sel_y1: Optional[float] = None
        self._sel_x2: Optional[float] = None
        self._sel_y2: Optional[float] = None

    def set_crop_color(self, color: QColor):
        self._crop_color = color
        self.update()

    def set_interaction_enabled(self, enabled: bool):
        self._interaction_enabled = bool(enabled)
        if not self._interaction_enabled:
            self.clear_selection()

    def _notify_quality(self):
        if self._quality_callback:
            self._quality_callback()
        elif hasattr(self.window(), "update_crop_quality"):
            self.window().update_crop_quality()

    def clear_selection(self):
        self._dragging = False
        self._sel_x1 = self._sel_y1 = self._sel_x2 = self._sel_y2 = None
        self.update()
        self._notify_quality()

    def has_image(self) -> bool:
        return self._pixmap is not None and not self._pixmap.isNull() and self._img_size_px is not None

    def has_selection(self) -> bool:
        return None not in (self._sel_x1, self._sel_y1, self._sel_x2, self._sel_y2)

    def set_image(self, pixmap: QPixmap, original_size_px: Tuple[int, int]):
        self._pixmap      = pixmap
        self._img_size_px = original_size_px
        self.clear_selection()
        self.update()

    def _image_draw_rect(self) -> Optional[QRectF]:
        if not self.has_image():
            return None
        w, h = self.width(), self.height()
        pm_w = self._pixmap.width()
        pm_h = self._pixmap.height()
        if pm_w <= 0 or pm_h <= 0 or w <= 0 or h <= 0:
            return None
        scale  = min(w / pm_w, h / pm_h)
        draw_w = pm_w * scale
        draw_h = pm_h * scale
        return QRectF((w - draw_w) / 2, (h - draw_h) / 2, draw_w, draw_h)

    def _screen_to_norm(self, pos: QPointF, dr: QRectF) -> Tuple[float, float]:
        """Convert screen pos to normalized image coords (0.0–1.0), clamped."""
        nx = (pos.x() - dr.left()) / dr.width()
        ny = (pos.y() - dr.top())  / dr.height()
        return max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))

    def _norm_to_screen(self, nx: float, ny: float, dr: QRectF) -> QPointF:
        """Convert normalized image coords back to screen pos."""
        return QPointF(dr.left() + nx * dr.width(), dr.top() + ny * dr.height())

    def _selection_screen_rect(self, dr: QRectF) -> Optional[QRectF]:
        if not self.has_selection():
            return None
        p1 = self._norm_to_screen(self._sel_x1, self._sel_y1, dr)
        p2 = self._norm_to_screen(self._sel_x2, self._sel_y2, dr)
        return QRectF(
            min(p1.x(), p2.x()), min(p1.y(), p2.y()),
            abs(p2.x() - p1.x()), abs(p2.y() - p1.y())
        )

    def mousePressEvent(self, event):
        if not self._interaction_enabled or event.button() != Qt.LeftButton:
            return
        if not self.has_image():
            return
        dr  = self._image_draw_rect()
        pos = QPointF(event.position())
        if not dr or not dr.adjusted(-1, -1, 1, 1).contains(pos):
            return
        nx, ny = self._screen_to_norm(pos, dr)
        self._dragging = True
        self._sel_x1 = self._sel_x2 = nx
        self._sel_y1 = self._sel_y2 = ny
        self.update()
        self._notify_quality()

    def mouseMoveEvent(self, event):
        if not self._dragging or not self.has_image():
            return
        dr = self._image_draw_rect()
        if not dr:
            return
        self._sel_x2, self._sel_y2 = self._screen_to_norm(QPointF(event.position()), dr)
        self.update()
        self._notify_quality()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self._dragging:
            return
        self._dragging = False
        self.update()
        self._notify_quality()

    def focusOutEvent(self, event):
        self._dragging = False
        super().focusOutEvent(event)

    def leaveEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.update()
            self._notify_quality()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 18, 18))

        if not self.has_image():
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(self.rect(), Qt.AlignCenter, "Select an input folder to load images.")
            return

        dr = self._image_draw_rect()
        if not dr:
            return
        painter.drawPixmap(dr, self._pixmap, QRectF(self._pixmap.rect()))

        if self.has_selection():
            sel = self._selection_screen_rect(dr)
            if sel and sel.width() > 2 and sel.height() > 2:
                fill = QColor(self._crop_color)
                fill.setAlpha(60)
                painter.fillRect(sel, fill)
                pen = QPen(self._crop_color)
                pen.setWidth(3)
                painter.setPen(pen)
                painter.drawRect(sel)

    def get_crop_box_in_original_px(self) -> Optional[Tuple[int, int, int, int]]:
        if not self.has_image() or not self.has_selection():
            return None
        ow, oh = self._img_size_px
        x1 = min(self._sel_x1, self._sel_x2)
        y1 = min(self._sel_y1, self._sel_y2)
        x2 = max(self._sel_x1, self._sel_x2)
        y2 = max(self._sel_y1, self._sel_y2)
        if x2 - x1 < 0.001 or y2 - y1 < 0.001:
            return None
        cl = max(0,      min(int(round(x1 * ow)), ow - 1))
        ct = max(0,      min(int(round(y1 * oh)), oh - 1))
        cr = max(cl + 1, min(int(round(x2 * ow)), ow))
        cb = max(ct + 1, min(int(round(y2 * oh)), oh))
        return (cl, ct, cr, cb)

    def set_overlay_box_normalized(self, nx1: float, ny1: float, nx2: float, ny2: float):
        """Set selection from normalized coords — used by auto mode."""
        self._sel_x1, self._sel_y1 = nx1, ny1
        self._sel_x2, self._sel_y2 = nx2, ny2
        self.update()