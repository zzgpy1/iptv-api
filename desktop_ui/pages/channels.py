from PySide6.QtCore import QItemSelection, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QListWidget, QListWidgetItem, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton, SearchLineEdit, SubtitleLabel, TableView

import utils.constants as constants
from desktop_ui.models import MappingTableModel
from utils.channel_repository import list_categories, list_channel_results, list_channels
from utils.i18n import t


def _health(value, _):
    return {
        "healthy": t("desktop.health_healthy"),
        "warning": t("desktop.health_warning"),
        "offline": t("desktop.health_offline"),
        "unknown": t("desktop.health_unknown"),
    }.get(value, value or "--")


def _speed(value, _):
    return "--" if value is None else f"{float(value):.2f} M/s"


def _delay(value, _):
    return "--" if value is None else f"{float(value):.0f} ms"


class ChannelCenterPage(QWidget):
    retest_channel_requested = Signal(dict)
    retest_result_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("channelCenterPage")
        self.category_list = QListWidget(self)
        self.category_list.setMinimumWidth(190)
        self.category_list.setMaximumWidth(260)
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText(t("desktop.search_channels"))
        self.refresh_button = PushButton(t("desktop.refresh"), self)
        self.retest_channel_button = PrimaryPushButton(t("desktop.retest_channel"), self)
        self.retest_result_button = PushButton(t("desktop.retest_result"), self)
        self.open_button = PushButton(t("desktop.open_player"), self)
        self.copy_button = PushButton(t("desktop.copy_url"), self)

        self.channel_model = MappingTableModel([
            ("name", t("name.channel"), None),
            ("health", t("desktop.health"), _health),
            ("total_results", t("desktop.candidates"), None),
            ("valid_results", t("name.valid"), None),
            ("best_speed", t("name.max_speed"), _speed),
            ("min_delay", t("name.min_delay"), _delay),
            ("max_resolution", t("name.max_resolution"), None),
        ], self)
        self.result_model = MappingTableModel([
            ("selected_rank", t("desktop.rank"), None),
            ("valid", t("desktop.status"), lambda value, _: t("name.valid") if value else t("desktop.unavailable")),
            ("origin", t("name.from"), None),
            ("ipv_type", t("name.ipv_type"), None),
            ("speed", t("name.speed"), _speed),
            ("delay", t("name.delay"), _delay),
            ("resolution", t("name.resolution"), None),
            ("fps", t("name.fps"), None),
            ("location", t("name.location"), None),
            ("host", t("desktop.host"), None),
        ], self)
        self.channel_table = self._table(self.channel_model)
        self.result_table = self._table(self.result_model)
        self.channel_table.setMinimumWidth(580)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(BodyLabel(t("desktop.categories"), left))
        left_layout.addWidget(self.category_list)

        center = QWidget(self)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_actions = QHBoxLayout()
        center_actions.addWidget(self.search, 1)
        center_actions.addWidget(self.refresh_button)
        center_actions.addWidget(self.retest_channel_button)
        center_layout.addLayout(center_actions)
        center_layout.addWidget(self.channel_table)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        result_actions = QHBoxLayout()
        result_actions.addWidget(BodyLabel(t("desktop.results"), right))
        result_actions.addStretch(1)
        result_actions.addWidget(self.retest_result_button)
        result_actions.addWidget(self.copy_button)
        result_actions.addWidget(self.open_button)
        right_layout.addLayout(result_actions)
        right_layout.addWidget(self.result_table)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel(t("desktop.channel_center"), self))
        layout.addWidget(BodyLabel(t("desktop.channel_center_desc"), self))
        layout.addWidget(splitter, 1)

        self.refresh_button.clicked.connect(self.reload)
        self.category_list.currentItemChanged.connect(self._category_changed)
        self.search.textChanged.connect(self._search_changed)
        self.channel_table.selectionModel().selectionChanged.connect(self._channel_changed)
        self.retest_channel_button.clicked.connect(self._request_channel_retest)
        self.retest_result_button.clicked.connect(self._request_result_retest)
        self.copy_button.clicked.connect(self._copy_result)
        self.open_button.clicked.connect(self._open_result)
        self.reload()

    def _table(self, model):
        table = TableView(self)
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.setBorderVisible(True)
        table.setBorderRadius(8)
        return table

    def reload(self):
        selected_category = self.category_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.category_list.currentItem() else None
        try:
            categories = list_categories(constants.channel_results_path)
        except Exception:
            categories = []
        self.category_list.clear()
        all_item = QListWidgetItem(t("desktop.all_categories"))
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.category_list.addItem(all_item)
        for category in categories:
            item = QListWidgetItem(f"{category['category']}  {category['channel_count']}")
            item.setData(Qt.ItemDataRole.UserRole, category["category"])
            self.category_list.addItem(item)
            if category["category"] == selected_category:
                self.category_list.setCurrentItem(item)
        if not self.category_list.currentItem():
            self.category_list.setCurrentRow(0)
        self._load_channels()

    def _load_channels(self):
        item = self.category_list.currentItem()
        category = item.data(Qt.ItemDataRole.UserRole) if item else None
        try:
            rows = list_channels(constants.channel_results_path, category, self.search.text())
        except Exception:
            rows = []
        self.channel_model.set_rows(rows)
        self.result_model.set_rows([])

    def _category_changed(self, *_):
        self._load_channels()

    def _search_changed(self, *_):
        self._load_channels()

    def _channel_changed(self, selected: QItemSelection, _):
        indexes = selected.indexes()
        row = self.channel_model.row(indexes[0]) if indexes else None
        self.result_model.set_rows(list_channel_results(constants.channel_results_path, row["channel_key"]) if row else [])

    def selected_channel(self):
        indexes = self.channel_table.selectionModel().selectedRows()
        return self.channel_model.row(indexes[0]) if indexes else None

    def selected_result(self):
        indexes = self.result_table.selectionModel().selectedRows()
        return self.result_model.row(indexes[0]) if indexes else None

    def _request_channel_retest(self):
        row = self.selected_channel()
        if row:
            self.retest_channel_requested.emit(row)

    def _request_result_retest(self):
        row = self.selected_result()
        if row:
            self.retest_result_requested.emit(row)

    def _copy_result(self):
        row = self.selected_result()
        if row:
            QGuiApplication.clipboard().setText(row["url"])
            InfoBar.success(t("desktop.copied"), row["url"], parent=self, position=InfoBarPosition.TOP)

    def _open_result(self):
        row = self.selected_result()
        if row:
            QDesktopServices.openUrl(QUrl(row["url"]))
