import datetime
import os

import pytz
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QHBoxLayout, QStackedWidget, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget
from qfluentwidgets import Action, BodyLabel, CardWidget, ComboBox, DropDownPushButton, FluentIcon, IconWidget, ProgressBar, PushButton, RoundMenu, SearchLineEdit, StrongBodyLabel, TableView, isDarkTheme

import utils.constants as constants
from desktop_ui.models import ChannelLogoLoader, ChannelTableModel
from desktop_ui.widgets import AccentPushButton, DangerPushButton, MetricCard, PageTitle, metric_row, play_circle_icon
from utils.channel_repository import latest_successful_run, list_categories, list_channel_results, list_channels
from utils.config import config
from utils.i18n import t
from utils.tools import get_public_url, parse_times, resource_path


def _speed(value, _):
    return "--" if value is None else f"{float(value):.2f} M/s"


def _channel_status(value, _):
    return {
        "pending": t("desktop.status_pending"),
        "testing": t("desktop.status_testing"),
        "completed": t("desktop.status_completed"),
        "healthy": t("desktop.health_healthy"),
        "warning": t("desktop.health_warning"),
        "offline": t("desktop.health_offline"),
        "unknown": t("desktop.health_unknown"),
    }.get(value, value or "--")


def _updated_at(value, _):
    return "--" if not value else datetime.datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")


def _channel_logo(name, logo):
    if logo:
        return logo
    local_logo = os.path.join(resource_path(constants.channel_logo_path), f"{name}.{config.logo_type}")
    if os.path.isfile(local_logo):
        return local_logo
    if config.logo_url:
        return f"{config.logo_url.rstrip('/')}/{name}.{config.logo_type}"
    return None


