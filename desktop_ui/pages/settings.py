from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton, SearchLineEdit, SubtitleLabel, TableView

from desktop_ui.models import ConfigTableModel
from utils.i18n import t


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.model = ConfigTableModel(self)
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText(t("desktop.search_settings"))
        self.save_button = PrimaryPushButton(t("desktop.save_settings"), self)
        self.reload_button = PushButton(t("desktop.reload"), self)
        self.table = TableView(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 420)
        actions = QHBoxLayout()
        actions.addWidget(self.search, 1)
        actions.addWidget(self.reload_button)
        actions.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel(t("desktop.settings"), self))
        layout.addWidget(BodyLabel(t("desktop.settings_desc"), self))
        layout.addLayout(actions)
        layout.addWidget(self.table, 1)
        self.search.textChanged.connect(self.model.filter)
        self.reload_button.clicked.connect(self.model.reload)
        self.save_button.clicked.connect(self.save)

    def save(self):
        self.model.save()
        InfoBar.success(t("desktop.saved"), t("desktop.restart_hint"), parent=self, position=InfoBarPosition.TOP)
