import os

from PySide6.QtCore import QSize, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import Action, BodyLabel, CardWidget, DropDownPushButton, FluentIcon, PrimaryPushButton, ProgressBar, PushButton, RoundMenu, SearchLineEdit, TableView

import utils.constants as constants
from desktop_ui.models import ChannelLogoLoader, ChannelTableModel
from desktop_ui.widgets import MetricCard, PageTitle, metric_row
from utils.channel_repository import list_categories, list_channels
from utils.i18n import t
from utils.tools import get_public_url


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


class DashboardPage(QWidget):
    run_requested = Signal()
    cancel_requested = Signal()
    destination_requested = Signal(str)

    def __init__(self, parent=None, logo_loader: ChannelLogoLoader | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardPage")
        self._running = False
        self._service_status = "unknown"
        self._runtime_status = {}
        self._active_channel = None
        self.status_card = MetricCard(t("desktop.run_status"), t("desktop.idle"), icon=FluentIcon.UPDATE)
        self.channel_card = MetricCard(t("desktop.channels"), "0", icon=FluentIcon.LIBRARY)
        self.valid_card = MetricCard(t("desktop.valid_results"), "0", icon=FluentIcon.COMPLETED)
        self.service_card = MetricCard(t("desktop.service"), t("desktop.unknown"), get_public_url(), FluentIcon.GLOBE)
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
        self.run_button = PrimaryPushButton(FluentIcon.PLAY_SOLID, t("desktop.run_once"), self.progress_card)
        self.cancel_button = PushButton(FluentIcon.CLOSE, t("desktop.cancel"), self.progress_card)
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
        channel_header = QHBoxLayout()
        channel_header.addWidget(self.channels_title)
        channel_header.addStretch(1)
        channel_header.addWidget(self.channel_search)
        channel_layout.addLayout(channel_header)
        channel_layout.addWidget(self.channel_table, 1)

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
        self.channel_search.textChanged.connect(self.refresh_metrics)
        self.status_card.clicked.connect(lambda: self.destination_requested.emit("tasks"))
        self.channel_card.clicked.connect(lambda: self.destination_requested.emit("channels"))
        self.valid_card.clicked.connect(lambda: self.destination_requested.emit("channels"))
        self.service_card.clicked.connect(lambda: self.destination_requested.emit("rtmp"))
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1500)
        self.refresh_timer.timeout.connect(self.refresh_metrics)
        self.refresh_metrics()

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
        ]

    def refresh_metrics(self):
        try:
            categories = list_categories(constants.channel_results_path)
            all_channels = list_channels(constants.channel_results_path)
            channels = list_channels(constants.channel_results_path, search=self.channel_search.text())
        except Exception:
            categories = []
            all_channels = []
            channels = []
        rows = []
        for row in channels:
            key = (row.get("category"), row.get("name"))
            runtime = self._runtime_status.get(key)
            rows.append({
                **row,
                "display_status": runtime.get("status") if runtime else "pending" if self._running else row.get("health"),
                "valid_results": max(int(row.get("valid_results") or 0), int((runtime or {}).get("valid_count") or 0)),
            })
        self.channel_card.set_value(len(all_channels), t("desktop.category_count").format(count=len(categories)))
        self.valid_card.set_value(sum(int(row.get("valid_results") or 0) for row in all_channels), t("desktop.selected_count").format(
            count=sum(int(row.get("selected_results") or 0) for row in all_channels)
        ))
        self.channel_model.set_rows(rows)
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
        self.run_button.setEnabled(not running)
        self.cancel_button.setVisible(running)
        self.status_card.set_value(t("desktop.running") if running else t("desktop.idle"))
        if running:
            self._runtime_status = {}
            self._active_channel = None
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()
        else:
            self.refresh_timer.stop()
        self.refresh_metrics()

    def set_progress(self, title: str, value: int, finished: bool = False, metadata=None, _now=None):
        self.progress.setValue(max(0, min(100, int(value))))
        if isinstance(metadata, dict) and metadata.get("channel"):
            key = (metadata.get("category"), metadata["channel"])
            self._active_channel = key
            self._runtime_status[key] = metadata
            self.progress_title.setText(t("desktop.testing_channel").format(name=metadata["channel"]))
            self._update_runtime_row(key, metadata)
        elif not self._active_channel or not self._running:
            self.progress_title.setText(title)
        if finished:
            self.progress_title.setText(t("desktop.update_completed_gui"))
            self.set_running(False)

    def _update_runtime_row(self, key, metadata):
        row_index = next(
            (index for index, row in enumerate(self.channel_model.rows)
             if (row.get("category"), row.get("name")) == key),
            -1,
        )
        if row_index < 0:
            return
        row = self.channel_model.rows[row_index]
        row["display_status"] = metadata.get("status")
        row["valid_results"] = max(int(row.get("valid_results") or 0), int(metadata.get("valid_count") or 0))
        self.channel_model.dataChanged.emit(
            self.channel_model.index(row_index, 0),
            self.channel_model.index(row_index, self.channel_model.columnCount() - 1),
        )
        self._scroll_to_active()

    def set_service_status(self, status: str):
        self._service_status = status
        label = {
            "running": t("desktop.running"),
            "external": t("desktop.external_service"),
            "stopped": t("desktop.stopped"),
            "failed": t("desktop.unavailable"),
        }.get(status, t("desktop.unknown"))
        self.service_card.set_value(label, get_public_url())

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
        self.channel_model.set_columns(self._channel_columns())
        for action, key in self.service_actions:
            action.setText(t(key))
        if not self._running and self.progress.value() == 0:
            self.progress_title.setText(t("desktop.ready"))
        self.set_service_status(self._service_status)
        self.refresh_metrics()

    def _open_service_route(self, route: str):
        QDesktopServices.openUrl(QUrl(f"{get_public_url().rstrip('/')}{route}"))

    def open_output(self):
        path = os.path.abspath(constants.output_dir)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
