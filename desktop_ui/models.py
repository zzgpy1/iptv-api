import os
import re
from collections import OrderedDict, deque
from typing import Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QSize, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkRequest
from qfluentwidgets import FluentIcon

from utils.config import config, resource_path
from utils.i18n import get_language, t


CONFIG_OPTIONS = {
    "update_time_position": ["top", "bottom"],
    "update_mode": ["interval", "time"],
    "public_scheme": ["http", "https"],
    "performance_mode": ["auto", "powersave", "balance", "fast"],
    "ipv_type": ["ipv4", "ipv6", "all"],
    "ipv_type_prefer": ["ipv4", "ipv6", "auto"],
    "logo_type": ["png", "jpg", "jpeg"],
    "rtmp_transcode_mode": ["copy", "auto"],
}


def _config_descriptions() -> dict[str, str]:
    path = resource_path("config/config.ini")
    descriptions = {}
    pending = ""
    english = get_language().startswith("en")
    try:
        with open(path, "r", encoding="utf-8") as file:
            for raw in file:
                line = raw.strip()
                if line.startswith("#"):
                    text = line[1:].strip()
                    parts = text.split(" | ", 1)
                    pending = parts[1] if english and len(parts) > 1 else parts[0]
                elif line.startswith(";"):
                    pending = ""
                elif "=" in line and not line.startswith("["):
                    key = line.split("=", 1)[0].strip()
                    descriptions[key] = pending
                    pending = ""
    except OSError:
        return {}
    return descriptions


def _config_kind(key: str, value: str) -> str:
    if value.strip().lower() in {"true", "false"}:
        return "bool"
    if key in CONFIG_OPTIONS:
        return "options"
    if re.fullmatch(r"-?\d+", value.strip()):
        return "int"
    if re.fullmatch(r"-?\d+\.\d+", value.strip()):
        return "float"
    return "text"


class MappingTableModel(QAbstractTableModel):
    def __init__(self, columns: list[tuple[str, str, Callable | None]], parent=None, checkable_key: str | None = None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict] = []
        self.checkable_key = checkable_key

    def set_rows(self, rows: list[dict]):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def set_columns(self, columns: list[tuple[str, str, Callable | None]]):
        self.beginResetModel()
        self.columns = columns
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row = self.rows[index.row()]
        key, _, formatter = self.columns[index.column()]
        value = row.get(key)
        if role == Qt.ItemDataRole.DisplayRole:
            return formatter(value, row) if formatter else "" if value is None else str(value)
        if role == Qt.ItemDataRole.CheckStateRole and key == self.checkable_key:
            return Qt.CheckState.Checked if value else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.UserRole:
            return row
        if role == Qt.ItemDataRole.ForegroundRole and key == "health":
            return {
                "healthy": QColor("#16a34a"),
                "warning": QColor("#d97706"),
                "offline": QColor("#dc2626"),
                "unknown": QColor("#64748b"),
            }.get(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, (int, float)):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.CheckStateRole:
            return False
        key = self.columns[index.column()][0]
        if key != self.checkable_key:
            return False
        self.rows[index.row()][key] = value == Qt.CheckState.Checked.value or value == Qt.CheckState.Checked
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        return True

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and self.columns[index.column()][0] == self.checkable_key:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section][1]
        return super().headerData(section, orientation, role)

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if column < 0 or column >= len(self.columns):
            return
        key = self.columns[column][0]
        self.layoutAboutToBeChanged.emit()
        self.rows.sort(
            key=lambda row: (row.get(key) is None, row.get(key)),
            reverse=order == Qt.SortOrder.DescendingOrder,
        )
        self.layoutChanged.emit()

    def row(self, index: QModelIndex | int) -> dict | None:
        row_index = index if isinstance(index, int) else index.row()
        return self.rows[row_index] if 0 <= row_index < len(self.rows) else None

    def check_state(self):
        if not self.checkable_key or not self.rows:
            return Qt.CheckState.Unchecked
        checked = sum(bool(row.get(self.checkable_key)) for row in self.rows)
        if checked == 0:
            return Qt.CheckState.Unchecked
        if checked == len(self.rows):
            return Qt.CheckState.Checked
        return Qt.CheckState.PartiallyChecked

    def set_all_checked(self, checked: bool):
        if not self.checkable_key or not self.rows:
            return
        for row in self.rows:
            row[self.checkable_key] = checked
        column = next((index for index, item in enumerate(self.columns) if item[0] == self.checkable_key), 0)
        self.dataChanged.emit(
            self.index(0, column),
            self.index(len(self.rows) - 1, column),
            [Qt.ItemDataRole.CheckStateRole],
        )


