from collections import deque
from datetime import datetime

from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis
from PySide6.QtCore import QDateTime, Signal, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, PushButton, SubtitleLabel, TableView

from desktop_ui.models import MappingTableModel
from desktop_ui.widgets import MetricCard, metric_row
from utils.i18n import t


def _stream_state(value, _):
    return t("desktop.stream_active") if value == "active" else t("desktop.stream_idle")


def _client_state(value, _):
    return t("desktop.client_publishing") if value == "publishing" else t("desktop.client_playing")


class RtmpPage(QWidget):
    refresh_requested = Signal()
    stream_control_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rtmpPage")
        self.samples = deque(maxlen=300)
        self.status_card = MetricCard(t("desktop.rtmp_service"), t("desktop.unknown"))
        self.stream_card = MetricCard(t("desktop.active_streams"), "0")
        self.client_card = MetricCard(t("desktop.clients"), "0")
        self.bandwidth_card = MetricCard(t("desktop.output_bandwidth"), "0 Kbit/s")
        self.refresh_button = PushButton(t("desktop.refresh"), self)
        self.stop_button = PushButton(t("desktop.stop_stream"), self)
        self.restart_button = PushButton(t("desktop.restart_stream"), self)
        self.stream_model = MappingTableModel([
            ("state", t("desktop.status"), _stream_state),
            ("channel_name", t("name.channel"), None),
            ("clients", t("desktop.clients"), None),
            ("bw_out", t("desktop.output_bandwidth"), lambda value, _: f"{float(value or 0) / 1000:.1f} Kbit/s"),
            ("resolution", t("name.resolution"), None),
            ("video_codec", t("name.video_codec"), None),
            ("fps", t("name.fps"), None),
            ("uptime", t("desktop.uptime"), None),
        ], self)
        self.client_model = MappingTableModel([
            ("state", t("desktop.status"), _client_state),
            ("address", t("desktop.client_address"), None),
            ("dropped", t("desktop.dropped_frames"), None),
            ("av_sync", t("desktop.av_sync"), None),
            ("uptime", t("desktop.uptime"), None),
        ], self)
        self.table = TableView(self)
        self.table.setModel(self.stream_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.client_table = TableView(self)
        self.client_table.setModel(self.client_model)
        self.client_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.client_table.verticalHeader().setVisible(False)
        self.client_table.setBorderVisible(True)
        self.client_table.setBorderRadius(8)

        self.series = QLineSeries(self)
        chart = QChart()
        chart.addSeries(self.series)
        chart.legend().hide()
        chart.setTitle(t("desktop.bandwidth_trend"))
        self.time_axis = QDateTimeAxis()
        self.time_axis.setFormat("HH:mm:ss")
        self.time_axis.setTickCount(6)
        self.value_axis = QValueAxis()
        self.value_axis.setLabelFormat("%.0f")
        self.value_axis.setTitleText("Kbit/s")
        chart.addAxis(self.time_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(self.value_axis, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.time_axis)
        self.series.attachAxis(self.value_axis)
        self.chart_view = QChartView(chart, self)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(220)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.restart_button)
        actions.addWidget(self.stop_button)
        tables = QSplitter(Qt.Orientation.Vertical, self)
        tables.addWidget(self.table)
        client_container = QWidget(self)
        client_layout = QVBoxLayout(client_container)
        client_layout.setContentsMargins(0, 0, 0, 0)
        client_layout.addWidget(BodyLabel(t("desktop.client_details"), client_container))
        client_layout.addWidget(self.client_table)
        tables.addWidget(client_container)
        tables.setStretchFactor(0, 2)
        tables.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel(t("desktop.rtmp_monitor"), self))
        layout.addWidget(BodyLabel(t("desktop.rtmp_monitor_desc"), self))
        layout.addWidget(metric_row([self.status_card, self.stream_card, self.client_card, self.bandwidth_card]))
        layout.addWidget(self.chart_view)
        layout.addLayout(actions)
        layout.addWidget(tables, 1)
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.stop_button.clicked.connect(lambda: self._request_control("stop"))
        self.restart_button.clicked.connect(lambda: self._request_control("restart"))
        self.table.selectionModel().selectionChanged.connect(self._stream_changed)

    def set_snapshot(self, snapshot: dict):
        streams = snapshot.get("streams", [])
        clients = sum(int(stream.get("clients") or 0) for stream in streams)
        bw_out = float(snapshot.get("bw_out") or sum(float(stream.get("bw_out") or 0) for stream in streams))
        self.status_card.set_value(t("desktop.running") if snapshot.get("available") else t("desktop.unavailable"))
        self.stream_card.set_value(len(streams))
        self.client_card.set_value(clients)
        self.bandwidth_card.set_value(f"{bw_out / 1000:.1f} Kbit/s")
        self.stream_model.set_rows(streams)
        now = datetime.now().timestamp() * 1000
        self.samples.append((now, bw_out / 1000))
        self.series.clear()
        for timestamp, value in self.samples:
            self.series.append(timestamp, value)
        if self.samples:
            self.time_axis.setRange(QDateTime.fromMSecsSinceEpoch(int(self.samples[0][0])), QDateTime.fromMSecsSinceEpoch(int(self.samples[-1][0] + 1000)))
        self.value_axis.setRange(0, max(10, max((value for _, value in self.samples), default=0) * 1.15))

    def _stream_changed(self, selected, _):
        indexes = selected.indexes()
        row = self.stream_model.row(indexes[0]) if indexes else None
        self.client_model.set_rows(row.get("client_details", []) if row else [])

    def _request_control(self, action: str):
        indexes = self.table.selectionModel().selectedRows()
        row = self.stream_model.row(indexes[0]) if indexes else None
        if row:
            self.stream_control_requested.emit(action, row["result_key"])
