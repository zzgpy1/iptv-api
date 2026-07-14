import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, LineEdit, PlainTextEdit, PushButton, SubtitleLabel, SwitchButton

import utils.constants as constants
from utils.i18n import t


class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logsPage")
        self.paths = [
            (t("desktop.runtime_log"), constants.log_path),
            (t("desktop.result_log"), constants.result_log_path),
            (t("desktop.speed_log"), constants.speed_test_log_path),
            (t("desktop.statistics_log"), constants.statistic_log_path),
            (t("desktop.unmatched_log"), constants.unmatch_log_path),
        ]
        self.selector = ComboBox(self)
        self.selector.addItems([item[0] for item in self.paths])
        self.search = LineEdit(self)
        self.search.setPlaceholderText(t("desktop.search_logs"))
        self.autoscroll = SwitchButton(t("desktop.auto_scroll"), self)
        self.autoscroll.setChecked(True)
        self.refresh_button = PushButton(FluentIcon.SYNC, t("desktop.refresh"), self)
        self.clear_button = PushButton(FluentIcon.BROOM, t("desktop.clear_view"), self)
        self.viewer = PlainTextEdit(self)
        self.viewer.setReadOnly(True)
        self.viewer.setLineWrapMode(PlainTextEdit.LineWrapMode.NoWrap)
        actions = QHBoxLayout()
        actions.addWidget(self.selector)
        actions.addWidget(self.search, 1)
        actions.addWidget(self.autoscroll)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.clear_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel(t("desktop.logs"), self))
        layout.addLayout(actions)
        layout.addWidget(self.viewer, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.selector.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.refresh_button.clicked.connect(self.refresh)
        self.clear_button.clicked.connect(self.viewer.clear)
        self.refresh()

    def refresh(self, *_):
        path = self.paths[max(0, self.selector.currentIndex())][1]
        if not os.path.exists(path):
            content = t("msg.waiting_tip")
        else:
            with open(path, "r", encoding="utf-8", errors="replace") as file:
                file.seek(max(0, os.path.getsize(path) - 1024 * 1024))
                content = file.read()
        term = self.search.text().strip().lower()
        if term:
            content = "\n".join(line for line in content.splitlines() if term in line.lower())
        if self.viewer.toPlainText() != content:
            self.viewer.setPlainText(content)
            if self.autoscroll.isChecked():
                self.viewer.verticalScrollBar().setValue(self.viewer.verticalScrollBar().maximum())

    def append_runtime(self, content: str):
        if self.selector.currentIndex() != 0 or self.search.text().strip():
            return
        text = content.rstrip()
        if not text:
            return
        self.viewer.appendPlainText(text)
        if self.autoscroll.isChecked():
            self.viewer.verticalScrollBar().setValue(self.viewer.verticalScrollBar().maximum())
