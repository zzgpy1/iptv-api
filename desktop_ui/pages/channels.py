import datetime
import re

from PySide6.QtCore import QEasingCurve, QEvent, QItemSelectionModel, QPoint, QPropertyAnimation, QRect, QRectF, QSettings, QSize, QSignalBlocker, Signal, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QRubberBand, QSplitter, QStackedWidget, QTreeWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import Action, BodyLabel, CardWidget, ComboBox, DropDownPushButton, FluentIcon, IconWidget, InfoBar, InfoBarPosition, MessageBox, ProgressBar, PushButton, RoundMenu, SegmentedWidget, StrongBodyLabel, TableView, ToolButton, TreeWidget, isDarkTheme

import utils.constants as constants
from desktop_ui.models import ChannelLogoLoader, ChannelTableModel, MappingTableModel
from desktop_ui.logo_dialog import ChannelLogoDialog, is_channel_logo_click
from desktop_ui.screenshot_dialog import StreamScreenshotDialog
from desktop_ui.stream_status import StreamingStatusDelegate, apply_channel_stream_state, build_channel_stream_states
from desktop_ui.widgets import AccentPushButton, AppEditableComboBox, AppLineEdit, AppSearchLineEdit, DangerPushButton, TableCheckBoxDelegate, TableCheckBoxHeader, configure_table_columns
from utils.channel_repository import add_manual_result, delete_channel_records, list_categories, list_channel_results, list_channels, list_result_urls_by_channel, set_channel_logo, upsert_manual_channel
from utils.config import config, resource_path
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


def _category_label(value):
    label = re.sub(r"^[^A-Za-z0-9\u4e00-\u9fff]+", "", str(value or "")).strip()
    return label or str(value or "")


def _template_category_order():
    try:
        with open(resource_path(config.source_file), "r", encoding="utf-8") as file:
            lines = file
            categories = []
            seen = set()
            for raw in lines:
                match = re.match(r"^(.*?)[,，]\s*#genre#\s*$", raw.strip())
                if not match:
                    continue
                category = match.group(1).strip()
                if category and category not in seen:
                    seen.add(category)
                    categories.append(category)
            return categories
    except OSError:
        return []


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


class ResultDrawerCard(CardWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QColor("#202020" if isDarkTheme() else "#FFFFFF")
        border = QColor("#3A3A3A" if isDarkTheme() else "#D9DFE7")
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        radius = self.getBorderRadius()
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), radius, radius)


