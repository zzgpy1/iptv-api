from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from qfluentwidgets import FluentIcon, FluentWindow, InfoBar, InfoBarPosition, NavigationItemPosition

from desktop_ui.controller import ChannelOperationController, UpdateController
from desktop_ui.pages.channels import ChannelCenterPage
from desktop_ui.pages.dashboard import DashboardPage
from desktop_ui.pages.logs import LogsPage
from desktop_ui.pages.rtmp import RtmpPage
from desktop_ui.pages.settings import SettingsPage
from desktop_ui.pages.sources import SourcesPage
from utils.config import resource_path
from utils.i18n import t
from utils.tools import get_version_info


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        info = get_version_info()
        self.setWindowTitle(f"{info.get('name', 'IPTV-API')} {info.get('version', '')}")
        self.setWindowIcon(QIcon(resource_path("favicon.ico")))
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        self.dashboard = DashboardPage(self)
        self.channels = ChannelCenterPage(self)
        self.rtmp = RtmpPage(self)
        self.sources = SourcesPage(self)
        self.logs = LogsPage(self)
        self.settings = SettingsPage(self)
        self.addSubInterface(self.dashboard, FluentIcon.HOME, t("desktop.dashboard"))
        self.addSubInterface(self.channels, FluentIcon.LIBRARY, t("desktop.channel_center"))
        self.addSubInterface(self.rtmp, FluentIcon.IOT, t("desktop.rtmp_monitor"))
        self.addSubInterface(self.sources, FluentIcon.DOCUMENT, t("desktop.sources"))
        self.addSubInterface(self.logs, FluentIcon.DEVELOPER_TOOLS, t("desktop.logs"))
        self.addSubInterface(self.settings, FluentIcon.SETTING, t("desktop.settings"), NavigationItemPosition.BOTTOM)
        self.controller = UpdateController(self)
        self.operation_controller = ChannelOperationController(self)
        self.dashboard.run_requested.connect(self._start_update)
        self.dashboard.cancel_requested.connect(self.controller.cancel)
        self.controller.started.connect(self._update_started)
        self.controller.progress.connect(self.dashboard.set_progress)
        self.controller.finished.connect(self._update_finished)
        self.controller.failed.connect(self._update_failed)
        self.channels.retest_channel_requested.connect(
            lambda row: self.operation_controller.enqueue("retest_channel", {"channel_key": row["channel_key"]})
        )
        self.channels.retest_result_requested.connect(
            lambda row: self.operation_controller.enqueue(
                "retest_result",
                {"channel_key": row["channel_key"], "result_key": row["result_key"]},
            )
        )
        self.operation_controller.task_started.connect(self.channels.set_task_started)
        self.operation_controller.task_progress.connect(self.channels.set_task_progress)
        self.operation_controller.task_succeeded.connect(self._operation_succeeded)
        self.operation_controller.task_failed.connect(self._operation_failed)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            menu = QMenu(self)
            show_action = QAction(t("desktop.show_window"), self)
            quit_action = QAction(t("desktop.quit"), self)
            show_action.triggered.connect(self.show_and_raise)
            quit_action.triggered.connect(QApplication.quit)
            menu.addAction(show_action)
            menu.addSeparator()
            menu.addAction(quit_action)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.show_and_raise() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.tray.show()

    def show_and_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _update_finished(self):
        self.dashboard.set_running(False)
        self.dashboard.refresh_metrics()
        self.channels.reload()
        self.operation_controller.resume()

    def _start_update(self):
        if self.operation_controller.is_busy:
            InfoBar.warning(t("desktop.task_running"), t("desktop.wait_for_task"), parent=self, position=InfoBarPosition.TOP)
            return
        self.controller.start()

    def _update_started(self):
        self.operation_controller.suspend()
        self.dashboard.set_running(True)

    def _update_failed(self, message: str):
        InfoBar.error(t("desktop.update_failed"), message.splitlines()[-1] if message else t("name.error"), parent=self, position=InfoBarPosition.TOP, duration=8000)

    def _operation_succeeded(self, operation: str, _):
        self.channels.set_task_finished()
        self.dashboard.refresh_metrics()
        InfoBar.success(t("desktop.task_completed"), t(f"desktop.{operation}", operation), parent=self, position=InfoBarPosition.TOP)

    def _operation_failed(self, operation: str, message: str):
        self.channels.set_task_finished()
        InfoBar.error(t("desktop.task_failed"), message.splitlines()[-1] if message else operation, parent=self, position=InfoBarPosition.TOP, duration=8000)

    def closeEvent(self, event):
        if self.tray and self.tray.isVisible():
            self.hide()
            event.ignore()
            return
        super().closeEvent(event)
