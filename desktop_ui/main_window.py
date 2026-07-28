import os
import sys
import threading

from PySide6.QtCore import QRect, QSettings, QTimer, Signal, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QDialogButtonBox, QLabel, QMenu, QMessageBox, QSystemTrayIcon, QVBoxLayout, QWidget
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
from desktop_ui.models import ChannelLogoLoader
from desktop_ui.widgets import NavigationStatusIndicator
from desktop_ui.platform_integration import set_macos_activation_policy
import utils.constants as constants
from utils.config import config, resource_path
from utils.i18n import get_language, set_language, t
from utils.rtmp_runtime import install_rtmp_runtime
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
    rtmp_install_finished = Signal(dict)
    rtmp_install_output = Signal(str)

    def __init__(self):
        super().__init__()
        info = get_version_info()
        self.setWindowTitle(str(info.get("name") or "IPTV-API"))
        icon_path = "static/images/macos_app_icon.icns" if sys.platform == "darwin" else "favicon.ico"
        self.setWindowIcon(QIcon(resource_path(icon_path)))
        self._window_geometry_timer = QTimer(self)
        self._window_geometry_timer.setSingleShot(True)
        self._window_geometry_timer.setInterval(300)
        self._window_geometry_timer.timeout.connect(self._save_window_geometry)
        self._configure_initial_geometry()
        self.navigationInterface.setReturnButtonVisible(False)
        if sys.platform == "darwin":
            self.setSystemTitleBarButtonVisible(True)
            self.titleBar.minBtn.hide()
            self.titleBar.maxBtn.hide()
            self.titleBar.closeBtn.hide()
        self.navigation_width = int(QSettings().value("appearance/navigation_width", 220))
        self.navigationInterface.setExpandWidth(self.navigation_width)
        self.navigationInterface.setMinimumExpandWidth(840)
        self.channel_logo_loader = ChannelLogoLoader(self)
        self.dashboard = DashboardPage(self, self.channel_logo_loader)
        self.channels = ChannelCenterPage(self, self.channel_logo_loader)
        self.rtmp = RtmpPage(self)
        self.sources = SourcesPage(self)
        self.logs = LogsPage(self)
        self.tasks = TasksPage(self)
        self.settings = SettingsPage(self)
        self.about = AboutPage(self)
        self.dashboard_item = self.addSubInterface(self.dashboard, FluentIcon.HOME, t("desktop.dashboard"))
        self.channels_item = self.addSubInterface(self.channels, FluentIcon.LIBRARY, t("desktop.channel_center"))
        self.rtmp_item = self.addSubInterface(self.rtmp, FluentIcon.IOT, t("desktop.play_streaming"))
        self.sources_item = self.addSubInterface(self.sources, FluentIcon.FOLDER, t("desktop.sources"))
        self.logs_item = self.addSubInterface(self.logs, FluentIcon.COMMAND_PROMPT, t("desktop.logs"))
        self.tasks_item = self.addSubInterface(self.tasks, FluentIcon.HISTORY, t("desktop.task_history"))
        self.settings_item = self.addSubInterface(self.settings, FluentIcon.SETTING, t("desktop.settings"), NavigationItemPosition.BOTTOM)
        self.about_item = self.addSubInterface(self.about, FluentIcon.INFO, t("desktop.about"), NavigationItemPosition.BOTTOM)
        self._navigation_items = {
            "dashboard": (self.dashboard_item, "desktop.dashboard", self.dashboard),
            "channels": (self.channels_item, "desktop.channel_center", self.channels),
            "rtmp": (self.rtmp_item, "desktop.play_streaming", self.rtmp),
            "sources": (self.sources_item, "desktop.sources", self.sources),
            "logs": (self.logs_item, "desktop.logs", self.logs),
            "tasks": (self.tasks_item, "desktop.task_history", self.tasks),
            "settings": (self.settings_item, "desktop.settings", self.settings),
            "about": (self.about_item, "desktop.about", self.about),
        }
        self._navigation_statuses = {}
        self._navigation_indicators = {}
        for name, (item, _, _) in self._navigation_items.items():
            indicator = NavigationStatusIndicator(item)
            indicator.move(24, 3)
            self._navigation_indicators[name] = indicator
        self.language_item = self.navigationInterface.addItem(
            "languageToggle",
            FluentIcon.LANGUAGE,
            "",
            self.toggle_language,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
        self.language_item.setEnabled(not self._language_environment_override())
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
        self._update_language_item()
        self._update_theme_item()
        self._position_navigation_resize_handle()
        self.controller = UpdateController(self)
        self._update_activity_state = "idle"
        self.operation_controller = ChannelOperationController(self)
        self.rtmp_controller = RtmpMonitorController(self)
        self.service_controller = ServiceProcessController(self)
        self.dashboard.run_requested.connect(self._start_update)
        self.dashboard.pause_requested.connect(self._pause_update)
        self.dashboard.resume_requested.connect(self._resume_update)
        self.dashboard.cancel_requested.connect(self._cancel_update)
        self.dashboard.destination_requested.connect(self._navigate_from_dashboard)
        self.settings.settings_saved.connect(self.dashboard.refresh_schedule)
        self.controller.started.connect(self._update_started)
        self.controller.progress.connect(self.dashboard.set_progress)
        self.controller.output.connect(self._on_runtime_output)
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
        self.operation_controller.task_started.connect(self._operation_started)
        self.operation_controller.task_progress.connect(self.channels.set_task_progress)
        self.operation_controller.task_succeeded.connect(self._operation_succeeded)
        self.operation_controller.task_failed.connect(self._operation_failed)
        self.rtmp_controller.snapshot.connect(self.rtmp.set_snapshot)
        self.rtmp_controller.snapshot.connect(self.dashboard.set_stream_snapshot)
        self.rtmp_controller.snapshot.connect(self.channels.set_stream_snapshot)
        self.rtmp_controller.snapshot.connect(self._update_rtmp_navigation_status)
        self.rtmp.stream_control_requested.connect(self.rtmp_controller.control)
        self.rtmp.stream_control_many_requested.connect(self.rtmp_controller.control_many)
        self.dashboard.stream_control_many_requested.connect(self.rtmp_controller.control_many)
        self.channels.stream_control_many_requested.connect(self.rtmp_controller.control_many)
        self.rtmp.refresh_requested.connect(self.rtmp_controller.refresh)
        self.rtmp.install_requested.connect(self._install_rtmp_from_ui)
        self.rtmp.settings_requested.connect(self._open_rtmp_limit_settings)
        self.channels.playback_workspace_requested.connect(self._open_playback_workspace)
        self.channels.playback_batch_requested.connect(self._open_playback_batch)
        self.channels.stream_monitor_requested.connect(lambda: self.switchTo(self.rtmp))
        self.rtmp_controller.control_finished.connect(self._stream_control_finished)
        self.rtmp_controller.batch_control_finished.connect(self._stream_batch_control_finished)
        self.service_controller.status_changed.connect(self._service_status_changed)
        self.service_controller.output.connect(self._on_runtime_output)
        self.about.status_changed.connect(self._update_about_navigation_status)
        self.rtmp_install_finished.connect(self._finish_rtmp_install)
        self.rtmp_install_output.connect(self._append_runtime_log)
        self.stackedWidget.currentChanged.connect(self._navigation_page_changed)
        if config.open_service:
            self._start_service()
        self.rtmp_controller.start()
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        self._force_quit = False
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("IPTV API")
            menu = QMenu(self)
            self.show_action = QAction(t("desktop.show_window"), self)
            self.quit_action = QAction(t("desktop.quit"), self)
            self.show_action.triggered.connect(self.show_and_raise)
            self.quit_action.triggered.connect(self.quit_app)
            menu.addAction(self.show_action)
            menu.addSeparator()
            menu.addAction(self.quit_action)
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
        if self.isVisible():
            self._window_geometry_timer.start()
        if sys.platform == "darwin":
            self.titleBar.move(90, 0)
            self.titleBar.resize(max(0, self.width() - 90), self.titleBar.height())

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.isVisible():
            self._window_geometry_timer.start()

    def _configure_initial_geometry(self):
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry()
        minimum_width = min(960, available.width())
        minimum_height = min(640, available.height())
        self.setMinimumSize(minimum_width, minimum_height)

        saved_geometry = QSettings().value("appearance/window_geometry")
        if saved_geometry is not None and self.restoreGeometry(saved_geometry):
            return

        width = max(minimum_width, min(1280, round(available.width() * 0.9)))
        height = max(minimum_height, min(800, round(available.height() * 0.9)))
        self.resize(width, height)
        self.move(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
        )

    def _save_window_geometry(self):
        QSettings().setValue("appearance/window_geometry", self.saveGeometry())

    def toggle_theme(self):
        self.set_dark_theme(not isDarkTheme())

    @staticmethod
    def _language_environment_override():
        names = ("language", "LANGUAGE", "Settings_language", "SETTINGS_LANGUAGE")
        return any(os.getenv(name) is not None for name in names)

    def toggle_language(self):
        language = "zh_CN" if get_language().startswith("en") else "en"
        config.set("Settings", "language", language)
        config.save()
        set_language(language)
        self.retranslate()

    def set_dark_theme(self, dark: bool):
        setTheme(Theme.DARK if dark else Theme.LIGHT)
        QSettings().setValue("appearance/theme", "dark" if dark else "light")
        self._update_theme_item()
        self.navigation_resize_handle.update()

    def _update_theme_item(self):
        text = t("desktop.light_mode" if isDarkTheme() else "desktop.dark_mode")
        self.theme_item.setText(text)
        self.theme_item.setToolTip(text)

    def _update_language_item(self):
        text = t("desktop.chinese" if get_language().startswith("en") else "desktop.english")
        self.language_item.setText(text)
        self.language_item.setToolTip(text)

    def retranslate(self, _language=None):
        navigation_items = (
            (self.dashboard_item, "desktop.dashboard"),
            (self.channels_item, "desktop.channel_center"),
            (self.rtmp_item, "desktop.play_streaming"),
            (self.sources_item, "desktop.sources"),
            (self.logs_item, "desktop.logs"),
            (self.tasks_item, "desktop.task_history"),
            (self.settings_item, "desktop.settings"),
            (self.about_item, "desktop.about"),
        )
        for item, key in navigation_items:
            text = t(key)
            item.setText(text)
            item.setToolTip(text)
        for page in (
            self.dashboard,
            self.channels,
            self.rtmp,
            self.sources,
            self.logs,
            self.tasks,
            self.settings,
            self.about,
        ):
            page.retranslate()
        if self.tray:
            self.show_action.setText(t("desktop.show_window"))
            self.quit_action.setText(t("desktop.quit"))
        self._update_language_item()
        self._update_theme_item()
        self._refresh_navigation_statuses()

    def _set_navigation_status(
            self,
            name: str,
            icon,
            color: str,
            status_key: str,
            status_args: dict | None = None,
            dismiss_on_visit: bool = False,
    ):
        if name not in self._navigation_items:
            return
        _, _, page = self._navigation_items[name]
        if dismiss_on_visit and self.stackedWidget.currentWidget() is page:
            self._clear_navigation_status(name)
            return
        self._navigation_statuses[name] = {
            "icon": icon,
            "color": color,
            "status_key": status_key,
            "status_args": status_args or {},
            "dismiss_on_visit": dismiss_on_visit,
        }
        self._refresh_navigation_status(name)

    def _clear_navigation_status(self, name: str):
        self._navigation_statuses.pop(name, None)
        indicator = self._navigation_indicators.get(name)
        if indicator:
            indicator.hide()
        if name in self._navigation_items:
            item, title_key, _ = self._navigation_items[name]
            title = t(title_key)
            item.setToolTip(title)

    def _refresh_navigation_status(self, name: str):
        status = self._navigation_statuses.get(name)
        if not status:
            return
        item, title_key, _ = self._navigation_items[name]
        title = t(title_key)
        detail = t(status["status_key"]).format(**status["status_args"])
        item.setToolTip(f"{title} · {detail}")
        indicator = self._navigation_indicators[name]
        indicator.setToolTip(detail)
        if self.stackedWidget.currentWidget() is self._navigation_items[name][2]:
            indicator.hide()
        else:
            indicator.set_status(status["icon"], status["color"])

    def _refresh_navigation_statuses(self):
        for name in self._navigation_statuses:
            self._refresh_navigation_status(name)

    def _navigation_page_changed(self, _index: int):
        current = self.stackedWidget.currentWidget()
        for name, (_, _, page) in self._navigation_items.items():
            status = self._navigation_statuses.get(name)
            if page is current and status and status.get("dismiss_on_visit"):
                self._clear_navigation_status(name)
        self._refresh_navigation_statuses()

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
        if sys.platform == "darwin":
            set_macos_activation_policy(False)
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self._force_quit = True
        QApplication.quit()

    def _navigate_from_dashboard(self, destination: str):
        page = {
            "channels": self.channels,
            "rtmp": self.rtmp,
            "tasks": self.tasks,
        }.get(destination)
        if page:
            self.switchTo(page)

    def _open_playback_workspace(self, row: dict):
        self.rtmp.select_result(row)
        self.switchTo(self.rtmp)

    def _open_playback_batch(self, rows: list[dict]):
        channel_keys = [row["channel_key"] for row in rows if row.get("channel_key")]
        selected_count = self.rtmp.select_channels(channel_keys)
        expected_count = len(channel_keys)
        if selected_count < expected_count:
            InfoBar.warning(
                t("desktop.start_selected_streams"),
                t("desktop.channels_without_output").format(count=expected_count - selected_count),
                parent=self,
                position=InfoBarPosition.TOP,
            )
        self.switchTo(self.rtmp)

    def _open_rtmp_limit_settings(self):
        self.switchTo(self.settings)
        self.settings.focus_setting("rtmp_max_streams")
        InfoBar.info(
            t("desktop.adjust_concurrency_limit"),
            t("desktop.concurrency_limit_restart_notice"),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=8000,
        )

    def _update_finished(self):
        if self._update_activity_state == "failed":
            self._set_update_navigation_status("failed")
        elif self._update_activity_state == "stopping":
            self._set_update_navigation_status("cancelled")
        else:
            self._set_update_navigation_status("completed")
        self.dashboard.set_running(False)
        self.dashboard.refresh_metrics()
        self.channels.reload()
        self.rtmp.reload_channels()
        self.operation_controller.resume()

    def _start_service(self):
        if config.open_rtmp and not config.rtmp_available:
            if self._install_rtmp_from_ui(start_service=True):
                return
            InfoBar.warning(
                t("name.error"),
                t("msg.rtmp_unavailable_fallback"),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=-1,
            )
        self.service_controller.start()

    def _install_rtmp_from_ui(self, start_service=False):
        dialog = QDialog(self)
        dialog.setWindowTitle(t("name.error"))
        dialog.setWindowIcon(self.windowIcon())
        layout = QVBoxLayout(dialog)
        logo = QLabel(dialog)
        logo.setPixmap(self.windowIcon().pixmap(64, 64))
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        message = QLabel(t("msg.rtmp_install_confirm"), dialog)
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(logo)
        layout.addWidget(message)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self._start_service_after_rtmp_install = start_service
        self.rtmp.set_installing(True)
        self._append_runtime_log(f"{t('msg.rtmp_installing')}\n")
        threading.Thread(
            target=lambda: self.rtmp_install_finished.emit(
                install_rtmp_runtime(self.rtmp_install_output.emit)
            ),
            daemon=True,
        ).start()
        return True

    def _finish_rtmp_install(self, result: dict):
        self.rtmp.set_installing(False)
        if result.get("available"):
            self._append_runtime_log(f"{t('msg.rtmp_install_success')}\n")
            InfoBar.success(
                t("desktop.rtmp_service"),
                t("msg.rtmp_install_success"),
                parent=self,
                position=InfoBarPosition.TOP,
            )
        else:
            self._mark_logs_error()
            info = result.get("output") or t(
                f"msg.rtmp_{result.get('error_code')}", result.get("error_code")
            ) or t("desktop.unknown")
            self._append_runtime_log(f"{t('msg.rtmp_install_failed').format(info=info[-1000:])}\n")
            InfoBar.error(
                t("name.error"),
                t("msg.rtmp_install_failed").format(info=info[-1000:]),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=-1,
            )
        self.rtmp_controller.refresh()
        if getattr(self, "_start_service_after_rtmp_install", False):
            self._start_service_after_rtmp_install = False
            self.service_controller.start()
        elif result.get("available") and self.service_controller.owns_process:
            self.service_controller.stop()
            self.service_controller.start()

    def _append_runtime_log(self, content: str):
        self._on_runtime_output(content)
        os.makedirs(os.path.dirname(constants.log_path), exist_ok=True)
        with open(constants.log_path, "a", encoding="utf-8") as file:
            file.write(content)

    def _on_runtime_output(self, content: str):
        self.logs.append_runtime(content)

    def _mark_logs_error(self):
        self._set_navigation_status(
            "logs",
            FluentIcon.CANCEL,
            "#DC2626",
            "desktop.nav_runtime_error",
            dismiss_on_visit=True,
        )

    def _service_status_changed(self, status: str):
        self.dashboard.set_service_status(status)
        if status == "failed":
            self._mark_logs_error()

    def _update_rtmp_navigation_status(self, snapshot: dict):
        active_count = max(0, int(snapshot.get("active_count") or 0))
        starting_count = max(0, int(snapshot.get("starting_count") or 0))
        if active_count:
            self._set_navigation_status(
                "rtmp",
                FluentIcon.PLAY,
                "#059669",
                "desktop.nav_streaming",
                {"count": active_count},
            )
        elif starting_count:
            self._set_navigation_status(
                "rtmp",
                FluentIcon.SYNC,
                "#2563EB",
                "desktop.nav_stream_starting",
                {"count": starting_count},
            )
        else:
            self._clear_navigation_status("rtmp")

    def _update_about_navigation_status(self, state: str, payload):
        payload = payload if isinstance(payload, dict) else {}
        if state == "checking":
            self._set_navigation_status(
                "about", FluentIcon.SYNC, "#2563EB", "desktop.nav_checking_version",
            )
        elif state == "available":
            self._set_navigation_status(
                "about",
                FluentIcon.DOWNLOAD,
                "#D97706",
                "desktop.nav_version_available",
                {"version": payload.get("version", "")},
            )
        elif state == "downloading":
            self._set_navigation_status(
                "about", FluentIcon.DOWNLOAD, "#2563EB", "desktop.nav_downloading_update",
            )
        elif state == "downloaded":
            self._set_navigation_status(
                "about",
                FluentIcon.COMPLETED,
                "#059669",
                "desktop.nav_update_downloaded",
                dismiss_on_visit=True,
            )
        elif state == "failed":
            self._set_navigation_status(
                "about",
                FluentIcon.CANCEL,
                "#DC2626",
                "desktop.nav_version_check_failed",
                dismiss_on_visit=True,
            )
        else:
            self._clear_navigation_status("about")

    def _start_update(self):
        if self.operation_controller.is_busy:
            InfoBar.warning(t("desktop.task_running"), t("desktop.wait_for_task"), parent=self, position=InfoBarPosition.TOP)
            return
        self.controller.start()

    def _update_started(self):
        self._set_update_navigation_status("running")
        self.operation_controller.suspend()
        self.dashboard.set_running(True)

    def _update_failed(self, message: str):
        self._set_update_navigation_status("failed")
        self._mark_logs_error()
        InfoBar.error(t("desktop.update_failed"), message.splitlines()[-1] if message else t("name.error"), parent=self, position=InfoBarPosition.TOP, duration=8000)

    def _pause_update(self):
        self.controller.pause()
        self._set_update_navigation_status("paused")

    def _resume_update(self):
        self.controller.resume()
        self._set_update_navigation_status("running")

    def _cancel_update(self):
        self.controller.cancel()
        self._set_update_navigation_status("stopping")

    def _set_update_navigation_status(self, state: str):
        self._update_activity_state = state
        icon, color, key, dismiss = {
            "running": (FluentIcon.SYNC, "#2563EB", "desktop.nav_update_running", False),
            "paused": (FluentIcon.PAUSE, "#D97706", "desktop.nav_update_paused", False),
            "stopping": (FluentIcon.CLOSE, "#DC2626", "desktop.nav_update_stopping", False),
            "completed": (FluentIcon.COMPLETED, "#059669", "desktop.nav_update_completed", True),
            "cancelled": (FluentIcon.CANCEL, "#64748B", "desktop.nav_update_cancelled", True),
            "failed": (FluentIcon.CANCEL, "#DC2626", "desktop.nav_update_failed", True),
        }[state]
        self._set_navigation_status("dashboard", icon, color, key, dismiss_on_visit=dismiss)
        self._clear_navigation_status("tasks")

    def _operation_started(self, operation: str):
        self._set_navigation_status(
            "channels",
            FluentIcon.SYNC,
            "#7C3AED",
            "desktop.nav_channel_task_running",
            {"operation": t(f"desktop.{operation}", operation)},
        )
        self._clear_navigation_status("tasks")

    def _operation_succeeded(self, operation: str, _):
        args = {"operation": t(f"desktop.{operation}", operation)}
        self._set_navigation_status(
            "channels", FluentIcon.COMPLETED, "#059669",
            "desktop.nav_channel_task_completed", args, dismiss_on_visit=True,
        )
        self.channels.set_task_finished()
        self.dashboard.refresh_metrics()
        InfoBar.success(t("desktop.task_completed"), t(f"desktop.{operation}", operation), parent=self, position=InfoBarPosition.TOP)

    def _operation_failed(self, operation: str, message: str):
        self._mark_logs_error()
        args = {"operation": t(f"desktop.{operation}", operation)}
        self._set_navigation_status(
            "channels", FluentIcon.CANCEL, "#DC2626",
            "desktop.nav_channel_task_failed", args, dismiss_on_visit=True,
        )
        self.channels.set_task_finished()
        InfoBar.error(t("desktop.task_failed"), message.splitlines()[-1] if message else operation, parent=self, position=InfoBarPosition.TOP, duration=8000)

    def _stream_control_finished(self, action: str, success: bool, message: str):
        if success:
            InfoBar.success(t("desktop.stream_action_sent"), t(f"desktop.{action}_stream", action), parent=self, position=InfoBarPosition.TOP)
        else:
            self._mark_logs_error()
            InfoBar.error(t("desktop.stream_action_failed"), message or action, parent=self, position=InfoBarPosition.TOP)

    def _stream_batch_control_finished(self, action: str, success: int, total: int, message: str):
        if success == total:
            InfoBar.success(
                t("desktop.stream_action_sent"),
                t("desktop.batch_stream_action_success").format(count=success),
                parent=self,
                position=InfoBarPosition.TOP,
            )
        else:
            self._mark_logs_error()
            InfoBar.error(
                t("desktop.stream_action_failed"),
                t("desktop.batch_stream_action_partial").format(success=success, total=total, info=message),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=8000,
            )

    def shutdown(self):
        self._save_window_geometry()
        self.rtmp_controller.shutdown()
        self.service_controller.stop()
        self.operation_controller.shutdown()
        self.controller.shutdown()

    def closeEvent(self, event):
        if self._force_quit:
            event.accept()
            return
        if sys.platform == "win32" and self.tray and self.tray.isVisible():
            action = str(QSettings().value("behavior/windows_close_action", "ask"))
            if action == "ask":
                action = self._ask_windows_close_action()
            if action == "cancel":
                event.ignore()
                return
            if action == "quit":
                self._force_quit = True
                event.accept()
                QTimer.singleShot(0, QApplication.quit)
                return
            self.hide()
            event.ignore()
            return
        if self.tray and self.tray.isVisible():
            self.hide()
            event.ignore()
            if sys.platform == "darwin":
                QTimer.singleShot(0, lambda: set_macos_activation_policy(True))
            return
        super().closeEvent(event)

    def _ask_windows_close_action(self):
        dialog = QMessageBox(QMessageBox.Icon.Question, t("desktop.close_window"), t("desktop.close_window_prompt"), parent=self)
        minimize_button = dialog.addButton(t("desktop.minimize_to_tray"), QMessageBox.ButtonRole.AcceptRole)
        quit_button = dialog.addButton(t("desktop.quit_app"), QMessageBox.ButtonRole.DestructiveRole)
        dialog.addButton(t("desktop.cancel"), QMessageBox.ButtonRole.RejectRole)
        remember = QCheckBox(t("desktop.remember_close_action"), dialog)
        dialog.setCheckBox(remember)
        dialog.exec()
        clicked = dialog.clickedButton()
        action = "tray" if clicked is minimize_button else "quit" if clicked is quit_button else "cancel"
        if remember.isChecked() and action in {"tray", "quit"}:
            QSettings().setValue("behavior/windows_close_action", action)
        return action