class DrawerResizeHandle(QWidget):
    resize_requested = Signal(int)
    resize_finished = Signal()
    full_screen_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_global_y = None
        self.setFixedHeight(12)
        self.setCursor(Qt.CursorShape.SizeVerCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#666666" if isDarkTheme() else "#A8B0BB")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        rect = QRectF((self.width() - 42) / 2, 4, 42, 4)
        painter.drawRoundedRect(rect, 2, 2)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_global_y = int(event.globalPosition().y())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._last_global_y is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            global_y = int(event.globalPosition().y())
            self.resize_requested.emit(self._last_global_y - global_y)
            self._last_global_y = global_y
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._last_global_y is not None
        ):
            self._last_global_y = None
            self.resize_finished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.full_screen_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ChannelCenterPage(QWidget):
    retest_channel_requested = Signal(dict)
    retest_result_requested = Signal(dict)
    capture_screenshot_requested = Signal(dict)
    capture_screenshots_requested = Signal(list)
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
        try:
            self._drawer_height = int(
                QSettings().value("appearance/channel_result_drawer_height", 360)
            )
        except (TypeError, ValueError):
            self._drawer_height = 360
        self._drawer_height = max(250, self._drawer_height)
        self._drawer_fullscreen = False
        self._screenshot_dialog = None
        self._checked_channel_keys = set()
        self._checked_result_keys = set()
        self._stream_snapshot = {"streams": []}
        self._stream_states = {}
        self._view_mode = str(QSettings().value("appearance/channel_center_view", "category"))
        if self._view_mode not in {"category", "list"}:
            self._view_mode = "category"
        self._category_order = []
        self._category_filter = None
        self._health_filter = None
        self._category_items = {}
        self._smart_items = {}
        self.view_switch = SegmentedWidget(self)
        self.view_switch.addItem("category", t("desktop.channel_view_category"), icon=FluentIcon.FOLDER)
        self.view_switch.addItem("list", t("desktop.channel_view_list"), icon=FluentIcon.MENU)
        self.view_switch.setMinimumWidth(210)
        self.view_switch.setCurrentItem(self._view_mode)
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
        self.channel_header = TableCheckBoxHeader(self.channel_table)
        self.channel_table.setHorizontalHeader(self.channel_header)
        self.channel_header.setSortIndicator(1, Qt.SortOrder.AscendingOrder)
        configure_table_columns(
            self.channel_table,
            [42, 240, 90, 80, 80, 105, 90, 115, 105, 85, 90, 170],
            "channel_center.channels",
            fixed_widths={0: 42},
        )
        self.channel_table.setIconSize(QSize(32, 24))
        self.channel_table.setItemDelegateForColumn(0, TableCheckBoxDelegate(self.channel_table))
        self.stream_status_delegate = StreamingStatusDelegate(self._show_stream_menu, self.channel_table)
        self.channel_table.setItemDelegateForColumn(1, self.stream_status_delegate)
        self.channel_header.toggled.connect(self._toggle_all_channels)
        self.channel_model.modelReset.connect(self._update_channel_header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(self.view_switch)
        toolbar.addWidget(self.category_selector)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.refresh_button)
        toolbar.addWidget(self.selection_label)
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

        self.channel_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.category_sidebar = self._create_category_sidebar()
        self.channel_splitter.addWidget(self.category_sidebar)
        self.channel_stack = QStackedWidget(self.channel_splitter)
        self.channel_stack.addWidget(self.channel_table)
        self.empty_state = self._create_empty_state()
        self.channel_stack.addWidget(self.empty_state)
        self.channel_splitter.addWidget(self.channel_stack)
        self.channel_splitter.setCollapsible(0, False)
        self.channel_splitter.setStretchFactor(0, 0)
        self.channel_splitter.setStretchFactor(1, 1)
        category_width = max(190, min(320, int(QSettings().value("appearance/channel_category_width", 228))))
        self.channel_splitter.setSizes([category_width, 900])
        self.channel_splitter.splitterMoved.connect(self._save_category_width)
        layout.addWidget(self.channel_splitter, 1)

        self._create_result_drawer()
        self.view_switch.currentItemChanged.connect(self._set_view_mode)
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
        self._apply_view_mode()
        self.reload()

    def _create_category_sidebar(self):
        sidebar = CardWidget(self)
        sidebar.setObjectName("channelCategorySidebar")
        sidebar.setMinimumWidth(190)
        sidebar.setMaximumWidth(320)
        sidebar.setBorderRadius(8)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(8)

        self.category_heading = StrongBodyLabel(t("desktop.channel_categories"), sidebar)
        layout.addWidget(self.category_heading)
        self.category_tree = self._directory_tree(sidebar)
        self.category_tree.itemClicked.connect(self._category_item_clicked)
        layout.addWidget(self.category_tree, 1)

        self.smart_heading = StrongBodyLabel(t("desktop.smart_collections"), sidebar)
        layout.addWidget(self.smart_heading)
        self.smart_tree = self._directory_tree(sidebar)
        self.smart_tree.setMaximumHeight(164)
        self.smart_tree.itemClicked.connect(self._smart_item_clicked)
        layout.addWidget(self.smart_tree)
        return sidebar

    @staticmethod
    def _directory_tree(parent):
        tree = TreeWidget(parent)
        tree.setColumnCount(2)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(False)
        tree.setIndentation(0)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.setBorderVisible(False)
        tree.header().setStretchLastSection(False)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        return tree

    def _create_empty_state(self):
        state = QWidget(self)
        layout = QVBoxLayout(state)
        layout.setContentsMargins(24, 32, 24, 32)
        layout.setSpacing(10)
        layout.addStretch(1)
        icon = IconWidget(FluentIcon.SEARCH.icon(color=QColor("#64748B")), state)
        icon.setFixedSize(44, 44)
        self.empty_title = StrongBodyLabel(t("desktop.channel_center_empty"), state)
        self.empty_hint = BodyLabel(t("desktop.channel_center_empty_hint"), state)
        self.empty_clear_button = PushButton(FluentIcon.CANCEL, t("desktop.clear_filters"), state)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_clear_button.clicked.connect(self._clear_channel_filters)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.empty_title)
        layout.addWidget(self.empty_hint)
        layout.addWidget(self.empty_clear_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return state

    def _create_result_drawer(self):
        self.result_drawer = ResultDrawerCard(self)
        self.result_drawer.setObjectName("resultDrawer")
        self.result_drawer.setBorderRadius(12)
        drawer_layout = QVBoxLayout(self.result_drawer)
        drawer_layout.setContentsMargins(18, 2, 18, 16)
        drawer_layout.setSpacing(6)
        self.drawer_resize_handle = DrawerResizeHandle(self.result_drawer)
        self.drawer_resize_handle.setAccessibleName(t("desktop.resize_result_drawer"))
        self.drawer_resize_handle.setToolTip(t("desktop.resize_result_drawer_hint"))
        drawer_layout.addWidget(self.drawer_resize_handle)
        header = QHBoxLayout()
        self.results_title = BodyLabel(t("desktop.results"), self.result_drawer)
        self.play_button = AccentPushButton(FluentIcon.PLAY, t("desktop.play"), self.result_drawer)
        self.retest_result_button = AccentPushButton(FluentIcon.SPEED_HIGH, t("desktop.retest_result"), self.result_drawer)
        self.screenshot_button = PushButton(FluentIcon.PHOTO, t("desktop.stream_screenshot"), self.result_drawer)
        self.stream_button = PushButton(FluentIcon.VIDEO, t("desktop.open_play_streaming"), self.result_drawer)
        self.more_button = DropDownPushButton(FluentIcon.MORE, t("desktop.more_actions"), self.result_drawer)
        self.fullscreen_drawer_button = ToolButton(FluentIcon.FULL_SCREEN, self.result_drawer)
        self.close_drawer_button = ToolButton(FluentIcon.CLOSE, self.result_drawer)
        header.addWidget(self.results_title)
        header.addStretch(1)
        header.addWidget(self.play_button)
        header.addWidget(self.retest_result_button)
        header.addWidget(self.screenshot_button)
        header.addWidget(self.stream_button)
        header.addWidget(self.more_button)
        header.addWidget(self.fullscreen_drawer_button)
        header.addWidget(self.close_drawer_button)
        drawer_layout.addLayout(header)
        self.result_table = self._table(self.result_model, multiple=True)
        self.result_header = TableCheckBoxHeader(self.result_table)
        self.result_table.setHorizontalHeader(self.result_header)
        self.result_header.setSortIndicator(1, Qt.SortOrder.AscendingOrder)
        configure_table_columns(
            self.result_table,
            [42, 90, 105, 85, 105, 105, 85, 95, 250],
            "channel_center.results",
            fixed_widths={0: 42},
        )
        self.result_table.setItemDelegateForColumn(0, TableCheckBoxDelegate(self.result_table))
        self.result_header.toggled.connect(self._toggle_all_results)
        self.result_model.modelReset.connect(self._update_result_header)
        self.result_table.selectionModel().selectionChanged.connect(self._result_selection_changed)
        self.result_table.selectionModel().currentChanged.connect(self._result_selection_changed)
        drawer_layout.addWidget(self.result_table, 1)
        self.result_drawer.hide()
        self.drawer_animation = QPropertyAnimation(self.result_drawer, b"geometry", self)
        self.drawer_animation.setDuration(180)
        self.drawer_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._drawer_hiding = False
        self.drawer_animation.finished.connect(self._drawer_animation_finished)
        self.play_button.clicked.connect(self._open_result)
        self.retest_result_button.clicked.connect(self._request_result_retest)
        self.screenshot_button.clicked.connect(self._preview_result_screenshot)
        self.stream_button.clicked.connect(self._stream_playback)
        self.fullscreen_drawer_button.clicked.connect(self._toggle_result_drawer_fullscreen)
        self.close_drawer_button.clicked.connect(self.hide_result_drawer)
        self.drawer_resize_handle.resize_requested.connect(self._resize_result_drawer)
        self.drawer_resize_handle.resize_finished.connect(self._save_result_drawer_height)
        self.drawer_resize_handle.full_screen_requested.connect(self._toggle_result_drawer_fullscreen)
        self.result_table.doubleClicked.connect(lambda _: self._open_result())
        self.result_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_table.customContextMenuRequested.connect(self._show_result_menu)
        self.result_model.dataChanged.connect(self._result_data_changed)
        self._create_menus()
        self._update_drawer_mode_button()
        self._update_drawer_style()
        self._update_result_actions()

    def _create_menus(self):
        self.copy_action = Action(FluentIcon.COPY, t("desktop.copy_url"), self, triggered=self._copy_result)
        self.copy_stream_action = Action(FluentIcon.LINK, t("desktop.copy_stream_url"), self, triggered=self._copy_stream_url)
        self.whitelist_action = Action(FluentIcon.ADD_TO, t("desktop.add_whitelist"), self, triggered=self._add_whitelist)
        self.blacklist_action = Action(FluentIcon.REMOVE_FROM, t("desktop.add_blacklist"), self, triggered=self._add_blacklist)
        self.preview_screenshot_action = Action(FluentIcon.PHOTO, t("desktop.preview_screenshot"), self, triggered=self._preview_result_screenshot)
        self.capture_screenshot_action = Action(FluentIcon.SYNC, t("desktop.refresh_screenshot"), self, triggered=self._request_result_screenshot)
        self.result_menu = RoundMenu(parent=self)
        for action in (
            self.preview_screenshot_action,
            self.capture_screenshot_action,
            self.copy_action,
            self.copy_stream_action,
            self.whitelist_action,
            self.blacklist_action,
        ):
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
            ("screenshot_status", t("desktop.screenshot"), lambda value, _: t(f"desktop.screenshot_{value or 'not_captured'}", value or "--")),
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
        if self._drawer_fullscreen:
            return self.rect()
        horizontal_margin = 12
        bottom_margin = 8
        maximum_height = max(250, self.height() - 28)
        height = min(maximum_height, max(250, self._drawer_height))
        return QRect(
            horizontal_margin,
            self.height() - height - bottom_margin,
            max(320, self.width() - horizontal_margin * 2),
            height,
        )

    def _resize_result_drawer(self, delta: int):
        if not delta:
            return
        if self._drawer_fullscreen:
            self._drawer_fullscreen = False
            self.result_drawer.setBorderRadius(12)
            self._drawer_height = max(250, self.height() - 28)
            self._update_drawer_mode_button()
        maximum_height = max(250, self.height() - 28)
        self._drawer_height = min(
            maximum_height,
            max(250, self._drawer_height + int(delta)),
        )
        self.drawer_animation.stop()
        self.result_drawer.setGeometry(self._drawer_geometry())

    def _save_result_drawer_height(self):
        if not self._drawer_fullscreen:
            QSettings().setValue(
                "appearance/channel_result_drawer_height",
                self._drawer_height,
            )

    def _toggle_result_drawer_fullscreen(self):
        self._drawer_fullscreen = not self._drawer_fullscreen
        self.result_drawer.setBorderRadius(0 if self._drawer_fullscreen else 12)
        self.drawer_animation.stop()
        self.result_drawer.setGeometry(self._drawer_geometry())
        self.result_drawer.raise_()
        self._update_drawer_mode_button()

    def _update_drawer_mode_button(self):
        if self._drawer_fullscreen:
            self.fullscreen_drawer_button.setIcon(FluentIcon.MINIMIZE)
            text = t("desktop.restore_result_drawer")
        else:
            self.fullscreen_drawer_button.setIcon(FluentIcon.FULL_SCREEN)
            text = t("desktop.fullscreen_result_drawer")
        self.fullscreen_drawer_button.setToolTip(text)
        self.fullscreen_drawer_button.setAccessibleName(text)

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
        self.drawer_animation.setEndValue(
            QRect(
                self.result_drawer.x(),
                self.height() + 4,
                self.result_drawer.width(),
                self.result_drawer.height(),
            )
        )
        self.drawer_animation.start()

    def _drawer_animation_finished(self):
        if self._drawer_hiding:
            self.result_drawer.hide()
            self._drawer_hiding = False

    def _update_drawer_style(self):
        self.result_drawer.update()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.hide_result_drawer()
        if event.type() == QEvent.Type.MouseButtonPress and self.result_drawer.isVisible():
            widget = watched if isinstance(watched, QWidget) else None
            if (
                not self._event_position_in_drawer(event)
                and widget
                and not self._is_drawer_interaction_widget(widget)
            ):
                self.hide_result_drawer()
        return super().eventFilter(watched, event)

    def _event_position_in_drawer(self, event):
        global_position = getattr(event, "globalPosition", None)
        if not callable(global_position):
            return False
        point = self.result_drawer.mapFromGlobal(global_position().toPoint())
        return self.result_drawer.rect().contains(point)

    def _is_drawer_interaction_widget(self, widget):
        if (
            self._is_child_of(widget, self.result_drawer)
            or self._is_child_of(widget, self.channel_table)
        ):
            return True
        return widget.window() is not self.window()

    @staticmethod
    def _is_child_of(widget, parent):
        current = widget
        while current:
            if current is parent:
                return True
            current = current.parentWidget()
        return False

    def _set_view_mode(self, mode: str):
        if mode not in {"list", "category"} or mode == self._view_mode:
            return
        if self.view_switch.currentRouteKey() != mode:
            blocker = QSignalBlocker(self.view_switch)
            self.view_switch.setCurrentItem(mode)
            del blocker
        self._view_mode = mode
        QSettings().setValue("appearance/channel_center_view", mode)
        self.hide_result_drawer()
        self._apply_view_mode()
        self._load_channels()

    def _apply_view_mode(self):
        categorized = self._view_mode == "category"
        self.category_selector.setVisible(not categorized)
        self.category_sidebar.setVisible(categorized)
        self.channel_table.setColumnHidden(8, categorized)
        adaptive_columns = getattr(self.channel_table.horizontalHeader(), "_adaptive_columns", None)
        if adaptive_columns:
            adaptive_columns.fit()

    def _save_category_width(self, *_):
        if self._view_mode != "category":
            return
        sizes = self.channel_splitter.sizes()
        if sizes and sizes[0] > 0:
            QSettings().setValue("appearance/channel_category_width", sizes[0])

    @staticmethod
    def _directory_item(tree, text: str, count: int, icon, route):
        item = QTreeWidgetItem([text, str(int(count or 0))])
        item.setData(0, Qt.ItemDataRole.UserRole, route)
        item.setIcon(0, icon.icon() if hasattr(icon, "icon") else icon)
        item.setSizeHint(0, QSize(0, 36))
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tree.addTopLevelItem(item)
        return item

    def _populate_category_directory(self, categories=None):
        try:
            full_categories = (
                categories
                if categories is not None
                else self._sort_category_rows(list_categories(constants.channel_results_path))
            )
            matched_categories = (
                list_categories(constants.channel_results_path, self.search.text())
                if self.search.text()
                else full_categories
            )
        except Exception:
            full_categories, matched_categories = [], []

        full_by_name = {row["category"]: row for row in full_categories}
        matched_by_name = {row["category"]: row for row in matched_categories}
        matched_count = sum(int(row.get("channel_count") or 0) for row in matched_categories)
        matched_health = {
            "healthy": sum(int(row.get("healthy_count") or 0) for row in matched_categories),
            "warning": sum(int(row.get("warning_count") or 0) for row in matched_categories),
            "offline": sum(int(row.get("offline_count") or 0) for row in matched_categories),
            "unknown": matched_count - sum(
                int(row.get(key) or 0)
                for row in matched_categories
                for key in ("healthy_count", "warning_count", "offline_count")
            ),
        }

        category_blocker = QSignalBlocker(self.category_tree)
        smart_blocker = QSignalBlocker(self.smart_tree)
        self.category_tree.clear()
        self.smart_tree.clear()
        self._category_items = {}
        self._smart_items = {}

        self._category_items[("all", None)] = self._directory_item(
            self.category_tree,
            t("desktop.all_channels"),
            matched_count,
            FluentIcon.LIBRARY,
            ("all", None),
        )
        for category in full_by_name:
            matched_row = matched_by_name.get(category, {})
            route = ("category", category)
            self._category_items[route] = self._directory_item(
                self.category_tree,
                _category_label(category),
                int(matched_row.get("channel_count") or 0),
                FluentIcon.FOLDER,
                route,
            )
            self._category_items[route].setToolTip(0, category)

        for health, label, icon in (
            ("healthy", t("desktop.health_healthy"), FluentIcon.ACCEPT),
            ("warning", t("desktop.health_warning"), FluentIcon.INFO),
            ("offline", t("desktop.health_offline"), FluentIcon.CANCEL),
            ("unknown", t("desktop.health_unknown"), FluentIcon.QUESTION),
        ):
            route = ("health", health)
            self._smart_items[route] = self._directory_item(
                self.smart_tree,
                label,
                matched_health[health],
                icon,
                route,
            )

        current_route = (
            ("health", self._health_filter)
            if self._health_filter
            else ("category", self._category_filter)
            if self._category_filter
            else ("all", None)
        )
        item = self._category_items.get(current_route) or self._smart_items.get(current_route)
        if item is None:
            self._category_filter = None
            self._health_filter = None
            current_route = ("all", None)
            item = self._category_items.get(current_route)
        if item:
            tree = self.smart_tree if current_route[0] == "health" else self.category_tree
            tree.setCurrentItem(item)
        del category_blocker, smart_blocker

    def _sort_category_rows(self, rows):
        positions = {category: index for index, category in enumerate(self._category_order)}
        fallback = len(positions)
        return [
            row
            for _, row in sorted(
                enumerate(rows),
                key=lambda item: (
                    0 if item[1].get("category") in positions else 1,
                    positions.get(item[1].get("category"), fallback),
                    item[0],
                ),
            )
        ]

    def _sort_channels_by_category(self, rows):
        positions = {category: index for index, category in enumerate(self._category_order)}
        fallback = len(positions)
        rows.sort(
            key=lambda row: (
                0 if row.get("category") in positions else 1,
                positions.get(row.get("category"), fallback),
                row.get("category") or "",
                row.get("name") or "",
            )
        )
        return rows

    def _category_item_clicked(self, item, _column):
        route = item.data(0, Qt.ItemDataRole.UserRole)
        if not route:
            return
        self._category_filter = route[1] if route[0] == "category" else None
        self._health_filter = None
        self.smart_tree.clearSelection()
        self.hide_result_drawer()
        self._load_channels()

    def _smart_item_clicked(self, item, _column):
        route = item.data(0, Qt.ItemDataRole.UserRole)
        if not route:
            return
        self._category_filter = None
        self._health_filter = route[1]
        self.category_tree.clearSelection()
        self.hide_result_drawer()
        self._load_channels()

    def _clear_channel_filters(self):
        search_blocker = QSignalBlocker(self.search)
        self.search.clear()
        del search_blocker
        if self._view_mode == "list":
            category_blocker = QSignalBlocker(self.category_selector)
            self.category_selector.setCurrentIndex(0)
            del category_blocker
        else:
            self._category_filter = None
            self._health_filter = None
        self._populate_category_directory()
        self.hide_result_drawer()
        self._load_channels()

    def reload(self):
        selected_category = self.category_selector.currentData()
        selected_channels = self._selected_channel_keys() - self._checked_channel_keys
        checked_channels = set(self._checked_channel_keys)
        selected_result_keys = {
            row["result_key"]
            for index in self.result_table.selectionModel().selectedRows()
            if (row := self.result_model.row(index))
        }
        current_result = self.result_model.row(self.result_table.currentIndex())
        result_key = current_result.get("result_key") if current_result else None
        self._category_order = _template_category_order()
        try:
            categories = self._sort_category_rows(list_categories(constants.channel_results_path))
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
        self._populate_category_directory(categories)
        self._load_channels(selected_channels, checked_channels)
        if self._drawer_channel_key:
            self._load_results(
                self._drawer_channel_key,
                result_key,
                selected_result_keys,
            )

    def _load_channels(self, selected_keys=None, checked_keys=None):
        category = self.category_selector.currentData() if self._view_mode == "list" else self._category_filter
        health = self._health_filter if self._view_mode == "category" else None
        try:
            rows = list_channels(
                constants.channel_results_path,
                category,
                self.search.text(),
                health=health,
            )
        except Exception:
            rows = []
        self._sort_channels_by_category(rows)
        self._prepare_channel_rows(rows, checked_keys)
        self.channel_model.set_rows(rows)
        self.channel_stack.setCurrentWidget(self.channel_table if rows else self.empty_state)
        has_filter = bool(
            self.search.text().strip()
            or category
            or health
        )
        self.empty_title.setText(t("desktop.channel_center_no_match" if has_filter else "desktop.channel_center_empty"))
        self.empty_hint.setText(t("desktop.channel_center_no_match_hint" if has_filter else "desktop.channel_center_empty_hint"))
        self.empty_clear_button.setVisible(has_filter)

        selection = self.channel_table.selectionModel()
        selection.clearSelection()
        for index, row in enumerate(self.channel_model.rows):
            if row.get("channel_key") in (selected_keys or set()):
                selection.select(
                    self.channel_model.index(index, 0),
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                )
        self._update_selection_label()

    def _prepare_channel_rows(self, rows, checked_keys=None):
        selected_keys = self._checked_channel_keys if checked_keys is None else checked_keys
        try:
            result_urls = list_result_urls_by_channel(constants.channel_results_path)
            whitelist_maps = load_whitelist_maps(constants.whitelist_path)
            blacklist = get_urls_from_file(constants.blacklist_path, pattern_search=False)
        except Exception:
            result_urls, whitelist_maps, blacklist = {}, ({}, {}), []
        for row in rows:
            urls = result_urls.get(row["channel_key"], [])
            row["whitelist_count"] = sum(is_url_whitelisted(whitelist_maps, url, row["name"]) for url in urls)
            row["blacklist_count"] = sum(check_url_by_keywords(url, blacklist) for url in urls)
            row["batch_selected"] = row.get("channel_key") in selected_keys
            row.update(apply_channel_stream_state(row, self._stream_states))
        return rows

    def _load_results(self, channel_key: str, result_key=None, selected_keys=None):
        if channel_key != self._drawer_channel_key:
            self._checked_result_keys.clear()
        try:
            results = list_channel_results(constants.channel_results_path, channel_key)
        except Exception:
            results = []
        for result in results:
            result["batch_selected"] = result.get("result_key") in self._checked_result_keys
        self.result_model.set_rows(results)
        selection = self.result_table.selectionModel()
        selection.clearSelection()
        restore_keys = set(selected_keys or ())
        if result_key:
            restore_keys.add(result_key)
        first_restored_row = -1
        current_row = -1
        for index, row in enumerate(self.result_model.rows):
            if row.get("result_key") not in restore_keys:
                continue
            selection.select(
                self.result_model.index(index, 0),
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )
            if first_restored_row < 0:
                first_restored_row = index
            if row.get("result_key") == result_key:
                current_row = index
        target_row = current_row if current_row >= 0 else first_restored_row
        if target_row < 0 and self.result_model.rows:
            target_row = 0
            selection.select(
                self.result_model.index(target_row, 0),
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        if target_row >= 0:
            selection.setCurrentIndex(
                self.result_model.index(target_row, 1),
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )
        self._update_result_actions()

    def _category_changed(self, *_):
        if self._view_mode != "list":
            return
        self.hide_result_drawer()
        self._load_channels()

    def _search_changed(self, *_):
        self.hide_result_drawer()
        self._populate_category_directory()
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
        visible_keys = {row["channel_key"] for row in self.channel_model.rows}
        self._checked_channel_keys.difference_update(visible_keys)
        self._checked_channel_keys.update({
            row["channel_key"] for row in self.channel_model.rows if row.get("batch_selected")
        })
        self._update_selection_label()
        self._update_channel_header()

    def _result_data_changed(self, *_):
        self._checked_result_keys = {
            row["result_key"] for row in self.result_model.rows if row.get("batch_selected")
        }
        self._update_result_header()
        self._update_result_actions()

    def _result_selection_changed(self, *_):
        self._update_result_actions()

    def _update_result_actions(self):
        rows = self.selected_results()
        count = len(rows)
        single = count == 1
        streamable = single and rows[0].get("selected_rank") is not None
        task_idle = self._task_operation is None

        self.play_button.setEnabled(single)
        self.retest_result_button.setEnabled(count > 0 and task_idle)
        self.screenshot_button.setEnabled(single)
        self.stream_button.setEnabled(streamable)
        self.more_button.setEnabled(count > 0)

        self.preview_screenshot_action.setEnabled(single)
        self.capture_screenshot_action.setEnabled(count > 0 and task_idle)
        self.copy_action.setEnabled(count > 0)
        self.copy_stream_action.setEnabled(streamable)
        self.whitelist_action.setEnabled(count > 0)
        self.blacklist_action.setEnabled(count > 0)
        if self._screenshot_dialog and self._screenshot_dialog.isVisible():
            self._screenshot_dialog.set_capture_enabled(task_idle)

    def _toggle_all_channels(self, checked: bool):
        self.channel_model.set_all_checked(checked)

    def _update_channel_header(self):
        self.channel_header.set_check_state(self.channel_model.check_state())

    def _toggle_all_results(self, checked: bool):
        self.result_model.set_all_checked(checked)

    def _update_result_header(self):
        self.result_header.set_check_state(self.result_model.check_state())

    def _update_selection_label(self):
        count = len(self._selected_channel_keys())
        self.selection_label.setText(t("desktop.channels_selected").format(count=count))
        self.selection_label.setVisible(count > 0)
        self.add_result_button.setEnabled(count > 0)
        self.delete_channel_button.setEnabled(count > 0)
        self.retest_channel_button.setEnabled(count > 0)
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

    def _selected_channel_keys(self):
        keys = {
            row["channel_key"]
            for index in self.channel_table.selectionModel().selectedRows()
            if (row := self.channel_model.row(index))
        }
        keys.update(self._checked_channel_keys)
        return keys

    def selected_channels(self):
        keys = self._selected_channel_keys()
        if not keys:
            return []
        current_rows = {
            row["channel_key"]: row
            for row in self.channel_model.rows
            if row.get("channel_key") in keys
        }
        missing = keys - current_rows.keys()
        if missing:
            try:
                rows = [
                    row for row in list_channels(constants.channel_results_path)
                    if row.get("channel_key") in missing
                ]
            except Exception:
                rows = []
            self._prepare_channel_rows(rows)
            current_rows.update({row["channel_key"]: row for row in rows})
        return self._sort_channels_by_category(
            [current_rows[key] for key in keys if key in current_rows]
        )

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
            self._update_result_actions()
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

    def _request_result_screenshot(self):
        rows = list(self.selected_results())
        if len(rows) == 1:
            self.capture_screenshot_requested.emit(rows[0])
        elif rows:
            self.capture_screenshots_requested.emit(rows)

    def _preview_result_screenshot(self):
        rows = self.selected_results()
        if len(rows) != 1:
            return
        row = rows[0]
        if self._screenshot_dialog and self._screenshot_dialog.isVisible():
            if not self._screenshot_dialog.is_loading:
                self._screenshot_dialog.set_result(row)
                self._auto_capture_missing_screenshot(
                    self._screenshot_dialog,
                    row,
                )
            self._screenshot_dialog.raise_()
            self._screenshot_dialog.activateWindow()
            return
        dialog = StreamScreenshotDialog(row, self)
        dialog.capture_requested.connect(self._request_dialog_screenshot)
        dialog.finished.connect(self._screenshot_dialog_finished)
        self._screenshot_dialog = dialog
        dialog.set_capture_enabled(self._task_operation is None)
        dialog.open()
        self._auto_capture_missing_screenshot(dialog, row)

    def _auto_capture_missing_screenshot(self, dialog, row: dict):
        status = row.get("screenshot_status") or "not_captured"
        missing = status == "not_captured" or (
            status == "success" and not dialog.has_screenshot()
        )
        if missing and self._task_operation is None:
            dialog.request_capture()

    def _request_dialog_screenshot(self, row: dict):
        if self._task_operation is not None:
            if self._screenshot_dialog:
                self._screenshot_dialog.set_loading(False)
            return
        self.capture_screenshot_requested.emit(row)

    def _screenshot_dialog_finished(self, *_):
        self._screenshot_dialog = None

    def show_result_screenshot(self, result_key: str, notify=False):
        row = next(
            (item for item in self.result_model.rows if item.get("result_key") == result_key),
            None,
        )
        if (
            row
            and self._screenshot_dialog
            and self._screenshot_dialog.isVisible()
            and self._screenshot_dialog.result.get("result_key") == result_key
        ):
            self._screenshot_dialog.set_result(row)
            self._update_result_actions()
        if notify:
            InfoBar.success(
                t("desktop.task_completed"),
                t("desktop.capture_result_screenshot"),
                parent=self._screenshot_notification_parent(),
                position=InfoBarPosition.TOP,
            )

    def set_screenshot_capture_failed(self, message: str, notify=False):
        if self._screenshot_dialog and self._screenshot_dialog.isVisible():
            result_key = self._screenshot_dialog.result.get("result_key")
            row = next(
                (
                    item
                    for item in self.result_model.rows
                    if item.get("result_key") == result_key
                ),
                None,
            )
            if row:
                self._screenshot_dialog.set_result(row)
                self._update_result_actions()
            else:
                self._screenshot_dialog.set_error(message)
        if notify:
            InfoBar.error(
                t("desktop.task_failed"),
                message.splitlines()[-1] if message else t("desktop.screenshot_failed"),
                parent=self._screenshot_notification_parent(),
                position=InfoBarPosition.TOP,
                duration=8000,
            )

    def _screenshot_notification_parent(self):
        if self._screenshot_dialog and self._screenshot_dialog.isVisible():
            return self._screenshot_dialog
        return self

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
        category.addItems([
            row["category"]
            for row in self._sort_category_rows(list_categories(constants.channel_results_path))
        ])
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
        deleted_keys = {row["channel_key"] for row in rows}
        delete_channels([row["name"] for row in rows])
        delete_channel_records(constants.channel_results_path, list(deleted_keys))
        self._checked_channel_keys.difference_update(deleted_keys)
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
        self._update_result_actions()

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
        self._update_result_actions()

    def retranslate(self):
        self.view_switch.items["list"].setText(t("desktop.channel_view_list"))
        self.view_switch.items["category"].setText(t("desktop.channel_view_category"))
        self.category_heading.setText(t("desktop.channel_categories"))
        self.smart_heading.setText(t("desktop.smart_collections"))
        self.search.setPlaceholderText(t("desktop.search_channels"))
        self.refresh_button.setToolTip(t("desktop.refresh"))
        self.empty_clear_button.setText(t("desktop.clear_filters"))
        self.add_channel_button.setText(t("desktop.add_channel"))
        self.add_result_button.setText(t("desktop.add_result"))
        self.delete_channel_button.setText(t("desktop.delete_channel"))
        self.retest_channel_button.setText(t("desktop.retest_channel"))
        self.stream_selected_button.setText(t("desktop.open_selected_streams"))
        self.play_button.setText(t("desktop.play"))
        self.retest_result_button.setText(t("desktop.retest_result"))
        self.screenshot_button.setText(t("desktop.stream_screenshot"))
        self.stream_button.setText(t("desktop.open_play_streaming"))
        self.more_button.setText(t("desktop.more_actions"))
        self.drawer_resize_handle.setAccessibleName(t("desktop.resize_result_drawer"))
        self.drawer_resize_handle.setToolTip(t("desktop.resize_result_drawer_hint"))
        self._update_drawer_mode_button()
        for action, key in (
            (self.copy_action, "desktop.copy_url"),
            (self.copy_stream_action, "desktop.copy_stream_url"),
            (self.whitelist_action, "desktop.add_whitelist"),
            (self.blacklist_action, "desktop.add_blacklist"),
            (self.preview_screenshot_action, "desktop.preview_screenshot"),
            (self.capture_screenshot_action, "desktop.refresh_screenshot"),
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
