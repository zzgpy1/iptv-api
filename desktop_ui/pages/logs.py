import os

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, InfoBar, InfoBarPosition, LineEdit, PlainTextEdit, PushButton, SwitchButton

import utils.constants as constants
from desktop_ui.widgets import PageTitle
from utils.diagnostics import export_logs
from utils.i18n import t


class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logsPage")
        self.path_specs = [
            ("desktop.runtime_log", constants.log_path),
            ("desktop.result_log", constants.result_log_path),
            ("desktop.speed_log", constants.speed_test_log_path),
            ("desktop.statistics_log", constants.statistic_log_path),
            ("desktop.unmatched_log", constants.unmatch_log_path),
        ]
        self.paths = [(t(key), path) for key, path in self.path_specs]
        self.selector = ComboBox(self)
        self.selector.addItems([item[0] for item in self.paths])
        self.search = LineEdit(self)
        self.search.setPlaceholderText(t("desktop.search_logs"))
        self.autoscroll = SwitchButton(t("desktop.auto_scroll"), self)
        self.autoscroll.setChecked(True)
        self.refresh_button = PushButton(FluentIcon.SYNC, t("desktop.refresh"), self)
        self.clear_button = PushButton(FluentIcon.BROOM, t("desktop.clear_view"), self)
        self.export_button = PushButton(FluentIcon.ZIP_FOLDER, t("desktop.export_logs"), self)
        self.viewer = PlainTextEdit(self)
        self.viewer.setReadOnly(True)
        self.viewer.setLineWrapMode(PlainTextEdit.LineWrapMode.NoWrap)
        self.cleared_offsets = {}
        actions = QHBoxLayout()
        actions.addWidget(self.selector)
        actions.addWidget(self.search, 1)
        actions.addWidget(self.autoscroll)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.export_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        self.title = PageTitle(FluentIcon.COMMAND_PROMPT, t("desktop.logs"), self)
        layout.addWidget(self.title)
        layout.addLayout(actions)
        layout.addWidget(self.viewer, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.selector.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.refresh_button.clicked.connect(self.refresh)
        self.clear_button.clicked.connect(self.clear_view)
        self.export_button.clicked.connect(self.export)
        self.refresh()

    def refresh(self, *_):
        path = self.paths[max(0, self.selector.currentIndex())][1]
        if not os.path.exists(path):
            content = "" if path in self.cleared_offsets else t("msg.waiting_tip")
        else:
            size = os.path.getsize(path)
            offset = self.cleared_offsets.get(path, max(0, size - 1024 * 1024))
            if offset > size:
                offset = 0
                self.cleared_offsets[path] = 0
            with open(path, "rb") as file:
                file.seek(offset)
                content = file.read().decode("utf-8", errors="replace")
        term = self.search.text().strip().lower()
        if term:
            content = "\n".join(line for line in content.splitlines() if term in line.lower())
        if self.viewer.toPlainText() != content:
            self.viewer.setPlainText(content)
            if self.autoscroll.isChecked():
                self.viewer.verticalScrollBar().setValue(self.viewer.verticalScrollBar().maximum())

    def clear_view(self):
        path = self.paths[max(0, self.selector.currentIndex())][1]
        self.cleared_offsets[path] = os.path.getsize(path) if os.path.exists(path) else 0
        self.viewer.clear()

    def export(self):
        try:
            path = export_logs()
            InfoBar.success(t("desktop.logs_exported"), path, parent=self, position=InfoBarPosition.TOP)
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))
        except Exception as exc:
            InfoBar.error(t("desktop.logs_export_failed"), str(exc), parent=self, position=InfoBarPosition.TOP)

    def append_runtime(self, content: str):
        if self.selector.currentIndex() != 0 or self.search.text().strip():
            return
        text = content.rstrip()
        if not text:
            return
        self.viewer.appendPlainText(text)
        if self.autoscroll.isChecked():
            self.viewer.verticalScrollBar().setValue(self.viewer.verticalScrollBar().maximum())

    def retranslate(self):
        index = self.selector.currentIndex()
        self.paths = [(t(key), path) for key, path in self.path_specs]
        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.addItems([item[0] for item in self.paths])
        self.selector.setCurrentIndex(index)
        self.selector.blockSignals(False)
        self.title.setText(t("desktop.logs"))
        self.search.setPlaceholderText(t("desktop.search_logs"))
        self.autoscroll.setText(t("desktop.auto_scroll"))
        self.refresh_button.setText(t("desktop.refresh"))
        self.clear_button.setText(t("desktop.clear_view"))
        self.export_button.setText(t("desktop.export_logs"))
        self.refresh()
