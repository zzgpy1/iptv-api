from collections import deque
from datetime import datetime

from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis
from PySide6.QtCore import QDateTime, Signal, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QHBoxLayout, QSizePolicy, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, PrimaryPushButton, PushButton, ScrollArea, TableView, isDarkTheme, qconfig

from desktop_ui.models import MappingTableModel
from desktop_ui.widgets import MetricCard, PageTitle, metric_row
from utils.i18n import t


def _stream_state(value, _):
    return t("desktop.stream_active") if value == "active" else t("desktop.stream_idle")


def _client_state(value, _):
    return t("desktop.client_publishing") if value == "publishing" else t("desktop.client_playing")


class RtmpPage(QWidget):
    refresh_requested = Signal()
    stream_control_requested = Signal(str, str)
    install_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rtmpPage")
        self.samples = deque(maxlen=300)
        self._available = False
        self._snapshot_received = False
        self._error_code = None
        self._error = ""
        self._installing = False
        self.status_card = MetricCard(t("desktop.rtmp_service"), t("desktop.unknown"))
        self.stream_card = MetricCard(t("desktop.active_streams"), "0")
        self.client_card = MetricCard(t("desktop.clients"), "0")
        self.bandwidth_card = MetricCard(t("desktop.output_bandwidth"), "0 Kbit/s")
        self.refresh_button = PushButton(FluentIcon.SYNC, t("desktop.refresh"), self)
        self.install_button = PrimaryPushButton(FluentIcon.DOWNLOAD, t("desktop.install_nginx_rtmp"), self)
        self.install_button.hide()
        self.stop_button = PushButton(FluentIcon.PAUSE_BOLD, t("desktop.stop_stream"), self)
        self.restart_button = PushButton(FluentIcon.ROTATE, t("desktop.restart_stream"), self)
        self.stream_model = MappingTableModel(self._stream_columns(), self)
        self.client_model = MappingTableModel(self._client_columns(), self)
        self.table = TableView(self)
        self.table.setModel(self.stream_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.setMinimumHeight(70)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.client_table = TableView(self)
        self.client_table.setModel(self.client_model)
        self.client_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.client_table.verticalHeader().setVisible(False)
        self.client_table.setBorderVisible(True)
        self.client_table.setBorderRadius(8)
        self.client_table.setMinimumHeight(60)
        self.client_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.client_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.client_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.series = QLineSeries(self)
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.chart.legend().hide()
        self.chart.setTitle(t("desktop.bandwidth_trend"))
        self.time_axis = QDateTimeAxis()
        self.time_axis.setFormat("HH:mm:ss")
        self.time_axis.setTickCount(6)
        self.value_axis = QValueAxis()
        self.value_axis.setLabelFormat("%.0f")
        self.value_axis.setTitleText("Kbit/s")
        self.chart.addAxis(self.time_axis, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.value_axis, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.time_axis)
        self.series.attachAxis(self.value_axis)
        self.chart_view = QChartView(self.chart, self)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(180)
        self.chart_view.setMaximumHeight(240)
        self.chart_view.setStyleSheet("background: transparent; border: none;")
        self.error_label = BodyLabel("", self)
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.install_button)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.restart_button)
        actions.addWidget(self.stop_button)
        tables = QSplitter(Qt.Orientation.Vertical, self)
        tables.addWidget(self.table)
        client_container = QWidget(self)
        client_layout = QVBoxLayout(client_container)
        client_layout.setContentsMargins(0, 0, 0, 0)
        self.client_details_title = BodyLabel(t("desktop.client_details"), client_container)
        client_layout.addWidget(self.client_details_title)
        client_layout.addWidget(self.client_table)
        client_container.setMinimumHeight(90)
        tables.addWidget(client_container)
        tables.setStretchFactor(0, 2)
        tables.setStretchFactor(1, 1)
        tables.setMinimumHeight(170)
        self.content = QWidget(self)
        self.content.setObjectName("rtmpContent")
        self.content.setMinimumHeight(680)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        self.title = PageTitle(FluentIcon.IOT, t("desktop.rtmp_monitor"), self)
        layout.addWidget(self.title)
        layout.addWidget(self.error_label)
        layout.addWidget(metric_row([self.status_card, self.stream_card, self.client_card, self.bandwidth_card]))
        layout.addLayout(actions)
        layout.addWidget(self.chart_view)
        layout.addWidget(tables, 1)
        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.content)
        self.scroll.setStyleSheet("QScrollArea { border: none; }")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.scroll)
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.install_button.clicked.connect(self.install_requested)
        self.stop_button.clicked.connect(lambda: self._request_control("stop"))
        self.restart_button.clicked.connect(lambda: self._request_control("restart"))
        self.table.selectionModel().selectionChanged.connect(self._stream_changed)
        qconfig.themeChanged.connect(self._apply_chart_theme)
        qconfig.themeChangedFinished.connect(self._apply_chart_theme)
        self._apply_chart_theme()

    @staticmethod
    def _stream_columns():
        return [
            ("state", t("desktop.status"), _stream_state),
            ("channel_name", t("name.channel"), None),
            ("clients", t("desktop.clients"), None),
            ("bw_out", t("desktop.output_bandwidth"), lambda value, _: f"{float(value or 0) / 1000:.1f} Kbit/s"),
            ("resolution", t("name.resolution"), None),
            ("video_codec", t("name.video_codec"), None),
            ("fps", t("name.fps"), None),
            ("uptime", t("desktop.uptime"), None),
        ]

    @staticmethod
    def _client_columns():
        return [
            ("state", t("desktop.status"), _client_state),
            ("address", t("desktop.client_address"), None),
            ("dropped", t("desktop.dropped_frames"), None),
            ("av_sync", t("desktop.av_sync"), None),
            ("uptime", t("desktop.uptime"), None),
        ]

    def set_snapshot(self, snapshot: dict):
        self._snapshot_received = True
        streams = snapshot.get("streams", [])
        clients = sum(int(stream.get("clients") or 0) for stream in streams)
        bw_out = float(snapshot.get("bw_out") or sum(float(stream.get("bw_out") or 0) for stream in streams))
        available = bool(snapshot.get("available"))
        self._available = available
        self._error_code = snapshot.get("error_code")
        self._error = snapshot.get("error") or ""
        self.status_card.set_value(t("desktop.running") if available else t("desktop.unavailable"))
        if available:
            self.error_label.hide()
            self.install_button.hide()
        else:
            error_code = snapshot.get("error_code")
            message = t(f"desktop.rtmp_error_{error_code}", snapshot.get("error") or t("desktop.rtmp_unavailable_hint"))
            self.error_label.setText(message)
            self.error_label.show()
            self.install_button.setVisible(error_code in {"nginx_missing", "rtmp_module_missing"})
        self.stream_card.set_value(len(streams))
        self.client_card.set_value(clients)
        self.bandwidth_card.set_value(f"{bw_out / 1000:.1f} Kbit/s")
        self.stream_model.set_rows(streams)
        if available:
            now = datetime.now().timestamp() * 1000
            self.samples.append((now, bw_out / 1000))
        self.series.clear()
        for timestamp, value in self.samples:
            self.series.append(timestamp, value)
        if self.samples:
            self.time_axis.setRange(QDateTime.fromMSecsSinceEpoch(int(self.samples[0][0])), QDateTime.fromMSecsSinceEpoch(int(self.samples[-1][0] + 1000)))
        self.value_axis.setRange(0, max(10, max((value for _, value in self.samples), default=0) * 1.15))

    def set_installing(self, installing: bool):
        self._installing = installing
        self.install_button.setEnabled(not installing)
        self.install_button.setText(
            t("desktop.installing_nginx_rtmp") if installing else t("desktop.install_nginx_rtmp")
        )

    def retranslate(self):
        self.title.setText(t("desktop.rtmp_monitor"))
        self.client_details_title.setText(t("desktop.client_details"))
        self.status_card.title_label.setText(t("desktop.rtmp_service"))
        self.stream_card.title_label.setText(t("desktop.active_streams"))
        self.client_card.title_label.setText(t("desktop.clients"))
        self.bandwidth_card.title_label.setText(t("desktop.output_bandwidth"))
        self.refresh_button.setText(t("desktop.refresh"))
        self.stop_button.setText(t("desktop.stop_stream"))
        self.restart_button.setText(t("desktop.restart_stream"))
        self.set_installing(self._installing)
        self.chart.setTitle(t("desktop.bandwidth_trend"))
        self.stream_model.set_columns(self._stream_columns())
        self.client_model.set_columns(self._client_columns())
        if self._snapshot_received:
            self.status_card.set_value(t("desktop.running") if self._available else t("desktop.unavailable"))
        if self._snapshot_received and not self._available:
            self.error_label.setText(t(
                f"desktop.rtmp_error_{self._error_code}",
                self._error or t("desktop.rtmp_unavailable_hint"),
            ))

    def _apply_chart_theme(self):
        dark = isDarkTheme()
        background = QColor("#202124" if dark else "#FFFFFF")
        page_background = QColor("#202124" if dark else "#F3F3F3")
        text = QColor("#F8FAFC" if dark else "#1E293B")
        grid = QColor("#475569" if dark else "#D7DEE8")
        line = QColor("#2DD4BF" if dark else "#0F766E")
        self.chart.setBackgroundBrush(QBrush(background))
        self.chart.setPlotAreaBackgroundBrush(QBrush(background))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.setTitleBrush(QBrush(text))
        self.chart_view.setBackgroundBrush(QBrush(page_background))
        self.chart_view.setStyleSheet("border: none;")
        for widget in (self, self.content, self.scroll.viewport(), self.chart_view.viewport()):
            palette = widget.palette()
            palette.setColor(QPalette.ColorRole.Window, page_background)
            palette.setColor(QPalette.ColorRole.Base, page_background)
            widget.setPalette(palette)
            widget.setAutoFillBackground(True)
        self.series.setPen(QPen(line, 2.2))
        for axis in (self.time_axis, self.value_axis):
            axis.setLabelsBrush(QBrush(text))
            axis.setTitleBrush(QBrush(text))
            axis.setGridLinePen(QPen(grid, 1))
            axis.setLinePen(QPen(grid, 1))
        self.chart_view.viewport().update()

    def _stream_changed(self, selected, _):
        indexes = selected.indexes()
        row = self.stream_model.row(indexes[0]) if indexes else None
        self.client_model.set_rows(row.get("client_details", []) if row else [])

    def _request_control(self, action: str):
        indexes = self.table.selectionModel().selectedRows()
        row = self.stream_model.row(indexes[0]) if indexes else None
        if row:
            self.stream_control_requested.emit(action, row["result_key"])
