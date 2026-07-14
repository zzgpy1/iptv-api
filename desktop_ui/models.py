import os
from typing import Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from utils.config import config
from utils.i18n import t


class MappingTableModel(QAbstractTableModel):
    def __init__(self, columns: list[tuple[str, str, Callable | None]], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict] = []

    def set_rows(self, rows: list[dict]):
        self.beginResetModel()
        self.rows = list(rows)
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_rows = []
        self.rows = []
        self.reload()

    def reload(self):
        self.beginResetModel()
        self.all_rows = []
        for key, value in config.config.items("Settings"):
            env_names = (key, key.upper(), f"Settings_{key}", f"SETTINGS_{key.upper()}")
            env_name = next((name for name in env_names if os.getenv(name) is not None), None)
            self.all_rows.append({"key": key, "value": value, "source": env_name or t("desktop.config_file")})
        self.rows = list(self.all_rows)
        self.endResetModel()

    def filter(self, text: str):
        term = text.strip().lower()
        self.beginResetModel()
        self.rows = [row for row in self.all_rows if not term or term in row["key"].lower() or term in str(row["value"]).lower()]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = ("key", "value", "source")[index.column()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return row[key]
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 2 and row["source"] != t("desktop.config_file"):
            return t("desktop.environment_override")
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != 1 or not index.isValid():
            return False
        row = self.rows[index.row()]
        if row["source"] != t("desktop.config_file"):
            return False
        row["value"] = str(value)
        self.dataChanged.emit(index, index, [role])
        return True

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 1 and self.rows[index.row()]["source"] == t("desktop.config_file"):
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return (t("desktop.config_key"), t("desktop.config_value"), t("desktop.config_source"))[section]
        return super().headerData(section, orientation, role)

    def save(self):
        for row in self.all_rows:
            if row["source"] == t("desktop.config_file"):
                config.set("Settings", row["key"], row["value"])
        config.save()
