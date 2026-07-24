import datetime

from PySide6.QtCore import QEasingCurve, QEvent, QItemSelectionModel, QPoint, QPropertyAnimation, QRect, QSize, QSignalBlocker, Signal, Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QGuiApplication, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QRubberBand, QStyleOptionViewItem, QVBoxLayout, QWidget
from qfluentwidgets import Action, BodyLabel, CardWidget, ComboBox, FluentIcon, InfoBar, InfoBarPosition, MessageBox, ProgressBar, PushButton, RoundMenu, TableItemDelegate, TableView, ToolButton, isDarkTheme

import utils.constants as constants
from desktop_ui.models import ChannelLogoLoader, ChannelTableModel, MappingTableModel
from desktop_ui.logo_dialog import ChannelLogoDialog, is_channel_logo_click
from desktop_ui.stream_status import StreamingStatusDelegate, apply_channel_stream_state, build_channel_stream_states
from desktop_ui.widgets import AccentPushButton, AppEditableComboBox, AppLineEdit, AppSearchLineEdit, DangerPushButton, configure_table_columns
from utils.channel_repository import add_manual_result, delete_channel_records, list_categories, list_channel_results, list_channels, list_result_urls_by_channel, set_channel_logo, upsert_manual_channel
from utils.config import config
from utils.i18n import t
from utils.tools import check_url_by_keywords, get_public_url, get_urls_from_file
from utils.user_actions import add_channel, add_manual_channel_result, add_to_blacklist, add_to_whitelist, delete_channels
from utils.whitelist import is_url_whitelisted, load_whitelist_maps


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


def _updated_at(value, _):
    return "--" if not value else datetime.datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")


