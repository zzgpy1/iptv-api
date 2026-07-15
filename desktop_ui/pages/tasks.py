from datetime import datetime

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton, SubtitleLabel, TableView

import utils.constants as constants
from desktop_ui.models import MappingTableModel
from utils.channel_repository import list_operations, list_runs
from utils.diagnostics import export_diagnostics
from utils.i18n import t


def _time(value, _):
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S") if value else "--"


def _status(value, _):
    return t(f"desktop.status_{value}", value or "--")


def _target_type(value, _):
    return t(f"desktop.target_{value}", value or "--")


class TasksPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tasksPage")
        self.run_model = MappingTableModel(self._run_columns(), self)
        self.operation_model = MappingTableModel(self._operation_columns(), self)
        self.run_table = self._table(self.run_model)
        self.operation_table = self._table(self.operation_model)
        splitter = QSplitter(self)
        splitter.addWidget(self.run_table)
        splitter.addWidget(self.operation_table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        self.refresh_button = PushButton(FluentIcon.SYNC, t("desktop.refresh"), self)
        self.export_button = PrimaryPushButton(FluentIcon.IMAGE_EXPORT, t("desktop.export_diagnostics"), self)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.export_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        self.title = SubtitleLabel(t("desktop.task_history"), self)
        layout.addWidget(self.title)
        layout.addLayout(actions)
        layout.addWidget(splitter, 1)
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button.clicked.connect(self.export)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    @staticmethod
    def _run_columns():
        return [
            ("started_at", t("desktop.started_at"), _time),
            ("finished_at", t("desktop.finished_at"), _time),
            ("status", t("desktop.status"), _status),
            ("error", t("name.error"), None),
        ]

    @staticmethod
    def _operation_columns():
        return [
            ("started_at", t("desktop.started_at"), _time),
            ("operation", t("desktop.operation"), lambda value, _: t(f"desktop.{value}", value or "--")),
            ("target_type", t("desktop.target"), _target_type),
            ("status", t("desktop.status"), _status),
            ("message", t("desktop.details"), None),
        ]

    def _table(self, model):
        table = TableView(self)
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.setBorderVisible(True)
        table.setBorderRadius(8)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(model.columnCount() - 1, QHeaderView.ResizeMode.Stretch)
        return table

    def refresh(self):
        try:
            self.run_model.set_rows(list_runs(constants.channel_results_path))
            self.operation_model.set_rows(list_operations(constants.channel_results_path))
        except Exception:
            self.run_model.set_rows([])
            self.operation_model.set_rows([])

    def export(self):
        try:
            path = export_diagnostics()
            InfoBar.success(t("desktop.diagnostics_exported"), path, parent=self, position=InfoBarPosition.TOP)
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as exc:
            InfoBar.error(t("desktop.diagnostics_failed"), str(exc), parent=self, position=InfoBarPosition.TOP)

    def retranslate(self):
        self.title.setText(t("desktop.task_history"))
        self.refresh_button.setText(t("desktop.refresh"))
        self.export_button.setText(t("desktop.export_diagnostics"))
        self.run_model.set_columns(self._run_columns())
        self.operation_model.set_columns(self._operation_columns())
