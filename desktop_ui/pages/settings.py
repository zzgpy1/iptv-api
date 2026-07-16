from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, PushButton, SearchLineEdit, TableView

from desktop_ui.delegates import ConfigValueDelegate, ElidedDescriptionDelegate
from desktop_ui.models import ConfigTableModel
from desktop_ui.widgets import AccentPushButton, PageTitle
from utils.i18n import t


class SettingsPage(QWidget):
    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.model = ConfigTableModel(self)
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText(t("desktop.search_settings"))
        self.save_button = AccentPushButton(FluentIcon.SAVE, t("desktop.save_settings"), self)
        self.reload_button = PushButton(FluentIcon.SYNC, t("desktop.reload"), self)
        self.table = TableView(self)
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(1, ConfigValueDelegate(self.table))
        self.table.setItemDelegateForColumn(2, ElidedDescriptionDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 420)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        actions = QHBoxLayout()
        actions.addWidget(self.search, 1)
        actions.addWidget(self.reload_button)
        actions.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        self.title = PageTitle(FluentIcon.SETTING, t("desktop.settings"), self)
        layout.addWidget(self.title)
        layout.addLayout(actions)
        layout.addWidget(self.table, 1)
        self.search.textChanged.connect(self.model.filter)
        self.reload_button.clicked.connect(self.model.reload)
        self.save_button.clicked.connect(self.save)
        self.model.modelReset.connect(lambda: QTimer.singleShot(0, self._open_editors))
        QTimer.singleShot(0, self._open_editors)

    def retranslate(self):
        self.title.setText(t("desktop.settings"))
        self.search.setPlaceholderText(t("desktop.search_settings"))
        self.save_button.setText(t("desktop.save_settings"))
        self.reload_button.setText(t("desktop.reload"))
        self.model.reload()

    def _open_editors(self):
        for row in range(self.model.rowCount()):
            index = self.model.index(row, 1)
            if index.flags() & Qt.ItemFlag.ItemIsEditable:
                self.table.openPersistentEditor(index)
        QTimer.singleShot(0, self._clear_editor_selection)

    def _clear_editor_selection(self):
        for editor in self.table.findChildren(QLineEdit):
            editor.setCursorPosition(0)
            editor.deselect()
            editor.clearFocus()
        self.table.clearSelection()
        self.search.setFocus(Qt.FocusReason.OtherFocusReason)

    def save(self):
        self.model.save()
        self.settings_saved.emit()
        InfoBar.success(t("desktop.saved"), t("desktop.restart_hint"), parent=self, position=InfoBarPosition.TOP)
