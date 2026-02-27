import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from ui.crop_studio   import CropStudioTab
from ui.file_studio   import FileStudioTab
from ui.signal_checker import SignalCheckerTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoRA Prep Suite")

        self.tabs = QTabWidget()

        self.crop_studio_tab    = CropStudioTab()
        self.file_studio_tab    = FileStudioTab()
        self.signal_checker_tab = SignalCheckerTab()

        self.tabs.addTab(self.crop_studio_tab,    "Crop Studio")
        self.tabs.addTab(self.signal_checker_tab, "Signal Studio")
        self.tabs.addTab(self.file_studio_tab,    "File Studio")

        self.setCentralWidget(self.tabs)

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