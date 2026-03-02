import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QPushButton, QMessageBox

from ui.crop_studio    import CropStudioTab
from ui.file_studio    import FileStudioTab
from ui.signal_checker import SignalCheckerTab
from ui.injector       import InjectorTab
from ui.full_auto      import FullAutoTab


HELP_TEXT = {
    "Crop Studio": (
        "Crop Studio",
        "Manually or automatically crop images into training-ready sizes.\n\n"
        "1. Load an input folder of images and set an output folder.\n\n"
        "2. Manual mode — click a crop type button (Face, Torso Up, etc.), "
        "then drag a box on the image. Hit Save to write the crop.\n\n"
        "3. Auto mode — MediaPipe detects pose keypoints and automatically "
        "crops all four default types for each image.\n\n"
        "4. Use Advanced Crop Settings to rename crop types, change their "
        "colors, or add up to 4 custom crop buttons. Custom crops only work "
        "in manual mode — auto mode always uses the default 4.\n\n"
        "5. Training Target sets the output resolution. Framing Signal Strength "
        "shows how clean the crop will be for training — it measures how much "
        "the image needs to be upscaled to hit your training resolution. "
        "Lower upscale = sharper signal = better training quality.\n\n"
        "6. Auto-advance moves to the next image automatically after saving all crop types."
    ),
    "Signal Studio": (
        "Signal Studio",
        "Grade and filter your cropped images by training signal quality.\n\n"
        "1. Load a folder of cropped images and set your training resolution.\n\n"
        "2. Signal strength is based on how much upscaling is needed to hit "
        "the training resolution — lower upscale = better signal.\n\n"
        "3. Images are graded into tiers: Good, Okay, Risky, Discard.\n\n"
        "4. If 'Organize by signal strength' is checked, images are physically "
        "moved into subfolders (good/, okay/, risky/, discard/) after grading. "
        "If unchecked, the run only grades and scores the dataset without "
        "moving any files — useful for a quick quality check.\n\n"
        "5. The dataset grade (A+ through F) summarizes overall quality based "
        "on the ratio of good/okay/risky/discard images across the full set.\n\n"
        "6. Cropped Image Mode grades images already organized into crop type "
        "subfolders from Crop Studio.\n\n"
        "7. Flatten moves all files back to the main folder and removes subfolders — "
        "available as soon as any folder with subfolders is loaded."
    ),
    "Injector": (
        "Injector",
        "Inject cropped images into the correct dataset subfolders by keyword.\n\n"
        "1. Select a source folder containing mixed cropped images.\n\n"
        "2. Select the output folder — your main dataset folder with subfolders "
        "like 10_face, 15_torso, etc.\n\n"
        "3. face, torso, thigh, and fullbody are matched by default. "
        "Files are matched by the crop name suffix in their filename "
        "(e.g. photo1_face.png → face subfolder).\n\n"
        "4. Add custom keywords using the + buttons if your dataset uses "
        "non-standard crop names. Up to 8 custom keywords total.\n\n"
        "5. Auto-detect automatically reads your current crop type setup from "
        "Crop Studio — including any renamed defaults or custom crop buttons — "
        "and fills the keyword fields for you.\n\n"
        "6. Any file with no matching subfolder is moved into an "
        "'unmatched' folder in the source for review."
    ),
    "Full Auto": (
        "Full Auto",
        "Automates the entire pipeline from raw images to a fully prepared dataset.\n\n"
        "1. Select your input folder — the raw full-body images to crop from.\n\n"
        "2. Select your staging folder — a temporary folder where crops are saved "
        "before being checked and injected into the dataset.\n\n"
        "3. Select your LoRA dataset folder — your main dataset folder with subfolders "
        "like 10_face, 15_torso, etc. already set up.\n\n"
        "4. Set your training resolution and hit Run — the pipeline does everything automatically:\n\n"
        "   Phase 1 — Auto Crop: MediaPipe crops each image into 4 sequential "
        "crops (face, torso, thigh, full body).\n\n"
        "   Phase 2 — Signal Check & Cull: Each set of 4 crops is graded. "
        "If a set has more than 1 risky or discard quality image, the entire "
        "set is deleted. Only sets with 3+ good/okay crops survive.\n\n"
        "   Phase 3 — Inject: Surviving crops are sorted into the correct "
        "dataset subfolders by crop type.\n\n"
        "   Phase 4 — Rename & Captions: All files in each subfolder are "
        "renamed sequentially using the subfolder name as prefix with _C suffix "
        "to mark them as crops, and blank caption files are created for any new images."
    ),
    "File Studio": (
        "File Studio",
        "Bulk rename and prepare your image files for training.\n\n"
        "1. Select a folder containing images.\n\n"
        "2. Enter a base name — all images will be renamed to "
        "basename_1, basename_2, etc.\n\n"
        "3. Choose an output format, or keep originals.\n\n"
        "4. Optionally generate blank .txt caption files alongside "
        "each renamed image — useful for adding captions to new additions.\n\n"
        "5. Re-run on a folder to close gaps after deletions. "
        "Enable 'Rename existing captions' to keep them paired with their images.\n\n"
        "Files are renamed in place — nothing is deleted."
    ),
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoRA Prep Suite")

        self.tabs = QTabWidget()

        self.crop_studio_tab    = CropStudioTab()
        self.file_studio_tab    = FileStudioTab()
        self.signal_checker_tab = SignalCheckerTab()
        self.injector_tab       = InjectorTab()
        self.full_auto_tab      = FullAutoTab()

        self.tabs.addTab(self.crop_studio_tab,    "Crop Studio")
        self.tabs.addTab(self.signal_checker_tab, "Signal Studio")
        self.tabs.addTab(self.injector_tab,       "Injector")
        self.tabs.addTab(self.file_studio_tab,    "File Studio")
        self.tabs.addTab(self.full_auto_tab,      "Full Auto")

        self.injector_tab.set_crop_studio(self.crop_studio_tab)

        # Help button — top right of tab bar
        from PySide6.QtWidgets import QWidget, QHBoxLayout
        corner = QWidget()
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 8, 4)

        self.help_btn = QPushButton("?")
        self.help_btn.setFixedSize(28, 28)
        self.help_btn.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QPushButton:hover { background-color: #4a4a4a; }
        """)
        self.help_btn.clicked.connect(self.show_help)
        corner_layout.addWidget(self.help_btn)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)

        self.setCentralWidget(self.tabs)

    def eventFilter(self, obj, event):
        if obj is self.tabs.tabBar():
            from PySide6.QtCore import QEvent
            if event.type() in (QEvent.Resize, QEvent.Show):
                bar = self.tabs.tabBar()
                self.help_btn.move(bar.width() - 32, (bar.height() - 28) // 2)
        return super().eventFilter(obj, event)

    def show_help(self):
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        title, text = HELP_TEXT.get(tab_name, ("Help", "No help available for this tab."))
        QMessageBox.information(self, title, text)

    def keyPressEvent(self, event):
        # Forward keybinds to whichever tab is active
        current = self.tabs.currentWidget()
        if hasattr(current, "handle_key"):
            if current.handle_key(event.key()):
                event.accept()
                return
        super().keyPressEvent(event)


def apply_dark_theme(app):
    app.setStyleSheet("""
        QWidget {
            background-color: #2b2b2b;
            color: #e0e0e0;
            font-size: 14px;
        }
        QPushButton {
            background-color: #3a3a3a;
            border: 1px solid #555;
            padding: 6px;
        }
        QPushButton:hover   { background-color: #4a4a4a; }
        QPushButton:pressed { background-color: #5a5a5a; }
        QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
        QLabel   { color: #dcdcdc; }
        QComboBox {
            background-color: #3a3a3a;
            border: 1px solid #555;
            padding: 4px;
        }
        QLineEdit {
            background-color: #3a3a3a;
            border: 1px solid #555;
            padding: 4px;
        }
        QCheckBox { spacing: 6px; }
        QGroupBox { border: 1px solid #444; margin-top: 10px; }
        QTabWidget::pane { border: 1px solid #444; }
        QTabBar::tab {
            background: #3a3a3a;
            border: 1px solid #555;
            padding: 8px 14px;
            margin-right: 2px;
        }
        QTabBar::tab:selected { background: #4a4a4a; }
        QProgressBar {
            border: 1px solid #555;
            background-color: #2b2b2b;
            text-align: center;
        }
        QProgressBar::chunk { background-color: #4a90d9; }
    """)


def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    w = MainWindow()
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()