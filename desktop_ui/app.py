import os
import sys

from PySide6.QtCore import QCoreApplication, QSettings, QStandardPaths, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor


def _prepare_runtime():
    QCoreApplication.setOrganizationName("IPTV-API")
    QCoreApplication.setApplicationName("IPTV-API Desktop")
    if getattr(sys, "frozen", False):
        data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        os.makedirs(data_dir, exist_ok=True)
        os.chdir(data_dir)


def _copy_runtime_resources():
    if not getattr(sys, "frozen", False):
        return
    from utils.config import config
    config.copy("config")
    if sys.platform == "win32":
        config.copy(os.path.join("utils", "nginx-rtmp-win32"))


def main():
    _prepare_runtime()
    _copy_runtime_resources()
    if "--service" in sys.argv:
        from service.app import run_service
        run_service()
        return 0
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    from utils.config import resource_path
    app.setWindowIcon(QIcon(resource_path("favicon.ico")))
    from desktop_ui.main_window import MainWindow
    theme = str(QSettings().value("appearance/theme", "system"))
    setTheme({"dark": Theme.DARK, "light": Theme.LIGHT}.get(theme, Theme.AUTO))
    setThemeColor("#0E5CAD")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
