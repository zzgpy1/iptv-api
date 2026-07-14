import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor

from desktop_ui.main_window import MainWindow


def main():
    if "--service" in sys.argv:
        from service.app import run_service
        run_service()
        return 0
    QCoreApplication.setOrganizationName("IPTV-API")
    QCoreApplication.setApplicationName("IPTV-API Desktop")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    setTheme(Theme.AUTO)
    setThemeColor("#0F766E")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