def _paint_checkbox(painter, rect, state):
    size = min(16, rect.width(), rect.height())
    box = QRect(rect.center().x() - size // 2, rect.center().y() - size // 2, size, size)
    checked = state in (Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked)
    border = QColor("#60A5FA" if isDarkTheme() else "#2563EB") if checked else QColor("#94A3B8" if isDarkTheme() else "#64748B")
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(border, 1.6))
    painter.setBrush(QBrush(border if checked else Qt.BrushStyle.NoBrush))
    painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), 3, 3)
    painter.setPen(QPen(QColor("#FFFFFF"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if state == Qt.CheckState.Checked:
        painter.drawLine(box.left() + 4, box.center().y(), box.left() + 7, box.bottom() - 4)
        painter.drawLine(box.left() + 7, box.bottom() - 4, box.right() - 3, box.top() + 4)
    elif state == Qt.CheckState.PartiallyChecked:
        painter.drawLine(box.left() + 4, box.center().y(), box.right() - 4, box.center().y())
    painter.restore()


class CheckBoxHeader(QHeaderView):
    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._state = Qt.CheckState.Unchecked
        self._resizing = False

    def set_check_state(self, state):
        if state != self._state:
            self._state = state
            self.viewport().update()

    def paintSection(self, painter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        if logical_index != 0:
            return
        _paint_checkbox(painter, rect, self._state)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._resizing:
            self._resizing = False
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and self.logicalIndexAt(event.position().toPoint()) == 0:
            self.toggled.emit(self._state != Qt.CheckState.Checked)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.logicalIndexAt(event.position().toPoint()) == 0:
            boundary = self.sectionViewportPosition(0) + self.sectionSize(0)
            if abs(event.position().x() - boundary) <= 6:
                self._resizing = True
                super().mousePressEvent(event)
                return
            event.accept()
            return
        super().mousePressEvent(event)


class CheckBoxDelegate(TableItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.text = ""
        option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator

    def paint(self, painter, option, index):
        primary_delegate = self.parent().delegate
        self.hoverRow = primary_delegate.hoverRow
        self.pressedRow = primary_delegate.pressedRow
        self.selectedRows = primary_delegate.selectedRows
        super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            if option.rect.contains(event.position().toPoint()):
                checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
                return model.setData(index, Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select):
            checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
            return model.setData(index, Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        return False


class RubberBandTableView(TableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_origin = QPoint()
        self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.position().toPoint()
            self._rubber_band.setGeometry(QRect(self._drag_origin, QSize()))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            rect = QRect(self._drag_origin, event.position().toPoint()).normalized()
            if rect.width() + rect.height() >= QApplication.startDragDistance():
                self._rubber_band.setGeometry(rect)
                self._rubber_band.show()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._rubber_band.hide()


class ChannelCenterPage(QWidget):
    retest_channel_requested = Signal(dict)
    retest_result_requested = Signal(dict)
    playback_workspace_requested = Signal(dict)
    playback_batch_requested = Signal(list)
    stream_monitor_requested = Signal()
    stream_control_many_requested = Signal(str, list)

    def __init__(self, parent=None, logo_loader: ChannelLogoLoader | None = None):
        super().__init__(parent)
        self.setObjectName("channelCenterPage")
        self._task_operation = None
        self._task_name = None
        self._drawer_channel_key = None
        self._checked_channel_keys = set()
        self._checked_result_keys = set()
        self._stream_snapshot = {"streams": []}
        self._stream_states = {}
        self.category_selector = ComboBox(self)
        self.category_selector.setMinimumWidth(170)
        self.search = AppSearchLineEdit(self)
        self.search.setPlaceholderText(t("desktop.search_channels"))
        self.refresh_button = ToolButton(FluentIcon.SYNC, self)
        self.refresh_button.setToolTip(t("desktop.refresh"))
        self.add_channel_button = PushButton(FluentIcon.ADD, t("desktop.add_channel"), self)
        self.add_result_button = PushButton(FluentIcon.LINK, t("desktop.add_result"), self)
        self.delete_channel_button = DangerPushButton(FluentIcon.DELETE, t("desktop.delete_channel"), self)
        self.retest_channel_button = AccentPushButton(FluentIcon.SPEED_HIGH, t("desktop.retest_channel"), self)
        self.stream_selected_button = PushButton(FluentIcon.VIDEO, t("desktop.open_selected_streams"), self)
        self.stream_selected_button.hide()
        self.selection_label = BodyLabel("", self)
        self.selection_label.hide()
        self.task_label = BodyLabel("", self)
        self.task_progress = ProgressBar(self)
        self.task_label.hide()
        self.task_progress.hide()

        self.channel_model = ChannelTableModel(
            self._channel_columns(), self, checkable_key="batch_selected", logo_loader=logo_loader
        )
        self.logo_loader = self.channel_model.logo_loader
        self.result_model = MappingTableModel(self._result_columns(), self, checkable_key="batch_selected")
        self.channel_table = self._table(self.channel_model, multiple=True)
        self.channel_header = CheckBoxHeader(self.channel_table)
        self.channel_table.setHorizontalHeader(self.channel_header)
        self.channel_header.setSortIndicator(1, Qt.SortOrder.AscendingOrder)
        configure_table_columns(
            self.channel_table,
            [42, 240, 90, 80, 80, 105, 90, 115, 105, 85, 90, 170],
            "channel_center.channels",
        )
        self.channel_table.setIconSize(QSize(32, 24))
        self.channel_table.setItemDelegateForColumn(0, CheckBoxDelegate(self.channel_table))
        self.stream_status_delegate = StreamingStatusDelegate(self._show_stream_menu, self.channel_table)
        self.channel_table.setItemDelegateForColumn(1, self.stream_status_delegate)
        self.channel_header.toggled.connect(self._toggle_all_channels)
        self.channel_model.modelReset.connect(self._update_channel_header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(self.category_selector)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.selection_label)
        toolbar.addWidget(self.refresh_button)
        toolbar.addWidget(self.add_channel_button)
        toolbar.addWidget(self.add_result_button)
        toolbar.addWidget(self.delete_channel_button)
        toolbar.addWidget(self.retest_channel_button)
        toolbar.addWidget(self.stream_selected_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(toolbar)
        task_row = QHBoxLayout()
        task_row.addWidget(self.task_label, 1)
        task_row.addWidget(self.task_progress, 1)
        layout.addLayout(task_row)
        layout.addWidget(self.channel_table, 1)

        self._create_result_drawer()
        self.refresh_button.clicked.connect(self.reload)
        self.category_selector.currentIndexChanged.connect(self._category_changed)
        self.search.textChanged.connect(self._search_changed)
        self.channel_table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.channel_table.selectionModel().currentChanged.connect(self._current_channel_changed)
        self.channel_model.dataChanged.connect(self._channel_data_changed)
        self.channel_table.clicked.connect(self._channel_clicked)
        self.channel_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.channel_table.customContextMenuRequested.connect(self._show_channel_menu)
        self.add_channel_button.clicked.connect(self._add_channel)
        self.add_result_button.clicked.connect(self._add_manual_result)
        self.delete_channel_button.clicked.connect(self._delete_selected_channels)
        self.retest_channel_button.clicked.connect(self._request_channel_retest)
        self.stream_selected_button.clicked.connect(self._open_selected_in_playback)
        QApplication.instance().installEventFilter(self)
        self.reload()

    def _create_result_drawer(self):
        self.result_drawer = CardWidget(self)
        self.result_drawer.setObjectName("resultDrawer")
        self.result_drawer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.result_drawer.setBorderRadius(12)
        drawer_layout = QVBoxLayout(self.result_drawer)
        drawer_layout.setContentsMargins(18, 14, 18, 16)
        drawer_layout.setSpacing(8)
        header = QHBoxLayout()
        self.results_title = BodyLabel(t("desktop.results"), self.result_drawer)
        self.play_button = AccentPushButton(FluentIcon.PLAY, t("desktop.play"), self.result_drawer)
        self.retest_result_button = AccentPushButton(FluentIcon.SPEED_HIGH, t("desktop.retest_result"), self.result_drawer)
        self.stream_button = PushButton(FluentIcon.VIDEO, t("desktop.open_play_streaming"), self.result_drawer)
        self.more_button = PushButton(FluentIcon.MORE, t("desktop.more_actions"), self.result_drawer)
        self.close_drawer_button = ToolButton(FluentIcon.CLOSE, self.result_drawer)
        header.addWidget(self.results_title)
        header.addStretch(1)
        header.addWidget(self.play_button)
        header.addWidget(self.retest_result_button)
        header.addWidget(self.stream_button)
        header.addWidget(self.more_button)
        header.addWidget(self.close_drawer_button)
        drawer_layout.addLayout(header)
        self.result_table = self._table(self.result_model, multiple=True)
        self.result_header = CheckBoxHeader(self.result_table)
        self.result_table.setHorizontalHeader(self.result_header)
        self.result_header.setSortIndicator(1, Qt.SortOrder.AscendingOrder)
        configure_table_columns(
            self.result_table,
            [42, 90, 110, 90, 110, 90, 100, 280],
            "channel_center.results",
        )
        self.result_table.setItemDelegateForColumn(0, CheckBoxDelegate(self.result_table))
        self.result_header.toggled.connect(self._toggle_all_results)
        self.result_model.modelReset.connect(self._update_result_header)
        drawer_layout.addWidget(self.result_table, 1)
        self.result_drawer.hide()
        self.drawer_animation = QPropertyAnimation(self.result_drawer, b"geometry", self)
        self.drawer_animation.setDuration(180)
        self.drawer_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._drawer_hiding = False
        self.drawer_animation.finished.connect(self._drawer_animation_finished)
        self.play_button.clicked.connect(self._open_result)
        self.retest_result_button.clicked.connect(self._request_result_retest)
        self.stream_button.clicked.connect(self._stream_playback)
        self.close_drawer_button.clicked.connect(self.hide_result_drawer)
        self.result_table.doubleClicked.connect(lambda _: self._open_result())
        self.result_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_table.customContextMenuRequested.connect(self._show_result_menu)
        self.result_model.dataChanged.connect(self._result_data_changed)
        self._create_menus()
        self._update_drawer_style()

    def _create_menus(self):
        self.copy_action = Action(FluentIcon.COPY, t("desktop.copy_url"), self, triggered=self._copy_result)
        self.copy_stream_action = Action(FluentIcon.LINK, t("desktop.copy_stream_url"), self, triggered=self._copy_stream_url)
        self.whitelist_action = Action(FluentIcon.ADD_TO, t("desktop.add_whitelist"), self, triggered=self._add_whitelist)
        self.blacklist_action = Action(FluentIcon.REMOVE_FROM, t("desktop.add_blacklist"), self, triggered=self._add_blacklist)
        self.result_menu = RoundMenu(parent=self)
        for action in (self.copy_action, self.copy_stream_action, self.whitelist_action, self.blacklist_action):
            self.result_menu.addAction(action)
        self.more_button.setMenu(self.result_menu)
        self.channel_retest_action = Action(FluentIcon.SPEED_HIGH, t("desktop.retest_channel"), self, triggered=self._request_channel_retest)
        self.channel_add_result_action = Action(FluentIcon.LINK, t("desktop.add_result"), self, triggered=self._add_manual_result)
        self.channel_edit_logo_action = Action(FluentIcon.PHOTO, t("desktop.edit_channel_logo"), self, triggered=self._edit_channel_logo)
        self.channel_delete_action = Action(FluentIcon.DELETE.icon(color=QColor("#DC2626")), t("desktop.delete_channel"), self, triggered=self._delete_selected_channels)
        self.channel_menu = RoundMenu(parent=self)
        for action in (self.channel_retest_action, self.channel_add_result_action, self.channel_edit_logo_action, self.channel_delete_action):
            self.channel_menu.addAction(action)

    @staticmethod
    def _channel_columns():
        return [
            ("batch_selected", "", None),
            ("name", t("name.channel"), None),
            ("health", t("desktop.status"), _health),
            ("valid_results", t("desktop.column_valid"), None),
            ("total_results", t("desktop.column_results"), None),
            ("best_speed", t("desktop.column_best_speed"), _speed),
            ("min_delay", t("desktop.column_delay"), _delay),
            ("max_resolution", t("desktop.column_resolution"), None),
            ("category", t("desktop.column_category"), None),
            ("whitelist_count", t("desktop.column_whitelist"), None),
            ("blacklist_count", t("desktop.column_blacklist"), None),
            ("updated_at", t("desktop.column_updated"), _updated_at),
        ]

    @staticmethod
    def _result_columns():
        return [
            ("batch_selected", "", None),
            ("valid", t("desktop.status"), lambda value, _: t("name.valid") if value else t("desktop.unavailable")),
            ("speed", t("desktop.column_speed"), _speed),
            ("delay", t("desktop.column_delay"), _delay),
            ("resolution", t("desktop.column_resolution"), None),
            ("ipv_type", t("desktop.column_protocol"), None),
            ("origin", t("name.from"), None),
            ("host", t("desktop.host"), None),
        ]

    def _table(self, model, multiple=False):
        table = RubberBandTableView(self)
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection if multiple
            else QAbstractItemView.SelectionMode.SingleSelection
        )
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.setBorderVisible(True)
        table.setBorderRadius(8)
        return table

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.result_drawer.isVisible() and self.drawer_animation.state() != QPropertyAnimation.State.Running:
            self.result_drawer.setGeometry(self._drawer_geometry())

    def _drawer_geometry(self):
        height = min(360, max(250, int(self.height() * 0.44)))
        return QRect(28, self.height() - height - 24, max(320, self.width() - 56), height)

    def show_result_drawer(self):
        target = self._drawer_geometry()
        self._update_drawer_style()
        if self.result_drawer.isVisible() and not self._drawer_hiding:
            self.drawer_animation.stop()
            self.result_drawer.setGeometry(target)
            self.result_drawer.raise_()
            return
        start = QRect(target.x(), self.height() + 4, target.width(), target.height())
        self.result_drawer.setGeometry(start)
        self.result_drawer.show()
        self.result_drawer.raise_()
        self._drawer_hiding = False
        self.drawer_animation.stop()
        self.drawer_animation.setStartValue(start)
        self.drawer_animation.setEndValue(target)
        self.drawer_animation.start()

    def hide_result_drawer(self):
        if not self.result_drawer.isVisible():
            return
        self.drawer_animation.stop()
        self._drawer_hiding = True
        self.drawer_animation.setStartValue(self.result_drawer.geometry())
        self.drawer_animation.setEndValue(QRect(28, self.height() + 4, self.result_drawer.width(), self.result_drawer.height()))
        self.drawer_animation.start()

    def _drawer_animation_finished(self):
        if self._drawer_hiding:
            self.result_drawer.hide()
            self._drawer_hiding = False

    def _update_drawer_style(self):
        background = "#202020" if isDarkTheme() else "#ffffff"
        border = "#3a3a3a" if isDarkTheme() else "#d9dfe7"
        self.result_drawer.setStyleSheet(
            f"CardWidget#resultDrawer {{ background-color: {background}; border: 1px solid {border}; }}"
        )

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.hide_result_drawer()
        if event.type() == QEvent.Type.MouseButtonPress and self.result_drawer.isVisible():
            widget = watched if isinstance(watched, QWidget) else None
            if widget and not self._is_child_of(widget, self.result_drawer) and not self._is_child_of(widget, self.channel_table):
                self.hide_result_drawer()
        return super().eventFilter(watched, event)

    @staticmethod
    def _is_child_of(widget, parent):
        current = widget
        while current:
            if current is parent:
                return True
            current = current.parentWidget()
        return False

    def reload(self):
        selected_category = self.category_selector.currentData()
        selected_channels = {row["channel_key"] for row in self.selected_channels()}
        checked_channels = {row["channel_key"] for row in self.channel_model.rows if row.get("batch_selected")}
        selected_result = self.selected_result()
        result_key = selected_result.get("result_key") if selected_result else None
        try:
            categories = list_categories(constants.channel_results_path)
        except Exception:
            categories = []
        blocker = QSignalBlocker(self.category_selector)
        self.category_selector.clear()
        self.category_selector.addItem(t("desktop.all_categories"), userData=None)
        target_index = 0
        for category in categories:
            self.category_selector.addItem(
                f"{category['category']}  {category['channel_count']}",
                userData=category["category"],
            )
            if category["category"] == selected_category:
                target_index = self.category_selector.count() - 1
        self.category_selector.setCurrentIndex(target_index)
        del blocker
        self._load_channels(selected_channels, checked_channels)
        if self._drawer_channel_key:
            self._load_results(self._drawer_channel_key, result_key)

    def _load_channels(self, selected_keys=None, checked_keys=None):
        category = self.category_selector.currentData()
        try:
            rows = list_channels(constants.channel_results_path, category, self.search.text())
            result_urls = list_result_urls_by_channel(constants.channel_results_path)
            whitelist_maps = load_whitelist_maps(constants.whitelist_path)
            blacklist = get_urls_from_file(constants.blacklist_path, pattern_search=False)
        except Exception:
            rows, result_urls, whitelist_maps, blacklist = [], {}, ({}, {}), []
        for row in rows:
            urls = result_urls.get(row["channel_key"], [])
            row["whitelist_count"] = sum(is_url_whitelisted(whitelist_maps, url, row["name"]) for url in urls)
            row["blacklist_count"] = sum(check_url_by_keywords(url, blacklist) for url in urls)
            row["batch_selected"] = row.get("channel_key") in (checked_keys or self._checked_channel_keys)
            row.update(apply_channel_stream_state(row, self._stream_states))
        self.channel_model.set_rows(rows)
        selection = self.channel_table.selectionModel()
        selection.clearSelection()
        for index, row in enumerate(self.channel_model.rows):
            if row.get("channel_key") in (selected_keys or set()):
                selection.select(
                    self.channel_model.index(index, 0),
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                )
        self._checked_channel_keys = {row["channel_key"] for row in rows if row.get("batch_selected")}
        self._update_selection_label()

    def _load_results(self, channel_key: str, result_key=None):
        if channel_key != self._drawer_channel_key:
            self._checked_result_keys.clear()
        try:
            results = list_channel_results(constants.channel_results_path, channel_key)
        except Exception:
            results = []
        for result in results:
            result["batch_selected"] = result.get("result_key") in self._checked_result_keys
        self.result_model.set_rows(results)
        selected_row = next((index for index, row in enumerate(self.result_model.rows) if row.get("result_key") == result_key), -1)
        if selected_row >= 0:
            self.result_table.selectRow(selected_row)

    def _category_changed(self, *_):
        self.hide_result_drawer()
        self._load_channels()

    def _search_changed(self, *_):
        self.hide_result_drawer()
        self._load_channels()

    def _current_channel_changed(self, current, _):
        row = self.channel_model.row(current)
        if row:
            if self._drawer_channel_key != row["channel_key"]:
                self._checked_result_keys.clear()
            self._drawer_channel_key = row["channel_key"]
            self._load_results(row["channel_key"])
            self.results_title.setText(t("desktop.channel_results_title").format(name=row["name"]))

    def _selection_changed(self, *_):
        self._update_selection_label()

    def _channel_data_changed(self, *_):
        self._checked_channel_keys = {
            row["channel_key"] for row in self.channel_model.rows if row.get("batch_selected")
        }
        self._update_selection_label()
        self._update_channel_header()

    def _result_data_changed(self, *_):
        self._checked_result_keys = {
            row["result_key"] for row in self.result_model.rows if row.get("batch_selected")
        }
        self._update_result_header()

    def _toggle_all_channels(self, checked: bool):
        self.channel_model.set_all_checked(checked)

    def _update_channel_header(self):
        self.channel_header.set_check_state(self.channel_model.check_state())

    def _toggle_all_results(self, checked: bool):
        self.result_model.set_all_checked(checked)

    def _update_result_header(self):
        self.result_header.set_check_state(self.result_model.check_state())

    def _update_selection_label(self):
        count = len(self.selected_channels())
        self.selection_label.setText(t("desktop.channels_selected").format(count=count))
        self.selection_label.setVisible(count > 0)
        self.stream_selected_button.setVisible(count > 0)

    def _channel_clicked(self, index):
        row = self.channel_model.row(index)
        if row and self.channel_model.columns[index.column()][0] == "name" and is_channel_logo_click(self.channel_table, index):
            self._edit_channel_logo(row)
            return
        if row and self.channel_model.columns[index.column()][0] != "batch_selected":
            if self._drawer_channel_key != row["channel_key"]:
                self._checked_result_keys.clear()
            self._drawer_channel_key = row["channel_key"]
            self._load_results(row["channel_key"])
            self.results_title.setText(t("desktop.channel_results_title").format(name=row["name"]))
            self.show_result_drawer()

    def selected_channels(self):
        keys = {
            row["channel_key"]
            for index in self.channel_table.selectionModel().selectedRows()
            if (row := self.channel_model.row(index))
        }
        keys.update(row["channel_key"] for row in self.channel_model.rows if row.get("batch_selected"))
        return [row for row in self.channel_model.rows if row.get("channel_key") in keys]

    def selected_channel(self):
        current = self.channel_table.currentIndex()
        return self.channel_model.row(current) if current.isValid() else (self.selected_channels()[0] if self.selected_channels() else None)

    def selected_result(self):
        rows = self.selected_results()
        current = self.result_model.row(self.result_table.currentIndex())
        return current if current in rows else (rows[0] if rows else None)

    def selected_results(self):
        indexes = self.result_table.selectionModel().selectedRows()
        keys = {
            row["result_key"]
            for index in indexes
            if (row := self.result_model.row(index))
        }
        keys.update(self._checked_result_keys)
        return [row for row in self.result_model.rows if row.get("result_key") in keys]

    def _show_channel_menu(self, position):
        index = self.channel_table.indexAt(position)
        if index.isValid():
            if not self.channel_table.selectionModel().isRowSelected(index.row(), index.parent()):
                self.channel_table.selectRow(index.row())
            self.channel_menu.exec(self.channel_table.viewport().mapToGlobal(position))

    def set_stream_snapshot(self, snapshot: dict):
        self._stream_snapshot = snapshot
        self._stream_states = build_channel_stream_states(snapshot)
        for index, row in enumerate(self.channel_model.rows):
            self.channel_model.rows[index] = apply_channel_stream_state(row, self._stream_states)
        if self.channel_model.rows:
            self.channel_model.dataChanged.emit(
                self.channel_model.index(0, 1),
                self.channel_model.index(len(self.channel_model.rows) - 1, 1),
                [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole],
            )

    def _show_stream_menu(self, row: dict, position):
        menu = RoundMenu(parent=self)
        menu.addAction(Action(
            FluentIcon.IOT,
            t("desktop.view_stream_details"),
            self,
            triggered=lambda _checked=False: self.stream_monitor_requested.emit(),
        ))
        menu.addAction(Action(
            FluentIcon.PAUSE_BOLD.icon(color=QColor("#DC2626")),
            t("desktop.stop_channel_streams"),
            self,
            triggered=lambda _checked=False: self._stop_channel_streams(row),
        ))
        menu.exec(position)

    def _stop_channel_streams(self, row: dict):
        result_keys = list(row.get("stream_result_keys") or [])
        if not result_keys:
            return
        box = MessageBox(
            t("desktop.stop_channel_streams"),
            t("desktop.stop_channel_streams_confirm").format(
                name=row.get("name") or "--",
                count=len(result_keys),
            ),
            self,
        )
        if box.exec():
            self.stream_control_many_requested.emit("stop", result_keys)

    def _show_result_menu(self, position):
        index = self.result_table.indexAt(position)
        if index.isValid():
            if not self.result_table.selectionModel().isRowSelected(index.row(), index.parent()):
                self.result_table.selectRow(index.row())
            self.result_menu.exec(self.result_table.viewport().mapToGlobal(position))

    def _request_channel_retest(self):
        for row in self.selected_channels():
            self.retest_channel_requested.emit(row)

    def _open_selected_in_playback(self):
        rows = self.selected_channels()
        if rows:
            self.playback_batch_requested.emit(rows)

    def _request_result_retest(self):
        for row in self.selected_results():
            self.retest_result_requested.emit(row)

    def _copy_result(self):
        rows = self.selected_results()
        if rows:
            value = "\n".join(row["url"] for row in rows)
            QGuiApplication.clipboard().setText(value)
            InfoBar.success(t("desktop.copied"), value, parent=self, position=InfoBarPosition.TOP)

    def _open_result(self):
        row = self.selected_result()
        if row:
            QDesktopServices.openUrl(QUrl(row["url"]))

    def _stream_playback(self):
        row = self.selected_result()
        if row and row.get("selected_rank") is not None:
            self.playback_workspace_requested.emit(row)
        elif row:
            InfoBar.warning(t("desktop.not_selected_result"), t("desktop.select_result_hint"), parent=self, position=InfoBarPosition.TOP)

    def _copy_stream_url(self):
        row = self.selected_result()
        if row and row.get("selected_rank") is not None:
            url = f"{get_public_url().rstrip('/')}/hls_proxy/{row['result_key']}"
            QGuiApplication.clipboard().setText(url)
            InfoBar.success(t("desktop.copied"), url, parent=self, position=InfoBarPosition.TOP)
        elif row:
            InfoBar.warning(t("desktop.not_selected_result"), t("desktop.select_result_hint"), parent=self, position=InfoBarPosition.TOP)

    def _add_whitelist(self):
        channel = self.selected_channel()
        results = self.selected_results()
        if channel and results:
            changes = [add_to_whitelist(channel["name"], result["url"]) for result in results]
            changed = any(changes)
            InfoBar.success(t("desktop.whitelist_updated"), t("desktop.next_update_effect" if changed else "desktop.already_exists"), parent=self, position=InfoBarPosition.TOP)
            self.reload()

    def _add_blacklist(self):
        results = self.selected_results()
        if results:
            changes = [add_to_blacklist(result["url"]) for result in results]
            changed = any(changes)
            InfoBar.success(t("desktop.blacklist_updated"), t("desktop.next_update_effect" if changed else "desktop.already_exists"), parent=self, position=InfoBarPosition.TOP)
            self.reload()

    def _add_channel(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(t("desktop.add_channel"))
        form = QFormLayout(dialog)
        category = AppEditableComboBox(dialog)
        category.addItems([row["category"] for row in list_categories(constants.channel_results_path)])
        name = AppLineEdit(dialog)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, dialog)
        form.addRow(t("desktop.categories"), category)
        form.addRow(t("name.channel"), name)
        form.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted or not category.currentText().strip() or not name.text().strip():
            return
        if add_channel(category.currentText(), name.text()):
            upsert_manual_channel(constants.channel_results_path, category.currentText().strip(), name.text().strip())
            self.reload()
            InfoBar.success(t("desktop.channel_added"), name.text().strip(), parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.warning(t("desktop.channel_exists"), name.text().strip(), parent=self, position=InfoBarPosition.TOP)

    def _edit_channel_logo(self, channel=None):
        channel = channel if isinstance(channel, dict) else self.selected_channel()
        if not channel:
            return
        dialog = ChannelLogoDialog(channel, self.logo_loader, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        set_channel_logo(constants.channel_results_path, channel["channel_key"], dialog.logo_value())
        self.reload()
        InfoBar.success(t("desktop.channel_logo_updated"), channel["name"], parent=self, position=InfoBarPosition.TOP)

    def _delete_selected_channels(self):
        rows = self.selected_channels()
        if not rows:
            return
        box = MessageBox(
            t("desktop.delete_channel"),
            t("desktop.delete_channels_confirm").format(count=len(rows)),
            self,
        )
        if not box.exec():
            return
        delete_channels([row["name"] for row in rows])
        delete_channel_records(constants.channel_results_path, [row["channel_key"] for row in rows])
        self.hide_result_drawer()
        self.reload()
        InfoBar.success(t("desktop.channels_deleted"), str(len(rows)), parent=self, position=InfoBarPosition.TOP)

    def _add_manual_result(self):
        channel = self.selected_channel()
        if not channel:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(t("desktop.add_result"))
        form = QFormLayout(dialog)
        channel_label = QLabel(channel["name"], dialog)
        url = AppLineEdit(dialog)
        url.setPlaceholderText("https://example.com/live.m3u8")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, dialog)
        form.addRow(t("name.channel"), channel_label)
        form.addRow(t("desktop.source_url"), url)
        form.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted or not url.text().strip():
            return
        add_manual_channel_result(channel["name"], url.text())
        result_key = add_manual_result(constants.channel_results_path, channel["channel_key"], url.text().strip())
        self._load_results(channel["channel_key"], result_key)
        self.show_result_drawer()
        row = next((item for item in self.result_model.rows if item.get("result_key") == result_key), None)
        if row:
            self.retest_result_requested.emit(row)

    def set_task_started(self, operation: str):
        self._task_operation = operation
        self._task_name = None
        self.task_label.setText(t(f"desktop.{operation}", operation))
        self.task_progress.setValue(0)
        self.task_label.show()
        self.task_progress.show()

    def set_task_progress(self, name: str, value: int):
        self._task_name = name
        self.task_label.setText(t("desktop.testing_channel").format(name=name))
        self.task_progress.setValue(value)

    def set_task_finished(self):
        self._task_operation = None
        self._task_name = None
        self.task_label.hide()
        self.task_progress.hide()
        self.reload()

    def retranslate(self):
        self.search.setPlaceholderText(t("desktop.search_channels"))
        self.refresh_button.setToolTip(t("desktop.refresh"))
        self.add_channel_button.setText(t("desktop.add_channel"))
        self.add_result_button.setText(t("desktop.add_result"))
        self.delete_channel_button.setText(t("desktop.delete_channel"))
        self.retest_channel_button.setText(t("desktop.retest_channel"))
        self.stream_selected_button.setText(t("desktop.open_selected_streams"))
        self.play_button.setText(t("desktop.play"))
        self.retest_result_button.setText(t("desktop.retest_result"))
        self.stream_button.setText(t("desktop.open_play_streaming"))
        self.more_button.setText(t("desktop.more_actions"))
        for action, key in (
            (self.copy_action, "desktop.copy_url"),
            (self.copy_stream_action, "desktop.copy_stream_url"),
            (self.whitelist_action, "desktop.add_whitelist"),
            (self.blacklist_action, "desktop.add_blacklist"),
            (self.channel_retest_action, "desktop.retest_channel"),
            (self.channel_add_result_action, "desktop.add_result"),
            (self.channel_edit_logo_action, "desktop.edit_channel_logo"),
            (self.channel_delete_action, "desktop.delete_channel"),
        ):
            action.setText(t(key))
        self.channel_model.set_columns(self._channel_columns())
        self.result_model.set_columns(self._result_columns())
        self.reload()
        self.set_stream_snapshot(self._stream_snapshot)
