from dataclasses import dataclass
from PySide6.QtGui import QColor

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg"}
DEFAULT_TRAINING_RESOLUTION = 512


@dataclass(frozen=True)
class CropType:
    key: str
    label: str
    suffix: str
    color: QColor


CROP_TYPES = [
    CropType("face",  "Face",      "_face",  QColor(0, 200, 120)),
    CropType("torso", "Torso Up",  "_torso", QColor(30, 144, 255)),
    CropType("thigh", "Thigh Up",  "_thigh", QColor(255, 215, 0)),
    CropType("full",  "Full Body", "_full",  QColor(220, 20, 60)),
]
