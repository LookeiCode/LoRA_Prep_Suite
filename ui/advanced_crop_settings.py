from typing import List, Optional, Callable
import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QWidget, QFrame, QColorDialog, QScrollArea,
    QMessageBox,
)

from core.config import CropType, CROP_TYPES


def _make_color_btn(color: QColor) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(32, 32)
    btn.setStyleSheet(
        f"background-color: {color.name()}; border: 2px solid #888; border-radius: 4px;"
    )
    return btn


def _set_color_btn(btn: QPushButton, color: QColor):
    btn.setStyleSheet(
        f"background-color: {color.name()}; border: 2px solid #888; border-radius: 4px;"
    )


class CropRow(QWidget):
    """A single editable crop type row."""
    def __init__(self, crop_type: CropType, removable: bool = False, parent=None):
        super().__init__(parent)
        self.color = QColor(crop_type.color)
        self._removable = removable
        self._on_remove: Optional[Callable] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        # Name field
        self.name_field = QLineEdit(crop_type.label)
        self.name_field.setMinimumWidth(120)
        self.name_field.setPlaceholderText("Crop name")

        # Color button
        self.color_btn = _make_color_btn(self.color)
        self.color_btn.setToolTip("Pick selection color")
        self.color_btn.clicked.connect(self._pick_color)

        layout.addWidget(self.name_field, 1)
        layout.addWidget(self.color_btn)

        if removable:
            self.remove_btn = QPushButton("✕")
            self.remove_btn.setFixedSize(28, 28)
            self.remove_btn.setStyleSheet(
                "QPushButton { background-color: #3a1a1a; color: #ff6666; "
                "border: 1px solid #663333; border-radius: 4px; font-weight: bold; }"
                "QPushButton:hover { background-color: #5a2020; }"
            )
            self.remove_btn.clicked.connect(lambda: self._on_remove and self._on_remove())
            layout.addWidget(self.remove_btn)

    def _pick_color(self):
        chosen = QColorDialog.getColor(self.color, self, "Pick Crop Color")
        if chosen.isValid():
            self.color = chosen
            _set_color_btn(self.color_btn, self.color)

    def get_label(self) -> str:
        return self.name_field.text().strip()

    def get_color(self) -> QColor:
        return self.color


def _divider():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color: #444;")
    return line


class AdvancedCropSettingsDialog(QDialog):
    def __init__(self, current_types: List[CropType], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Crop Settings")
        self.setMinimumWidth(420)
        self.setModal(True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setStyleSheet("background-color: #2b2b2b; color: #e0e0e0;")

        # Work on a copy so cancel discards changes
        self._original = current_types
        self._default_count = sum(1 for ct in current_types if ct.is_default)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Default crops ──
        root.addWidget(QLabel("Default crop types:"))

        self._default_rows: List[CropRow] = []
        for ct in current_types:
            if ct.is_default:
                row = CropRow(ct, removable=False, parent=self)
                root.addWidget(row)
                self._default_rows.append(row)

        root.addSpacing(8)
        root.addWidget(_divider())
        root.addSpacing(8)

        # ── Custom crops ──
        root.addWidget(QLabel("Custom crop types (up to 4):"))
        self._custom_container_widget = QWidget()
        self._custom_container = QVBoxLayout(self._custom_container_widget)
        self._custom_container.setSpacing(4)
        self._custom_container.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._custom_container_widget)

        self._custom_rows: List[CropRow] = []

        self._add_btn = QPushButton("+ Add Custom Crop")
        self._add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a3a2a; color: #00cc44;
                border: 1px solid #00aa33; border-radius: 4px;
                padding: 6px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2f4a2f; }
            QPushButton:disabled { background-color: #222; color: #444; border-color: #333; }
        """)
        self._add_btn.clicked.connect(self._add_empty_custom)

        # Restore existing custom crops
        for ct in current_types:
            if not ct.is_default:
                self._add_custom_row(ct)

        root.addWidget(self._add_btn)
        self._update_add_btn()

        root.addSpacing(8)
        root.addWidget(_divider())
        root.addSpacing(8)

        # ── Buttons ──
        btn_row_widget = QWidget()
        btn_row = QHBoxLayout(btn_row_widget)
        btn_row.setContentsMargins(0, 0, 0, 0)
        self._save_btn = QPushButton("Apply")
        self._save_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a4a2a; color: #00ff66;
                border: 1px solid #00aa44; border-radius: 4px;
                padding: 8px 20px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1f5a30; }
        """)
        self._save_btn.clicked.connect(self._apply)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a; color: #ccc;
                border: 1px solid #555; border-radius: 4px;
                padding: 8px 20px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
        """)
        cancel_btn.clicked.connect(lambda: (self.clearFocus(), self.reject()))

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a2a1a; color: #ffaa44;
                border: 1px solid #aa6622; border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #4a3020; }
        """)
        reset_btn.clicked.connect(self._reset_defaults)

        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._save_btn)
        root.addWidget(btn_row_widget)

        self.result_types: Optional[List[CropType]] = None

    def _add_custom_row(self, ct: CropType):
        row = CropRow(ct, removable=True, parent=self)
        row._on_remove = lambda r=row: self._remove_custom_row(r)
        self._custom_container.addWidget(row)
        self._custom_rows.append(row)
        self._update_add_btn()

    def _add_empty_custom(self):
        if len(self._custom_rows) >= 4:
            return
        dummy = CropType(
            key=f"custom{len(self._custom_rows)+1}",
            label="",
            suffix=f"_custom{len(self._custom_rows)+1}",
            color=QColor(180, 100, 220),
            is_default=False,
        )
        self._add_custom_row(dummy)
        # Focus the name field
        self._custom_rows[-1].name_field.setFocus()

    def _remove_custom_row(self, row: CropRow):
        self._custom_rows.remove(row)
        self._custom_container.removeWidget(row)
        row.setParent(None)
        row.hide()
        self._update_add_btn()

    def _update_add_btn(self):
        self._add_btn.setEnabled(len(self._custom_rows) < 4)

    def _reset_defaults(self):
        from core.config import CROP_TYPES as DEFAULTS
        # Reset default row labels/colors
        for i, row in enumerate(self._default_rows):
            row.name_field.setText(DEFAULTS[i].label)
            row.color = QColor(DEFAULTS[i].color)
            _set_color_btn(row.color_btn, row.color)
        # Remove all custom rows
        for row in list(self._custom_rows):
            self._remove_custom_row(row)

    def _apply(self):
        result = []

        # Validate defaults
        for i, row in enumerate(self._default_rows):
            label = row.get_label()
            if not label:
                QMessageBox.warning(self, "Empty name", "Default crop names cannot be empty.")
                return
            orig = self._original[i]
            result.append(CropType(
                key=orig.key,
                label=label,
                suffix=f"_{label.lower().replace(' ', '_')}",
                color=row.get_color(),
                is_default=True,
            ))

        # Validate and collect customs
        for row in self._custom_rows:
            label = row.get_label()
            if not label:
                QMessageBox.warning(self, "Empty name", "Custom crop names cannot be empty.")
                return
            key = label.lower().replace(" ", "_")
            result.append(CropType(
                key=key,
                label=label,
                suffix=f"_{key}",
                color=row.get_color(),
                is_default=False,
            ))

        self.result_types = result
        self.clearFocus()
        self.accept()