class ChannelNamePlayDelegate(QStyledItemDelegate):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._icon = play_circle_icon()

    def paint(self, painter: QPainter, option, index):
        base_option = QStyleOptionViewItem(option)
        row = index.data(Qt.ItemDataRole.UserRole) or {}
        playable = bool(row.get("best_url") and int(row.get("valid_results") or 0) > 0)
        if playable:
            base_option.rect = base_option.rect.adjusted(0, 0, -42, 0)
        super().paint(painter, base_option, index)
        if not playable:
            return
        rect = self._button_rect(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#2563EB"))
        painter.drawRoundedRect(rect, 6, 6)
        self._icon.paint(painter, rect.adjusted(5, 2, -5, -2), Qt.AlignmentFlag.AlignCenter)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            row = index.data(Qt.ItemDataRole.UserRole) or {}
            if row.get("best_url") and int(row.get("valid_results") or 0) > 0 and self._button_rect(option.rect).contains(event.position().toPoint()):
                self._callback(row)
                return True
        return False

    @staticmethod
    def _button_rect(rect):
        size = min(30, rect.height() - 8)
        return rect.adjusted(rect.width() - size - 8, (rect.height() - size) // 2, -8, -(rect.height() - size) // 2)


class DashboardPage(QWidget):
    run_requested = Signal()
    cancel_requested = Signal()
    destination_requested = Signal(str)

    def __init__(self, parent=None, logo_loader: ChannelLogoLoader | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardPage")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._running = False
        self._service_status = "unknown"
        self._runtime_rows = []
        self._active_channel = None
        self.status_card = MetricCard(t("desktop.run_status"), t("desktop.idle"), icon=FluentIcon.UPDATE, accent="#2563EB")
        self.channel_card = MetricCard(t("desktop.channels"), "0", icon=FluentIcon.LIBRARY, accent="#7C3AED")
        self.valid_card = MetricCard(t("desktop.valid_results"), "0", icon=FluentIcon.COMPLETED, accent="#059669")
        self.service_card = MetricCard(t("desktop.service"), t("desktop.unknown"), get_public_url(), FluentIcon.GLOBE, accent="#EA580C")
        for card in (self.status_card, self.channel_card, self.valid_card, self.service_card):
            card.set_clickable()

        self.title = PageTitle(FluentIcon.HOME, t("desktop.dashboard"), self)
        self.progress_card = CardWidget(self)
        progress_layout = QVBoxLayout(self.progress_card)
        progress_layout.setContentsMargins(18, 16, 18, 16)
        progress_layout.setSpacing(10)
        self.progress_title = BodyLabel(t("desktop.ready"), self.progress_card)
        self.progress = ProgressBar(self.progress_card)
        self.progress.setValue(0)
        actions = QHBoxLayout()
        self.run_button = AccentPushButton(FluentIcon.POWER_BUTTON, t("desktop.run_once"), self.progress_card)
        self.cancel_button = DangerPushButton(FluentIcon.CLOSE, t("desktop.cancel"), self.progress_card)
        self.cancel_button.hide()
        self.output_button = PushButton(FluentIcon.FOLDER, t("desktop.open_output"), self.progress_card)
        self.service_button = DropDownPushButton(FluentIcon.GLOBE, t("desktop.browse_results"), self.progress_card)
        self._create_service_menu()
        actions.addWidget(self.run_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        actions.addWidget(self.output_button)
        actions.addWidget(self.service_button)
        progress_layout.addWidget(self.progress_title)
        progress_layout.addWidget(self.progress)
        progress_layout.addLayout(actions)

        self.channels_card = CardWidget(self)
        channel_layout = QVBoxLayout(self.channels_card)
        channel_layout.setContentsMargins(18, 16, 18, 16)
        channel_layout.setSpacing(8)
        self.channels_title = BodyLabel(t("desktop.channel_result_status"), self.channels_card)
        self.channel_search = SearchLineEdit(self.channels_card)
        self.channel_search.setPlaceholderText(t("desktop.search_channels"))
        self.channel_model = ChannelTableModel(self._channel_columns(), self, logo_loader=logo_loader)
        self.channel_table = TableView(self.channels_card)
        self.channel_table.setModel(self.channel_model)
        self.channel_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.channel_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.channel_table.verticalHeader().setVisible(False)
        self.channel_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.channel_table.setBorderVisible(False)
        self.channel_table.setIconSize(QSize(28, 28))
        self.play_delegate = ChannelNamePlayDelegate(self._play_channel, self.channel_table)
        self.channel_table.setItemDelegateForColumn(0, self.play_delegate)
        self.channel_stack = QStackedWidget(self.channels_card)
        self.channel_stack.addWidget(self.channel_table)
        self.empty_state = QWidget(self.channel_stack)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(20, 32, 20, 32)
        empty_layout.setSpacing(10)
        empty_layout.addStretch(1)
        self.empty_icon = IconWidget(FluentIcon.UPDATE.icon(color=QColor("#64748B")), self.empty_state)
        self.empty_icon.setFixedSize(46, 46)
        self.empty_title = StrongBodyLabel(t("desktop.channel_results_empty"), self.empty_state)
        self.empty_hint = BodyLabel(t("desktop.channel_results_empty_hint"), self.empty_state)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setStyleSheet(f"color: {'#94A3B8' if isDarkTheme() else '#64748B'}")
        empty_layout.addWidget(self.empty_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_hint)
        empty_layout.addStretch(1)
        self.channel_stack.addWidget(self.empty_state)
        channel_header = QHBoxLayout()
        channel_header.addWidget(self.channels_title)
        channel_header.addWidget(self.channel_search)
        self.channel_search.setMaximumWidth(320)
        channel_header.addStretch(1)
        channel_layout.addLayout(channel_header)
        channel_layout.addWidget(self.channel_stack, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(self.title)
        layout.addWidget(metric_row([self.status_card, self.channel_card, self.valid_card, self.service_card]))
        layout.addWidget(self.progress_card)
        layout.addWidget(self.channels_card, 1)

        self.run_button.clicked.connect(self.run_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.output_button.clicked.connect(self.open_output)
        self.channel_search.textChanged.connect(self._apply_runtime_rows)
        self.status_card.clicked.connect(lambda: self.destination_requested.emit("tasks"))
        self.channel_card.clicked.connect(lambda: self.destination_requested.emit("channels"))
        self.valid_card.clicked.connect(lambda: self.destination_requested.emit("channels"))
        self.service_card.clicked.connect(lambda: self.destination_requested.emit("rtmp"))
        self.schedule_timer = QTimer(self)
        self.schedule_timer.setInterval(30_000)
        self.schedule_timer.timeout.connect(self.refresh_schedule)
        self.schedule_timer.start()
        self.refresh_metrics()
        self.refresh_schedule()

    def _create_service_menu(self):
        self.service_menu = RoundMenu(parent=self)
        self.service_actions = []
        for key, route, icon in (
            ("desktop.result_all", "/", FluentIcon.GLOBE),
            ("desktop.result_content", "/content", FluentIcon.VIEW),
            ("desktop.result_ipv4", "/ipv4", FluentIcon.CONNECT),
            ("desktop.result_ipv6", "/ipv6", FluentIcon.CONNECT),
            ("desktop.result_hls", "/hls", FluentIcon.VIDEO),
            ("desktop.result_epg", "/epg/epg.xml", FluentIcon.CALENDAR),
        ):
            action = Action(icon, t(key), self, triggered=lambda _checked=False, value=route: self._open_service_route(value))
            self.service_actions.append((action, key))
            self.service_menu.addAction(action)
        self.service_button.setMenu(self.service_menu)

    @staticmethod
    def _channel_columns():
        return [
            ("name", t("name.channel"), None),
            ("category", t("desktop.categories"), None),
            ("display_status", t("desktop.test_status"), _channel_status),
            ("total_results", t("desktop.total_results"), None),
            ("valid_results", t("desktop.valid_results"), None),
            ("selected_results", t("desktop.output_results"), None),
            ("best_speed", t("name.max_speed"), _speed),
            ("max_resolution", t("name.max_resolution"), None),
            ("updated_at", t("desktop.updated_at"), _updated_at),
        ]

    def refresh_metrics(self):
        try:
            categories = list_categories(constants.channel_results_path)
            all_channels = list_channels(constants.channel_results_path)
        except Exception:
            categories = []
            all_channels = []
        self.channel_card.set_value(len(all_channels), t("desktop.category_count").format(count=len(categories)))
        self.valid_card.set_value(sum(int(row.get("valid_results") or 0) for row in all_channels), t("desktop.selected_count").format(
            count=sum(int(row.get("selected_results") or 0) for row in all_channels)
        ))
        if not self._running:
            self._runtime_rows = [{**row, "display_status": "completed"} for row in all_channels]
        self._apply_runtime_rows()

    def _apply_runtime_rows(self):
        term = self.channel_search.text().strip().lower()
        rows = [
            row for row in self._runtime_rows
            if not term or term in str(row.get("name", "")).lower() or term in str(row.get("category", "")).lower()
        ]
        self.channel_model.set_rows(rows)
        self.channel_stack.setCurrentWidget(self.channel_table if rows else self.empty_state)
        self.empty_title.setText(t("desktop.channel_results_no_match" if term else "desktop.channel_results_empty"))
        self.empty_hint.setText(t("desktop.channel_results_no_match_hint" if term else "desktop.channel_results_empty_hint"))
        self._scroll_to_active()

    def _scroll_to_active(self):
        if not self._active_channel:
            return
        row_index = next(
            (index for index, row in enumerate(self.channel_model.rows)
             if (row.get("category"), row.get("name")) == self._active_channel),
            -1,
        )
        if row_index >= 0:
            index = self.channel_model.index(row_index, 0)
            self.channel_table.setCurrentIndex(index)
            self.channel_table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def set_running(self, running: bool):
        self._running = running
        if running:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.run_button.setEnabled(not running)
        self.cancel_button.setVisible(running)
        self.status_card.set_value(t("desktop.running") if running else t("desktop.idle"))
        if running:
            self._active_channel = None
            self._apply_runtime_rows()
        else:
            self.refresh_metrics()

    def set_progress(self, title: str, value: int, finished: bool = False, metadata=None, _now=None):
        self.progress.setValue(max(0, min(100, int(value))))
        if isinstance(metadata, dict) and metadata.get("channel"):
            key = (metadata.get("category"), metadata["channel"])
            self._active_channel = key
            self.progress_title.setText(t("desktop.testing_channel").format(name=metadata["channel"]))
            self._update_runtime_row(key, metadata)
        elif not self._active_channel or not self._running:
            self.progress_title.setText(title)
        if finished:
            self.progress_title.setText(t("desktop.update_completed_gui"))

    def _update_runtime_row(self, key, metadata):
        if metadata.get("status") != "completed":
            return
        runtime_row = {
            "name": metadata.get("channel"),
            "category": metadata.get("category"),
            "display_status": "completed",
            "total_results": metadata.get("total_results", 0),
            "valid_results": metadata.get("valid_count", 0),
            "selected_results": None,
            "best_speed": metadata.get("best_speed"),
            "max_resolution": metadata.get("max_resolution"),
            "best_url": metadata.get("best_url"),
            "playable_results": metadata.get("playable_results", []),
            "updated_at": metadata.get("updated_at"),
            "logo": _channel_logo(metadata.get("channel"), metadata.get("logo")),
        }
        existing = next(
            (index for index, row in enumerate(self._runtime_rows)
             if (row.get("category"), row.get("name")) == key),
            -1,
        )
        if existing < 0:
            self._runtime_rows.append(runtime_row)
        else:
            self._runtime_rows[existing] = runtime_row
        self.channel_card.set_value(len(self._runtime_rows))
        self.valid_card.set_value(sum(int(row.get("valid_results") or 0) for row in self._runtime_rows))
        self._apply_runtime_rows()

    def set_service_status(self, status: str):
        self._service_status = status
        label = {
            "running": t("desktop.running"),
            "external": t("desktop.external_service"),
            "stopped": t("desktop.stopped"),
            "failed": t("desktop.unavailable"),
        }.get(status, t("desktop.unknown"))
        self.service_card.set_value(label, get_public_url())

    def _play_channel(self, row):
        results = list(row.get("playable_results") or [])
        if not results and row.get("channel_key"):
            try:
                results = [item for item in list_channel_results(constants.channel_results_path, row["channel_key"]) if item.get("valid") and item.get("url")]
            except Exception:
                results = []
        if len(results) == 1:
            QDesktopServices.openUrl(QUrl(results[0]["url"]))
            return
        if not results:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(t("desktop.choose_playback_source"))
        layout = QFormLayout(dialog)
        selector = ComboBox(dialog)
        for result in results:
            speed = _speed(result.get("speed"), result)
            resolution = result.get("resolution") or "--"
            selector.addItem(f"{speed} · {resolution} · {result['url']}", userData=result["url"])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.button(QDialogButtonBox.StandardButton.Open).setText(t("desktop.confirm"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("desktop.cancel"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(t("desktop.playback_source"), selector)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            QDesktopServices.openUrl(QUrl(selector.currentData()))

    def refresh_schedule(self):
        try:
            timezone = pytz.timezone(config.time_zone)
            now = datetime.datetime.now(timezone)
            times = parse_times(config.update_times)
            if config.update_mode == "time" and times:
                candidates = []
                for hour, minute in times:
                    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    candidates.append(candidate if candidate > now else candidate + datetime.timedelta(days=1))
                next_time = min(candidates)
            elif config.update_interval:
                run = latest_successful_run(constants.channel_results_path)
                base = datetime.datetime.fromtimestamp(float(run["finished_at"]), timezone) if run and run.get("finished_at") else now
                interval = datetime.timedelta(hours=config.update_interval)
                next_time = base + interval
                while next_time <= now:
                    next_time += interval
            else:
                self.status_card.detail_label.setText(t("desktop.schedule_disabled"))
                return
            self.status_card.detail_label.setText(t("desktop.next_update_time").format(time=next_time.strftime("%Y-%m-%d %H:%M:%S")))
        except Exception:
            self.status_card.detail_label.setText(t("desktop.schedule_unavailable"))

    def retranslate(self):
        self.title.setText(t("desktop.dashboard"))
        self.status_card.title_label.setText(t("desktop.run_status"))
        self.channel_card.title_label.setText(t("desktop.channels"))
        self.valid_card.title_label.setText(t("desktop.valid_results"))
        self.service_card.title_label.setText(t("desktop.service"))
        self.run_button.setText(t("desktop.run_once"))
        self.cancel_button.setText(t("desktop.cancel"))
        self.output_button.setText(t("desktop.open_output"))
        self.service_button.setText(t("desktop.browse_results"))
        self.channels_title.setText(t("desktop.channel_result_status"))
        self.channel_search.setPlaceholderText(t("desktop.search_channels"))
        self.empty_title.setText(t("desktop.channel_results_empty"))
        self.empty_hint.setText(t("desktop.channel_results_empty_hint"))
        self.channel_model.set_columns(self._channel_columns())
        for action, key in self.service_actions:
            action.setText(t(key))
        if not self._running and self.progress.value() == 0:
            self.progress_title.setText(t("desktop.ready"))
        self.set_service_status(self._service_status)
        self.refresh_metrics()
        self.refresh_schedule()

    def _open_service_route(self, route: str):
        QDesktopServices.openUrl(QUrl(f"{get_public_url().rstrip('/')}{route}"))

    def open_output(self):
        path = os.path.abspath(constants.output_dir)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
