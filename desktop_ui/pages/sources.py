import os

from PySide6.QtCore import QSaveFile, QIODevice
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, InfoBar, InfoBarPosition, PlainTextEdit, PrimaryPushButton, PushButton, SubtitleLabel

import utils.constants as constants
from utils.config import config, resource_path
from utils.i18n import t


class SourcesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sourcesPage")
        self.path_specs = [
            ("desktop.template", lambda: config.source_file),
            ("name.local", lambda: constants.local_path),
            ("name.subscribe", lambda: constants.subscribe_path),
            ("name.epg", lambda: constants.epg_path),
            ("name.whitelist", lambda: constants.whitelist_path),
            ("desktop.blacklist", lambda: constants.blacklist_path),
            ("desktop.alias", lambda: constants.alias_path),
        ]
        self.paths = [(t(key), path) for key, path in self.path_specs]
        self.selector = ComboBox(self)
        self.selector.addItems([item[0] for item in self.paths])
        self.editor = PlainTextEdit(self)
        self.editor.setLineWrapMode(PlainTextEdit.LineWrapMode.NoWrap)
        self.save_button = PrimaryPushButton(FluentIcon.SAVE, t("desktop.save"), self)
        self.reload_button = PushButton(FluentIcon.SYNC, t("desktop.reload"), self)
        actions = QHBoxLayout()
        actions.addWidget(self.selector)
        actions.addStretch(1)
        actions.addWidget(self.reload_button)
        actions.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        self.title = SubtitleLabel(t("desktop.sources"), self)
        layout.addWidget(self.title)
        layout.addLayout(actions)
        layout.addWidget(self.editor, 1)
        self.selector.currentIndexChanged.connect(self.load)
        self.reload_button.clicked.connect(self.load)
        self.save_button.clicked.connect(self.save)
        self.load()

    def current_path(self):
        index = max(0, self.selector.currentIndex())
        return resource_path(self.paths[index][1](), persistent=True)

    def load(self, *_):
        path = self.current_path()
        try:
            with open(path, "r", encoding="utf-8") as file:
                self.editor.setPlainText(file.read())
        except FileNotFoundError:
            self.editor.clear()

    def save(self):
        path = self.current_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        target = QSaveFile(path)
        if target.open(QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Text):
            target.write(self.editor.toPlainText().encode("utf-8"))
            if target.commit():
                InfoBar.success(t("desktop.saved"), path, parent=self, position=InfoBarPosition.TOP)
                return
        InfoBar.error(t("name.error"), target.errorString(), parent=self, position=InfoBarPosition.TOP)

    def retranslate(self):
        index = self.selector.currentIndex()
        self.paths = [(t(key), path) for key, path in self.path_specs]
        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.addItems([item[0] for item in self.paths])
        self.selector.setCurrentIndex(index)
        self.selector.blockSignals(False)
        self.title.setText(t("desktop.sources"))
        self.save_button.setText(t("desktop.save"))
        self.reload_button.setText(t("desktop.reload"))
