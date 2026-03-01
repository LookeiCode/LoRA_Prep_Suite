import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QPushButton, QMessageBox

from ui.crop_studio    import CropStudioTab
from ui.file_studio    import FileStudioTab
from ui.signal_checker import SignalCheckerTab
from ui.injector       import InjectorTab


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
        "colors, or add up to 4 custom crop buttons.\n\n"
        "5. Training Target sets the output resolution. Signal Strength "
        "shows how clean the crop will be for training — lower upscale = better."
    ),
    "Signal Studio": (
        "Signal Studio",
        "Grade and filter your cropped images by training signal quality.\n\n"
        "1. Load a folder of cropped images.\n\n"
        "2. Each image gets a signal strength score based on how much "
        "upscaling is needed to hit the training resolution.\n\n"
        "3. Images are sorted into tiers: High, Mid, Low, Reject.\n\n"
        "4. Use Cropped Image Mode to grade images that are already "
        "cropped and organized into subfolders.\n\n"
        "5. Organize by signal strength moves images into tier subfolders "
        "so you can review and delete weak images before training."
    ),
    "File Studio": (
        "File Studio",
        "Bulk rename and prepare your image files for training.\n\n"
        "1. Select a folder containing images.\n\n"
        "2. Enter a base name — all images will be renamed to "
        "basename_1, basename_2, etc.\n\n"
        "3. Choose an output format, or keep originals.\n\n"
        "4. Optionally generate blank .txt caption files alongside "
        "each renamed image.\n\n"
        "5. Re-run on a folder to close gaps after deletions. "
        "Enable 'Rename existing captions' to keep them paired.\n\n"
        "Files are renamed in place — nothing is deleted."
    ),
    "Injector": (
        "Injector",
        "Inject cropped images into the correct dataset subfolders.\n\n"
        "1. Select a source folder containing mixed cropped images "
        "(e.g. after flattening from Signal Studio).\n\n"
        "2. Select the output folder — your main dataset folder "
        "with subfolders like 10_face, 15_torso, etc.\n\n"
        "3. face, torso, thigh, and fullbody are matched by default. "
        "Add custom keywords using the + buttons if needed.\n\n"
        "4. Hit Inject — files are matched by keyword in their "
        "filename to the matching subfolder in the output.\n\n"
        "5. Any file with no matching subfolder is moved into "
        "an 'unmatched' folder in the source for review."
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

        self.tabs.addTab(self.crop_studio_tab,    "Crop Studio")
        self.tabs.addTab(self.signal_checker_tab, "Signal Studio")
        self.tabs.addTab(self.file_studio_tab,    "File Studio")
        self.tabs.addTab(self.injector_tab,       "Injector")

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