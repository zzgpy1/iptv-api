import os

from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, FluentIcon, PrimaryPushButton, ProgressBar, PushButton, SubtitleLabel

import utils.constants as constants
from utils.channel_repository import list_categories, list_channels
from utils.i18n import t
from utils.tools import get_public_url
from desktop_ui.widgets import MetricCard, metric_row


class DashboardPage(QWidget):
    run_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashboardPage")
        self._running = False
        self.status_card = MetricCard(t("desktop.run_status"), t("desktop.idle"))
        self.channel_card = MetricCard(t("desktop.channels"), "0")
        self.valid_card = MetricCard(t("desktop.valid_results"), "0")
        self.service_card = MetricCard(t("desktop.service"), t("desktop.unknown"), get_public_url())

        self.title = SubtitleLabel(t("desktop.dashboard"), self)
        self.progress_card = CardWidget(self)
        progress_layout = QVBoxLayout(self.progress_card)
        progress_layout.setContentsMargins(18, 16, 18, 16)
        self.progress_title = BodyLabel(t("desktop.ready"), self.progress_card)
        self.progress = ProgressBar(self.progress_card)
        self.progress.setValue(0)
        actions = QHBoxLayout()
        self.run_button = PrimaryPushButton(FluentIcon.PLAY_SOLID, t("desktop.run_once"), self.progress_card)
        self.cancel_button = PushButton(FluentIcon.CANCEL, t("desktop.cancel"), self.progress_card)
        self.cancel_button.setEnabled(False)
        self.output_button = PushButton(FluentIcon.FOLDER, t("desktop.open_output"), self.progress_card)
        self.service_button = PushButton(FluentIcon.GLOBE, t("desktop.open_service"), self.progress_card)
        actions.addWidget(self.run_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        actions.addWidget(self.output_button)
        actions.addWidget(self.service_button)
        progress_layout.addWidget(self.progress_title)
        progress_layout.addWidget(self.progress)
        progress_layout.addLayout(actions)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(self.title)
        layout.addWidget(metric_row([self.status_card, self.channel_card, self.valid_card, self.service_card]))
        layout.addWidget(self.progress_card)
        layout.addStretch(1)

        self.run_button.clicked.connect(self.run_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.output_button.clicked.connect(self.open_output)
        self.service_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(get_public_url())))
        self.refresh_metrics()

    def refresh_metrics(self):
        try:
            categories = list_categories(constants.channel_results_path)
            channels = list_channels(constants.channel_results_path)
        except Exception:
            categories = []
            channels = []
        self.channel_card.set_value(len(channels), t("desktop.category_count").format(count=len(categories)))
        self.valid_card.set_value(sum(int(row.get("valid_results") or 0) for row in channels))

    def set_running(self, running: bool):
        self._running = running
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.status_card.set_value(t("desktop.running") if running else t("desktop.idle"))

    def set_progress(self, title: str, value: int, finished: bool = False):
        self.progress_title.setText(title)
        self.progress.setValue(max(0, min(100, int(value))))
        if finished:
            self.set_running(False)
            self.refresh_metrics()

    def set_service_status(self, status: str):
        label = {
            "running": t("desktop.running"),
            "external": t("desktop.external_service"),
            "stopped": t("desktop.stopped"),
            "failed": t("desktop.unavailable"),
        }.get(status, t("desktop.unknown"))
        self.service_card.set_value(label, get_public_url())

    def open_output(self):
        path = os.path.abspath(constants.output_dir)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
