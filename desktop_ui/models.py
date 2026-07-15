import os
import re
from typing import Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

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
    def __init__(self, columns: list[tuple[str, str, Callable | None]], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict] = []

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
