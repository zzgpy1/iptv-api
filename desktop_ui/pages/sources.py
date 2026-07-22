import os
from collections import defaultdict

from PySide6.QtCore import QIODevice, QSaveFile, Signal, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, FlowLayout, FluentIcon, InfoBar, InfoBarPosition, PushButton, ToolButton, isDarkTheme

import utils.constants as constants
from desktop_ui.widgets import AccentPushButton, AppPlainTextEdit, AppSearchLineEdit, DangerPushButton, PageTitle, configure_table_columns
from utils.config import config, resource_path
from utils.i18n import t


class AliasTagsEditor(QWidget):
    changed = Signal()
    colors = ("#2563EB", "#7C3AED", "#DB2777", "#059669", "#D97706", "#0891B2")

    def __init__(self, aliases=None, parent=None):
        super().__init__(parent)
        self.aliases = list(aliases or [])
        self.tags = QWidget(self)
        self.flow = FlowLayout(self.tags, isTight=True)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.flow.setHorizontalSpacing(5)
        self.flow.setVerticalSpacing(4)
        self.edit_button = ToolButton(FluentIcon.PENCIL_INK, self)
        self.edit_button.setToolTip(t("desktop.edit_aliases"))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 4, 3)
        layout.setSpacing(6)
        layout.addWidget(self.tags, 1)
        layout.addWidget(self.edit_button)
        self.edit_button.clicked.connect(self.edit)
        self._rebuild()

    def _rebuild(self):
        self.flow.removeAllWidgets()
        foreground = "#F8FAFC"
        for index, alias in enumerate(self.aliases[:5]):
            tag = QLabel(alias, self.tags)
            tag.setStyleSheet(
                f"QLabel {{ color: {foreground}; background-color: {self.colors[index % len(self.colors)]}; "
                "border-radius: 9px; padding: 2px 8px; }"
            )
            self.flow.addWidget(tag)
        if len(self.aliases) > 5:
            more = QLabel(f"+{len(self.aliases) - 5}", self.tags)
            background = "#475569" if isDarkTheme() else "#E2E8F0"
            color = "#F8FAFC" if isDarkTheme() else "#334155"
            more.setStyleSheet(f"QLabel {{ color: {color}; background-color: {background}; border-radius: 9px; padding: 2px 8px; }}")
            self.flow.addWidget(more)
        self.setToolTip("\n".join(self.aliases))

    def edit(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(t("desktop.edit_aliases"))
        dialog.resize(480, 360)
        layout = QVBoxLayout(dialog)
        hint = BodyLabel(t("desktop.alias_editor_hint"), dialog)
        editor = AppPlainTextEdit(dialog)
        editor.setPlainText("\n".join(self.aliases))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save, parent=dialog)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("desktop.cancel"))
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("desktop.save"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(hint)
        layout.addWidget(editor, 1)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = [part.strip() for line in editor.toPlainText().splitlines() for part in line.split(",") if part.strip()]
        self.aliases = list(dict.fromkeys(values))
        self._rebuild()
        self.changed.emit()


class SourceEditor(QWidget):
    def __init__(self, kind: str, path_provider, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.path_provider = path_provider
        self.rows = []
        self.comments = defaultdict(list)
        self.group_order = []
        self._syncing = False
        self.loaded = False
        self.raw_editor = AppPlainTextEdit(self)
        self.raw_editor.setLineWrapMode(AppPlainTextEdit.LineWrapMode.NoWrap)
        self.table = QTableWidget(self)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.search = AppSearchLineEdit(self)
        self.search.setPlaceholderText(t("desktop.search_source_data"))
        self.search.setMaximumWidth(320)
        self.add_button = AccentPushButton(FluentIcon.ADD, t("desktop.add_item"), self)
        self.delete_button = DangerPushButton(FluentIcon.DELETE, t("desktop.delete_item"), self)
        self.mode_button = ToolButton(FluentIcon.PENCIL_INK, self)
        self.mode_button.setToolTip(t("desktop.open_raw_editor"))

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(2, 2, 2, 2)
        toolbar.setSpacing(8)
        toolbar.addWidget(self.search)
        toolbar.addStretch(1)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.mode_button)
        visual = QWidget(self)
        visual_layout = QVBoxLayout(visual)
        visual_layout.setContentsMargins(0, 0, 0, 0)
        visual_layout.addWidget(self.table)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(visual)
        self.stack.addWidget(self.raw_editor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(toolbar)
        layout.addWidget(self.stack, 1)
        self.table.itemChanged.connect(self._visual_changed)
        self.add_button.clicked.connect(self.add_item)
        self.delete_button.clicked.connect(self.delete_items)
        self.mode_button.clicked.connect(self.toggle_mode)
        self.search.textChanged.connect(self._filter_rows)

    def path(self):
        return resource_path(self.path_provider(), persistent=True)

    def load(self):
        try:
            with open(self.path(), "r", encoding="utf-8") as file:
                content = file.read()
        except FileNotFoundError:
            content = ""
        self.raw_editor.setPlainText(content)
        self.raw_editor.document().setModified(False)
        self._parse(content)
        self._rebuild_table()
        self.loaded = True

    def save(self):
        if self.stack.currentIndex() == 0:
            self._visual_changed()
        path = self.path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        target = QSaveFile(path)
        if target.open(QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Text):
            target.write(self.raw_editor.toPlainText().encode("utf-8"))
            if target.commit():
                self.raw_editor.document().setModified(False)
                return path, ""
        return "", target.errorString()

    def toggle_mode(self):
        if self.stack.currentIndex() == 0:
            self.stack.setCurrentIndex(1)
            self.add_button.hide()
            self.delete_button.hide()
            self.mode_button.setIcon(FluentIcon.TILES)
            self.mode_button.setToolTip(t("desktop.open_visual_editor"))
        else:
            self._parse(self.raw_editor.toPlainText())
            self._rebuild_table()
            self.stack.setCurrentIndex(0)
            self.add_button.show()
            self.delete_button.show()
            self.mode_button.setIcon(FluentIcon.PENCIL_INK)
            self.mode_button.setToolTip(t("desktop.open_raw_editor"))
        self._filter_rows()

    def _parse(self, content: str):
        self.rows = []
        self.comments = defaultdict(list)
        self.group_order = []
        section = ""
        for raw in content.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                self.comments[section].append(raw)
                continue
            if self.kind == "template" and line.endswith(",#genre#"):
                section = line.rsplit(",#genre#", 1)[0]
                if section not in self.group_order:
                    self.group_order.append(section)
                continue
            if self.kind == "subscribe" and line.upper() == "[WHITELIST]":
                section = "WHITELIST"
                continue
            if self.kind == "whitelist" and line.upper() == "[KEYWORDS]":
                section = "KEYWORDS"
                continue
            if self.kind == "alias" and "," not in line:
                self.comments[section].append(raw)
                continue
            self._parse_data_line(section, line)

    def _parse_data_line(self, section: str, line: str):
        if self.kind == "template":
            self.rows.append({"group": section, "name": line})
        elif self.kind == "local":
            name, separator, value = line.partition(",")
            self.rows.append({"channel": name if separator else "", "url": value if separator else name})
        elif self.kind == "subscribe":
            url, separator, options = line.partition(" ")
            self.rows.append({"whitelist": section == "WHITELIST", "url": url, "options": options.strip() if separator else ""})
        elif self.kind == "epg":
            url, separator, options = line.partition(" ")
            self.rows.append({"url": url, "options": options.strip() if separator else ""})
        elif self.kind == "whitelist":
            channel, separator, value = line.partition(",")
            self.rows.append({
                "rule_type": "keyword" if section == "KEYWORDS" else "exact",
                "channel": channel if separator else "",
                "value": value if separator else channel,
            })
        elif self.kind == "blacklist":
            self.rows.append({"keyword": line})
        elif self.kind == "alias":
            parts = [part.strip() for part in line.split(",")]
            canonical = parts[0]
            aliases = parts[1:] or [""]
            existing = next((row for row in self.rows if row["canonical"] == canonical), None)
            if existing:
                existing["aliases"] = list(dict.fromkeys(existing["aliases"] + aliases))
            else:
                self.rows.append({"canonical": canonical, "aliases": list(dict.fromkeys(aliases))})

    def _headers(self):
        return {
            "template": [t("name.channel"), t("desktop.column_category")],
            "local": [t("name.channel"), t("desktop.source_url")],
            "subscribe": [t("desktop.source_url"), t("desktop.column_whitelist"), t("desktop.source_options")],
            "epg": [t("desktop.source_url"), t("desktop.source_options")],
            "whitelist": [t("name.channel"), t("desktop.column_match"), t("desktop.column_rule")],
            "blacklist": [t("desktop.keyword")],
            "alias": [t("desktop.column_canonical"), t("desktop.column_aliases")],
        }[self.kind]

    def _column_widths(self):
        return {
            "template": [260, 160],
            "local": [180, 520],
            "subscribe": [520, 85, 260],
            "epg": [520, 260],
            "whitelist": [180, 420, 110],
            "blacklist": [520],
            "alias": [180, 520],
        }[self.kind]

    def _rebuild_table(self):
        self._syncing = True
        headers = self._headers()
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(self.rows))
        for row_index, row in enumerate(self.rows):
            self._populate_row(row_index, row)
        configure_table_columns(self.table, self._column_widths(), f"sources.{self.kind}")
        if self.kind == "alias":
            self.table.verticalHeader().setDefaultSectionSize(46)
        self._syncing = False
        self._filter_rows()

    def _populate_row(self, row_index: int, row: dict):
        if self.kind == "subscribe":
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if row.get("whitelist") else Qt.CheckState.Unchecked)
            self._set_text_item(row_index, 0, row.get("url", ""))
            self.table.setItem(row_index, 1, item)
            self._set_text_item(row_index, 2, row.get("options", ""))
            return
        if self.kind == "whitelist":
            self._set_text_item(row_index, 0, row.get("channel", ""))
            self._set_text_item(row_index, 1, row.get("value", ""))
            self._set_combo(row_index, 2, [(t("desktop.rule_exact"), "exact"), (t("desktop.rule_keyword"), "keyword")], row.get("rule_type"))
            return
        if self.kind == "alias":
            self._set_text_item(row_index, 0, row.get("canonical", ""))
            aliases = AliasTagsEditor(row.get("aliases", []), self.table)
            aliases.changed.connect(self._visual_changed)
            self.table.setCellWidget(row_index, 1, aliases)
            return
        keys = {
            "template": ("name", "group"),
            "local": ("channel", "url"),
            "epg": ("url", "options"),
            "blacklist": ("keyword",),
        }[self.kind]
        for column, key in enumerate(keys):
            self._set_text_item(row_index, column, row.get(key, ""))

    def _set_text_item(self, row: int, column: int, value: str):
        self.table.setItem(row, column, QTableWidgetItem(value))

    def _set_combo(self, row: int, column: int, options, value):
        combo = ComboBox(self.table)
        for label, data in options:
            combo.addItem(label, userData=data)
        target = next((index for index in range(combo.count()) if combo.itemData(index) == value), 0)
        combo.setCurrentIndex(target)
        combo.currentIndexChanged.connect(self._visual_changed)
        self.table.setCellWidget(row, column, combo)

    def _visual_changed(self, *_):
        if self._syncing:
            return
        self.rows = [self._read_row(row) for row in range(self.table.rowCount())]
        self.raw_editor.setPlainText(self._serialize())

    def _read_row(self, row: int):
        text = lambda column: self.table.item(row, column).text().strip() if self.table.item(row, column) else ""
        if self.kind == "template":
            return {"group": text(1), "name": text(0)}
        if self.kind == "local":
            return {"channel": text(0), "url": text(1)}
        if self.kind == "subscribe":
            return {"whitelist": self.table.item(row, 1).checkState() == Qt.CheckState.Checked, "url": text(0), "options": text(2)}
        if self.kind == "epg":
            return {"url": text(0), "options": text(1)}
        if self.kind == "whitelist":
            return {"rule_type": self.table.cellWidget(row, 2).currentData(), "channel": text(0), "value": text(1)}
        if self.kind == "blacklist":
            return {"keyword": text(0)}
        aliases = self.table.cellWidget(row, 1)
        return {"canonical": text(0), "aliases": list(aliases.aliases)}

    def _serialize(self):
        lines = []
        if self.kind == "template":
            groups = list(dict.fromkeys(self.group_order + [row["group"] for row in self.rows if row["group"]]))
            lines.extend(self.comments.get("", []))
            for group in groups:
                lines.append(f"{group},#genre#")
                lines.extend(self.comments.get(group, []))
                lines.extend(row["name"] for row in self.rows if row["group"] == group and row["name"])
                lines.append("")
        elif self.kind == "subscribe":
            lines.extend(self.comments.get("", []))
            lines.extend(self._subscription_line(row) for row in self.rows if not row["whitelist"] and row["url"])
            lines.extend(["", "[WHITELIST]"])
            lines.extend(self.comments.get("WHITELIST", []))
            lines.extend(self._subscription_line(row) for row in self.rows if row["whitelist"] and row["url"])
        elif self.kind == "whitelist":
            lines.extend(self.comments.get("", []))
            lines.extend(self._whitelist_line(row) for row in self.rows if row["rule_type"] == "exact" and row["value"])
            lines.extend(["", "[KEYWORDS]"])
            lines.extend(self.comments.get("KEYWORDS", []))
            lines.extend(self._whitelist_line(row) for row in self.rows if row["rule_type"] == "keyword" and row["value"])
        elif self.kind == "alias":
            lines.extend(self.comments.get("", []))
            grouped = defaultdict(list)
            for row in self.rows:
                for value in row["aliases"]:
                    if row["canonical"] and value:
                        grouped[row["canonical"]].append(value)
            lines.extend(f"{name},{','.join(aliases)}" for name, aliases in grouped.items())
        else:
            lines.extend(self.comments.get("", []))
            for row in self.rows:
                value = self._simple_line(row)
                if value:
                    lines.append(value)
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _subscription_line(row):
        return f"{row['url']} {row['options']}".rstrip()

    @staticmethod
    def _whitelist_line(row):
        return f"{row['channel']},{row['value']}" if row["channel"] else row["value"]

    def _simple_line(self, row):
        if self.kind == "local":
            return f"{row['channel']},{row['url']}" if row["channel"] else row["url"]
        if self.kind == "epg":
            return f"{row['url']} {row['options']}".rstrip()
        return row.get("keyword", "")

    def add_item(self):
        self.search.clear()
        defaults = {
            "template": {"group": "", "name": ""},
            "local": {"channel": "", "url": ""},
            "subscribe": {"whitelist": False, "url": "", "options": ""},
            "epg": {"url": "", "options": ""},
            "whitelist": {"rule_type": "exact", "channel": "", "value": ""},
            "blacklist": {"keyword": ""},
            "alias": {"canonical": "", "aliases": []},
        }
        if self.kind == "template" and self.rows:
            defaults["template"]["group"] = self.rows[-1].get("group", "")
        self.rows.append(defaults[self.kind])
        self._rebuild_table()
        row = self.table.rowCount() - 1
        self.table.selectRow(row)
        edit_column = 1 if self.kind == "local" else 0
        self.table.editItem(self.table.item(row, edit_column))

    def delete_items(self):
        selected = sorted({index.row() for index in self.table.selectionModel().selectedRows()}, reverse=True)
        for row in selected:
            del self.rows[row]
        if selected:
            self._rebuild_table()
            self._visual_changed()

    def _filter_rows(self, *_):
        term = self.search.text().strip().lower()
        if self.stack.currentIndex() == 1:
            cursor = self.raw_editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.raw_editor.setTextCursor(cursor)
            if term:
                self.raw_editor.find(term)
            return
        for index, row in enumerate(self.rows):
            values = []
            for value in row.values():
                values.extend(value if isinstance(value, list) else [value])
            matches = not term or term in " ".join(str(value) for value in values).lower()
            self.table.setRowHidden(index, not matches)

    def retranslate(self):
        self.add_button.setText(t("desktop.add_item"))
        self.delete_button.setText(t("desktop.delete_item"))
        self.search.setPlaceholderText(t("desktop.search_source_data"))
        self.mode_button.setToolTip(t("desktop.open_visual_editor" if self.stack.currentIndex() else "desktop.open_raw_editor"))
        self._rebuild_table()


class SourcesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sourcesPage")
        self.path_specs = [
            ("desktop.template", "template", lambda: config.source_file, FluentIcon.LAYOUT),
            ("name.local", "local", lambda: constants.local_path, FluentIcon.FOLDER),
            ("name.subscribe", "subscribe", lambda: constants.subscribe_path, FluentIcon.CLOUD_DOWNLOAD),
            ("name.epg", "epg", lambda: constants.epg_path, FluentIcon.CALENDAR),
            ("name.whitelist", "whitelist", lambda: constants.whitelist_path, FluentIcon.ACCEPT),
            ("desktop.blacklist", "blacklist", lambda: constants.blacklist_path, FluentIcon.HIDE),
            ("desktop.alias", "alias", lambda: constants.alias_path, FluentIcon.TAG),
        ]
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.editors = []
        for key, kind, provider, icon in self.path_specs:
            editor = SourceEditor(kind, provider, self)
            self.editors.append(editor)
            self.tabs.addTab(editor, icon.icon(), t(key))
        self.save_button = AccentPushButton(FluentIcon.SAVE, t("desktop.save"), self)
        self.reload_button = PushButton(FluentIcon.SYNC, t("desktop.reload"), self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        self.title = PageTitle(FluentIcon.CLOUD_DOWNLOAD, t("desktop.sources"), self)
        self.title.addWidget(self.reload_button)
        self.title.addWidget(self.save_button)
        layout.addWidget(self.title)
        layout.addWidget(self.tabs, 1)
        self.reload_button.clicked.connect(self.load)
        self.save_button.clicked.connect(self.save)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.load()

    def current_editor(self):
        return self.editors[max(0, self.tabs.currentIndex())]

    def load(self):
        self.current_editor().load()

    def _tab_changed(self, _index):
        if not self.current_editor().loaded:
            self.current_editor().load()

    def save(self):
        path, error = self.current_editor().save()
        if path:
            InfoBar.success(t("desktop.saved"), path, parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.error(t("name.error"), error, parent=self, position=InfoBarPosition.TOP)

    def retranslate(self):
        self.title.setText(t("desktop.sources"))
        self.save_button.setText(t("desktop.save"))
        self.reload_button.setText(t("desktop.reload"))
        for index, ((key, _, _, _), editor) in enumerate(zip(self.path_specs, self.editors)):
            self.tabs.setTabText(index, t(key))
            editor.retranslate()
