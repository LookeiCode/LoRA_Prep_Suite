from dataclasses import dataclass, field
from PySide6.QtGui import QColor

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg"}
DEFAULT_TRAINING_RESOLUTION = 512


@dataclass
class CropType:
    key: str
    label: str
    suffix: str
    color: QColor
    is_default: bool = True  # False for user-added custom types


CROP_TYPES = [
    CropType("face",  "Face",      "_face",  QColor(0, 200, 120)),
    CropType("torso", "Torso Up",  "_torso", QColor(30, 144, 255)),
    CropType("thigh", "Thigh Up",  "_thigh", QColor(255, 215, 0)),
    CropType("fullbody",  "Full Body", "_fullbody",  QColor(220, 20, 60)),
]