class ChannelLogoLoader(QObject):
    icon_ready = Signal(str)

    def __init__(self, parent=None, max_entries: int = 512, max_concurrent: int = 6):
        super().__init__(parent)
        self._icons = OrderedDict()
        self._queued = set()
        self._queue = deque()
        self._active = {}
        self._max_entries = max_entries
        self._max_concurrent = max_concurrent
        self._fallback_icon = FluentIcon.VIDEO.icon()
        self._network = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self._network)
        cache_dir = os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation), "channel-logos")
        cache.setCacheDirectory(cache_dir)
        cache.setMaximumCacheSize(64 * 1024 * 1024)
        self._network.setCache(cache)

    @property
    def fallback_icon(self):
        return self._fallback_icon

    def icon(self, logo: str):
        if logo in self._icons:
            self._icons.move_to_end(logo)
            return self._icons[logo]
        url = QUrl(logo)
        if url.isLocalFile():
            icon = QIcon(url.toLocalFile())
        elif not url.scheme():
            icon = QIcon(logo)
        else:
            self._enqueue(logo, url)
            return None
        if not icon.isNull():
            self._store(logo, icon)
            return icon
        self._store(logo, self._fallback_icon)
        return self._fallback_icon

    def _enqueue(self, logo: str, url: QUrl):
        if logo in self._queued or logo in self._active:
            return
        self._queued.add(logo)
        self._queue.append((logo, url))
        self._start_next()

    def _start_next(self):
        while self._queue and len(self._active) < self._max_concurrent:
            logo, url = self._queue.popleft()
            self._queued.discard(logo)
            request = QNetworkRequest(url)
            request.setAttribute(
                QNetworkRequest.Attribute.CacheLoadControlAttribute,
                QNetworkRequest.CacheLoadControl.PreferCache,
            )
            reply = self._network.get(request)
            self._active[logo] = reply
            reply.finished.connect(lambda value=logo, item=reply: self._loaded(value, item))

    def _loaded(self, logo: str, reply):
        self._active.pop(logo, None)
        pixmap = QPixmap()
        if reply.error() == reply.NetworkError.NoError and pixmap.loadFromData(reply.readAll()):
            self._store(logo, QIcon(pixmap))
        else:
            self._store(logo, self._fallback_icon)
        reply.deleteLater()
        self.icon_ready.emit(logo)
        self._start_next()

    def _store(self, logo: str, icon: QIcon):
        self._icons[logo] = icon
        self._icons.move_to_end(logo)
        while len(self._icons) > self._max_entries:
            self._icons.popitem(last=False)


class ChannelTableModel(MappingTableModel):
    def __init__(self, columns, parent=None, checkable_key: str | None = None, logo_loader: ChannelLogoLoader | None = None):
        super().__init__(columns, parent, checkable_key)
        self._logo_loader = logo_loader or ChannelLogoLoader(self)
        self._logo_loader.icon_ready.connect(self._logo_loaded)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role == Qt.ItemDataRole.DecorationRole:
            key = self.columns[index.column()][0]
            if key == "name":
                logo = str(self.rows[index.row()].get("logo") or "")
                if logo:
                    icon = self._logo_loader.icon(logo)
                    if icon:
                        return icon
                return self._logo_loader.fallback_icon
        if role == Qt.ItemDataRole.SizeHintRole and index.isValid() and self.columns[index.column()][0] == "name":
            return QSize(180, 38)
        return super().data(index, role)

    def _logo_loaded(self, logo: str):
        for row_index, row in enumerate(self.rows):
            if row.get("logo") == logo:
                column = next((i for i, item in enumerate(self.columns) if item[0] == "name"), 0)
                index = self.index(row_index, column)
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])


class ConfigTableModel(QAbstractTableModel):
    KindRole = Qt.ItemDataRole.UserRole + 1
    OptionsRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_rows = []
        self.rows = []
        self.reload()

    def reload(self):
        self.beginResetModel()
        self.all_rows = []
        descriptions = _config_descriptions()
        for key, value in config.config.items("Settings"):
            if key == "language":
                continue
            env_names = (key, key.upper(), f"Settings_{key}", f"SETTINGS_{key.upper()}")
            env_name = next((name for name in env_names if os.getenv(name) is not None), None)
            description = descriptions.get(key, "")
            if env_name:
                description = f"{description} · {t('desktop.environment_override')}: {env_name}"
            self.all_rows.append({
                "key": key,
                "value": value,
                "description": description,
                "env_name": env_name,
                "kind": _config_kind(key, value),
                "options": CONFIG_OPTIONS.get(key, []),
            })
        self.rows = list(self.all_rows)
        self.endResetModel()

    def filter(self, text: str):
        term = text.strip().lower()
        self.beginResetModel()
        self.rows = [
            row for row in self.all_rows
            if not term or term in row["key"].lower() or term in str(row["value"]).lower()
            or term in row["description"].lower()
        ]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = ("key", "value", "description")[index.column()]
        if role == Qt.ItemDataRole.DisplayRole and index.column() == 1 and not row["env_name"]:
            return ""
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return row[key]
        if role == self.KindRole:
            return row["kind"]
        if role == self.OptionsRole:
            return row["options"]
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 2:
            return row["description"]
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != 1 or not index.isValid():
            return False
        row = self.rows[index.row()]
        if row["env_name"]:
            return False
        if row["kind"] == "bool":
            enabled = value if isinstance(value, bool) else str(value).lower() == "true"
            row["value"] = "True" if enabled else "False"
        else:
            row["value"] = str(value)
        self.dataChanged.emit(index, index, [role, Qt.ItemDataRole.DisplayRole])
        return True

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 1 and not self.rows[index.row()]["env_name"]:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return (t("desktop.config_key"), t("desktop.config_value"), t("desktop.config_description"))[section]
        return super().headerData(section, orientation, role)

    def save(self):
        for row in self.all_rows:
            if not row["env_name"]:
                config.set("Settings", row["key"], row["value"])
        config.save()
