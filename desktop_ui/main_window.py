import sys

from PySide6.QtCore import QRect, QSettings, Signal, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget
from qfluentwidgets import FluentIcon, FluentWindow, InfoBar, InfoBarPosition, NavigationItemPosition, Theme, isDarkTheme, setTheme

from desktop_ui.controller import ChannelOperationController, RtmpMonitorController, ServiceProcessController, UpdateController
from desktop_ui.pages.channels import ChannelCenterPage
from desktop_ui.pages.about import AboutPage
from desktop_ui.pages.dashboard import DashboardPage
from desktop_ui.pages.logs import LogsPage
from desktop_ui.pages.rtmp import RtmpPage
from desktop_ui.pages.settings import SettingsPage
from desktop_ui.pages.sources import SourcesPage
from desktop_ui.pages.tasks import TasksPage
from utils.config import config, resource_path
from utils.i18n import t
from utils.tools import get_version_info


class NavigationResizeHandle(QWidget):
    width_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_origin = None
        self.start_width = 0
        self.setFixedWidth(6)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = event.globalPosition().x()
            self.start_width = self.parentWidget().width()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_origin is not None:
            self.width_changed.emit(self.start_width + int(event.globalPosition().x() - self.drag_origin))
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = None
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QColor("#475569" if isDarkTheme() else "#D7DEE8"))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        info = get_version_info()
        self.setWindowTitle(str(info.get("name") or "IPTV-API"))
        self.setWindowIcon(QIcon(resource_path("favicon.ico")))
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        self.navigationInterface.setReturnButtonVisible(False)
        if sys.platform == "darwin":
            self.setSystemTitleBarButtonVisible(True)
            self.titleBar.minBtn.hide()
            self.titleBar.maxBtn.hide()
            self.titleBar.closeBtn.hide()
        self.navigation_width = int(QSettings().value("appearance/navigation_width", 220))
        self.navigationInterface.setExpandWidth(self.navigation_width)
        self.navigationInterface.setMinimumExpandWidth(840)
        self.dashboard = DashboardPage(self)
        self.channels = ChannelCenterPage(self)
        self.rtmp = RtmpPage(self)
        self.sources = SourcesPage(self)
        self.logs = LogsPage(self)
        self.tasks = TasksPage(self)
        self.settings = SettingsPage(self)
        self.about = AboutPage(self)
        self.addSubInterface(self.dashboard, FluentIcon.HOME, t("desktop.dashboard"))
        self.addSubInterface(self.channels, FluentIcon.LIBRARY, t("desktop.channel_center"))
        self.addSubInterface(self.rtmp, FluentIcon.IOT, t("desktop.rtmp_monitor"))
        self.addSubInterface(self.sources, FluentIcon.DOCUMENT, t("desktop.sources"))
        self.addSubInterface(self.logs, FluentIcon.DEVELOPER_TOOLS, t("desktop.logs"))
        self.addSubInterface(self.tasks, FluentIcon.HISTORY, t("desktop.task_history"))
        self.addSubInterface(self.settings, FluentIcon.SETTING, t("desktop.settings"), NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.about, FluentIcon.INFO, t("desktop.about"), NavigationItemPosition.BOTTOM)
        self.theme_item = self.navigationInterface.addItem(
            "themeToggle",
            FluentIcon.CONSTRACT,
            "",
            self.toggle_theme,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
        panel = self.navigationInterface.panel
        panel.vBoxLayout.setContentsMargins(0, 48, 0, 5)
        panel.topLayout.removeWidget(panel.menuButton)
        panel.bottomLayout.addWidget(panel.menuButton, 0, Qt.AlignmentFlag.AlignBottom)
        self.navigation_resize_handle = NavigationResizeHandle(self.navigationInterface)
        self.navigation_resize_handle.width_changed.connect(self.set_navigation_width)
        panel.expandAni.valueChanged.connect(lambda _: self._position_navigation_resize_handle())
        self._update_theme_item()
        self._position_navigation_resize_handle()
        self.controller = UpdateController(self)
        self.operation_controller = ChannelOperationController(self)
        self.rtmp_controller = RtmpMonitorController(self)
        self.service_controller = ServiceProcessController(self)
        self.dashboard.run_requested.connect(self._start_update)
        self.dashboard.cancel_requested.connect(self.controller.cancel)
        self.controller.started.connect(self._update_started)
        self.controller.progress.connect(self.dashboard.set_progress)
        self.controller.output.connect(self.logs.append_runtime)
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
        self.channels.retest_category_requested.connect(
            lambda category: self.operation_controller.enqueue("retest_category", {"category": category})
        )
        self.operation_controller.task_started.connect(self.channels.set_task_started)
        self.operation_controller.task_progress.connect(self.channels.set_task_progress)
        self.operation_controller.task_succeeded.connect(self._operation_succeeded)
        self.operation_controller.task_failed.connect(self._operation_failed)
        self.rtmp_controller.snapshot.connect(self.rtmp.set_snapshot)
        self.rtmp.stream_control_requested.connect(self.rtmp_controller.control)
        self.rtmp.refresh_requested.connect(self.rtmp_controller.refresh)
        self.channels.stream_control_requested.connect(
            lambda action, row: self.rtmp_controller.control(action, row["result_key"])
        )
        self.rtmp_controller.control_finished.connect(self._stream_control_finished)
        self.service_controller.status_changed.connect(self.dashboard.set_service_status)
        self.service_controller.output.connect(self.logs.append_runtime)
        if config.open_service:
            self.service_controller.start()
        self.rtmp_controller.start()
        QApplication.instance().aboutToQuit.connect(self.shutdown)
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
        else:
            QApplication.instance().setQuitOnLastWindowClosed(True)

    def systemTitleBarRect(self, size):
        if sys.platform == "darwin":
            return QRect(0, 8, 75, size.height())
        return super().systemTitleBarRect(size)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_navigation_resize_handle()
        if sys.platform == "darwin":
            self.titleBar.move(90, 0)
            self.titleBar.resize(max(0, self.width() - 90), self.titleBar.height())

    def toggle_theme(self):
        self.set_dark_theme(not isDarkTheme())

    def set_dark_theme(self, dark: bool):
        setTheme(Theme.DARK if dark else Theme.LIGHT)
        QSettings().setValue("appearance/theme", "dark" if dark else "light")
        self._update_theme_item()
        self.navigation_resize_handle.update()

    def _update_theme_item(self):
        text = t("desktop.light_mode" if isDarkTheme() else "desktop.dark_mode")
        self.theme_item.setText(text)
        self.theme_item.setToolTip(text)

    def _position_navigation_resize_handle(self):
        if not hasattr(self, "navigation_resize_handle"):
            return
        navigation = self.navigationInterface
        expanded = navigation.width() > 48
        self.navigation_resize_handle.setVisible(expanded)
        if expanded:
            self.navigation_resize_handle.setGeometry(
                navigation.width() - self.navigation_resize_handle.width(),
                48,
                self.navigation_resize_handle.width(),
                max(0, navigation.height() - 48),
            )
            self.navigation_resize_handle.raise_()

    def set_navigation_width(self, width: int):
        self.navigation_width = max(180, min(360, int(width)))
        QSettings().setValue("appearance/navigation_width", self.navigation_width)
        self.navigationInterface.setExpandWidth(self.navigation_width)
        panel = self.navigationInterface.panel
        if not panel.isCollapsed():
            panel.resize(self.navigation_width, panel.height())
        self._position_navigation_resize_handle()

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

    def _stream_control_finished(self, action: str, success: bool, message: str):
        if success:
            InfoBar.success(t("desktop.stream_action_sent"), t(f"desktop.{action}_stream", action), parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.error(t("desktop.stream_action_failed"), message or action, parent=self, position=InfoBarPosition.TOP)

    def shutdown(self):
        self.rtmp_controller.shutdown()
        self.service_controller.stop()
        self.operation_controller.shutdown()
        self.controller.shutdown()

    def closeEvent(self, event):
        if self.tray and self.tray.isVisible():
            self.hide()
            event.ignore()
            return
        super().closeEvent(event)
