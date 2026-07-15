from PySide6.QtCore import QItemSelection, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QListWidgetItem, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FlowLayout, FluentIcon, InfoBar, InfoBarPosition, ListWidget, PrimaryPushButton, ProgressBar, PushButton, SearchLineEdit, SubtitleLabel, TableView

import utils.constants as constants
from desktop_ui.models import MappingTableModel
from utils.channel_repository import list_categories, list_channel_results, list_channels
from utils.i18n import t
from utils.user_actions import add_to_blacklist, add_to_whitelist


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
    retest_category_requested = Signal(str)
    stream_control_requested = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("channelCenterPage")
        self.category_list = ListWidget(self)
        self.category_list.setMinimumWidth(190)
        self.category_list.setMaximumWidth(260)
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText(t("desktop.search_channels"))
        self.refresh_button = PushButton(FluentIcon.SYNC, t("desktop.refresh"), self)
        self.retest_channel_button = PrimaryPushButton(FluentIcon.SPEED_HIGH, t("desktop.retest_channel"), self)
        self.retest_category_button = PushButton(FluentIcon.LIBRARY, t("desktop.retest_category"), self)
        self.retest_result_button = PushButton(FluentIcon.SPEED_HIGH, t("desktop.retest_result"), self)
        self.open_button = PushButton(FluentIcon.PLAY, t("desktop.open_player"), self)
        self.copy_button = PushButton(FluentIcon.COPY, t("desktop.copy_url"), self)
        self.start_stream_button = PushButton(FluentIcon.PLAY_SOLID, t("desktop.start_stream"), self)
        self.whitelist_button = PushButton(FluentIcon.ADD_TO, t("desktop.add_whitelist"), self)
        self.blacklist_button = PushButton(FluentIcon.REMOVE_FROM, t("desktop.add_blacklist"), self)
        self.task_label = BodyLabel(t("desktop.no_pending_tasks"), self)
        self.task_progress = ProgressBar(self)
        self.task_progress.setValue(0)
        self.task_progress.hide()
        self._task_operation = None
        self._task_name = None

        self.channel_model = MappingTableModel(self._channel_columns(), self)
        self.result_model = MappingTableModel(self._result_columns(), self)
        self.channel_table = self._table(self.channel_model)
        self.result_table = self._table(self.result_model)
        self.channel_table.setMinimumWidth(340)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.categories_title = BodyLabel(t("desktop.categories"), left)
        left_layout.addWidget(self.categories_title)
        left_layout.addWidget(self.category_list)

        center = QWidget(self)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_actions = QHBoxLayout()
        center_actions.addWidget(self.search, 1)
        center_actions.addWidget(self.refresh_button)
        center_layout.addLayout(center_actions)
        channel_action_widget = QWidget(center)
        channel_actions = FlowLayout(channel_action_widget, isTight=True)
        channel_actions.setContentsMargins(0, 0, 0, 0)
        channel_actions.setHorizontalSpacing(8)
        channel_actions.setVerticalSpacing(8)
        channel_actions.addWidget(self.retest_category_button)
        channel_actions.addWidget(self.retest_channel_button)
        center_layout.addWidget(channel_action_widget)
        center_layout.addWidget(self.channel_table)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.results_title = BodyLabel(t("desktop.results"), right)
        right_layout.addWidget(self.results_title)
        result_action_widget = QWidget(right)
        result_actions = FlowLayout(result_action_widget, isTight=True)
        result_actions.setContentsMargins(0, 0, 0, 0)
        result_actions.setHorizontalSpacing(8)
        result_actions.setVerticalSpacing(8)
        for button in (
            self.retest_result_button,
            self.copy_button,
            self.whitelist_button,
            self.blacklist_button,
            self.start_stream_button,
            self.open_button,
        ):
            result_actions.addWidget(button)
        right_layout.addWidget(result_action_widget)
        right_layout.addWidget(self.result_table)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        splitter.setSizes([180, 470, 470])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        self.title = SubtitleLabel(t("desktop.channel_center"), self)
        layout.addWidget(self.title)
        task_row = QHBoxLayout()
        task_row.addWidget(self.task_label, 1)
        task_row.addWidget(self.task_progress, 1)
        layout.addLayout(task_row)
        layout.addWidget(splitter, 1)

        self.refresh_button.clicked.connect(self.reload)
        self.category_list.currentItemChanged.connect(self._category_changed)
        self.search.textChanged.connect(self._search_changed)
        self.channel_table.selectionModel().selectionChanged.connect(self._channel_changed)
        self.retest_channel_button.clicked.connect(self._request_channel_retest)
        self.retest_category_button.clicked.connect(self._request_category_retest)
        self.retest_result_button.clicked.connect(self._request_result_retest)
        self.copy_button.clicked.connect(self._copy_result)
        self.open_button.clicked.connect(self._open_result)
        self.start_stream_button.clicked.connect(self._start_stream)
        self.whitelist_button.clicked.connect(self._add_whitelist)
        self.blacklist_button.clicked.connect(self._add_blacklist)
        self.reload()

    @staticmethod
    def _channel_columns():
        return [
            ("name", t("name.channel"), None),
            ("health", t("desktop.health"), _health),
            ("total_results", t("desktop.candidates"), None),
            ("valid_results", t("name.valid"), None),
            ("best_speed", t("name.max_speed"), _speed),
            ("min_delay", t("name.min_delay"), _delay),
            ("max_resolution", t("name.max_resolution"), None),
        ]

    @staticmethod
    def _result_columns():
        return [
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
        ]

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
        try:
            results = list_channel_results(constants.channel_results_path, row["channel_key"]) if row else []
        except Exception:
            results = []
        self.result_model.set_rows(results)

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

    def _request_category_retest(self):
        item = self.category_list.currentItem()
        category = item.data(Qt.ItemDataRole.UserRole) if item else None
        if category:
            self.retest_category_requested.emit(category)

    def _copy_result(self):
        row = self.selected_result()
        if row:
            QGuiApplication.clipboard().setText(row["url"])
            InfoBar.success(t("desktop.copied"), row["url"], parent=self, position=InfoBarPosition.TOP)

    def _open_result(self):
        row = self.selected_result()
        if row:
            QDesktopServices.openUrl(QUrl(row["url"]))

    def _start_stream(self):
        row = self.selected_result()
        if row and row.get("selected_rank") is not None:
            self.stream_control_requested.emit("start", row)
        elif row:
            InfoBar.warning(t("desktop.not_selected_result"), t("desktop.select_result_hint"), parent=self, position=InfoBarPosition.TOP)

    def _add_whitelist(self):
        channel = self.selected_channel()
        result = self.selected_result()
        if channel and result:
            changed = add_to_whitelist(channel["name"], result["url"])
            InfoBar.success(t("desktop.whitelist_updated"), t("desktop.next_update_effect" if changed else "desktop.already_exists"), parent=self, position=InfoBarPosition.TOP)

    def _add_blacklist(self):
        result = self.selected_result()
        if result:
            changed = add_to_blacklist(result["url"])
            InfoBar.success(t("desktop.blacklist_updated"), t("desktop.next_update_effect" if changed else "desktop.already_exists"), parent=self, position=InfoBarPosition.TOP)

    def set_task_started(self, operation: str):
        self._task_operation = operation
        self._task_name = None
        self.task_label.setText(t(f"desktop.{operation}", operation))
        self.task_progress.setValue(0)
        self.task_progress.show()

    def set_task_progress(self, name: str, value: int):
        self._task_name = name
        self.task_label.setText(t("desktop.testing_channel").format(name=name))
        self.task_progress.setValue(value)

    def set_task_finished(self):
        self._task_operation = None
        self._task_name = None
        self.task_label.setText(t("desktop.no_pending_tasks"))
        self.task_progress.hide()
        self.reload()

    def retranslate(self):
        self.title.setText(t("desktop.channel_center"))
        self.categories_title.setText(t("desktop.categories"))
        self.results_title.setText(t("desktop.results"))
        self.search.setPlaceholderText(t("desktop.search_channels"))
        self.refresh_button.setText(t("desktop.refresh"))
        self.retest_channel_button.setText(t("desktop.retest_channel"))
        self.retest_category_button.setText(t("desktop.retest_category"))
        self.retest_result_button.setText(t("desktop.retest_result"))
        self.open_button.setText(t("desktop.open_player"))
        self.copy_button.setText(t("desktop.copy_url"))
        self.start_stream_button.setText(t("desktop.start_stream"))
        self.whitelist_button.setText(t("desktop.add_whitelist"))
        self.blacklist_button.setText(t("desktop.add_blacklist"))
        self.channel_model.set_columns(self._channel_columns())
        self.result_model.set_columns(self._result_columns())
        if self._task_name:
            self.task_label.setText(t("desktop.testing_channel").format(name=self._task_name))
        elif self._task_operation:
            self.task_label.setText(t(f"desktop.{self._task_operation}", self._task_operation))
        else:
            self.task_label.setText(t("desktop.no_pending_tasks"))
        self.reload()
