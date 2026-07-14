import os
import sys

from PySide6.QtCore import QCoreApplication, QStandardPaths, Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor


def _prepare_runtime():
    QCoreApplication.setOrganizationName("IPTV-API")
    QCoreApplication.setApplicationName("IPTV-API Desktop")
    if getattr(sys, "frozen", False):
        data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        os.makedirs(data_dir, exist_ok=True)
        os.chdir(data_dir)


def main():
    _prepare_runtime()
    if "--service" in sys.argv:
        from service.app import run_service
        run_service()
        return 0
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if getattr(sys, "frozen", False):
        from utils.config import config
        config.copy("config")
    from desktop_ui.main_window import MainWindow
    setTheme(Theme.AUTO)
    setThemeColor("#0F766E")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
