from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QStyledItemDelegate, QTimeEdit, QToolTip, QWidget
from qfluentwidgets import ComboBox, DoubleSpinBox, EditableComboBox, FluentIcon, LineEdit, SpinBox, SwitchButton, TableItemDelegate, TimeEdit, ToolButton

from desktop_ui.models import ConfigTableModel


def _draw_focused_border(widget):
    if not widget.hasFocus():
        return
    painter = QPainter(widget)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillRect(5, widget.height() - 2, max(0, widget.width() - 10), 2, widget.focusedBorderColor())


class SettingsLineEdit(LineEdit):
    def paintEvent(self, event):
        QLineEdit.paintEvent(self, event)
        _draw_focused_border(self)


class SettingsTimeEdit(TimeEdit):
    def paintEvent(self, event):
        QTimeEdit.paintEvent(self, event)
        _draw_focused_border(self)


class TimeListEditor(QWidget):
    valueChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._times = []
        self.display = SettingsLineEdit(self)
        self.display.setPlaceholderText("08:00, 18:30")
        self.picker = SettingsTimeEdit(self)
        self.picker.setDisplayFormat("HH:mm")
        self.add_button = ToolButton(FluentIcon.ADD, self)
        self.clear_button = ToolButton(FluentIcon.DELETE, self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.display, 1)
        layout.addWidget(self.picker)
        layout.addWidget(self.add_button)
        layout.addWidget(self.clear_button)
        self.add_button.clicked.connect(self._add_time)
        self.clear_button.clicked.connect(self._clear)
        self.display.editingFinished.connect(self._commit_text)

    def setValue(self, value):
        self._times = sorted({part.strip() for part in str(value or "").split(",") if part.strip()})
        self._sync()

    def value(self):
        return ",".join(self._times)

    def _add_time(self):
        value = self.picker.time().toString("HH:mm")
        if value not in self._times:
            self._times.append(value)
            self._times.sort()
            self._sync(True)

    def _clear(self):
        if self._times:
            self._times = []
            self._sync(True)

    def _commit_text(self):
        values = []
        for part in self.display.text().split(","):
            pieces = part.strip().split(":", 1)
            if len(pieces) != 2:
                continue
            try:
                hour, minute = (int(value) for value in pieces)
            except ValueError:
                continue
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                values.append(f"{hour:02d}:{minute:02d}")
        self._times = sorted(set(values))
        self._sync(True)

    def _sync(self, emit=False):
        self.display.setText(", ".join(self._times))
        if emit:
            self.valueChanged.emit(self.value())


class WheelFocusFilter(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._owners = {}

    def register(self, editor):
        widgets = [editor]
        if hasattr(editor, "lineEdit"):
            widgets.append(editor.lineEdit())
        for widget in widgets:
            self._owners[widget] = editor
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        editor = self._owners.get(watched)
        if not editor:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.FocusIn and event.reason() == Qt.FocusReason.MouseFocusReason:
            if QApplication.mouseButtons() == Qt.MouseButton.NoButton:
                QTimer.singleShot(0, editor.clearFocus)
        elif event.type() == QEvent.Type.Wheel and not (editor.hasFocus() or editor.focusWidget()):
            return True
        return super().eventFilter(watched, event)


class ConfigValueDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._wheel_filter = WheelFocusFilter(self)

    def _guard_wheel(self, editor):
        editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if hasattr(editor, "lineEdit"):
            editor.lineEdit().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._wheel_filter.register(editor)
        return editor

    def createEditor(self, parent, option, index):
        kind = index.data(ConfigTableModel.KindRole)
        if kind == "bool":
            editor = SwitchButton(parent)
            editor.setOnText("")
            editor.setOffText("")
            editor.setText("")
            editor.checkedChanged.connect(lambda checked: index.model().setData(index, checked))
            return self._guard_wheel(editor)
        if kind == "options":
            editor = ComboBox(parent)
            editor.addItems(index.data(ConfigTableModel.OptionsRole) or [])
            editor.currentTextChanged.connect(lambda value: index.model().setData(index, value))
            return self._guard_wheel(editor)
        if kind == "int":
            editor = SpinBox(parent)
            editor.setRange(-1_000_000, 1_000_000)
            editor.valueChanged.connect(lambda value: index.model().setData(index, value))
            return self._guard_wheel(editor)
        if kind == "float":
            editor = DoubleSpinBox(parent)
            editor.setRange(-1_000_000, 1_000_000)
            editor.setDecimals(3)
            editor.valueChanged.connect(lambda value: index.model().setData(index, value))
            return self._guard_wheel(editor)
        if kind == "hours":
            editor = DoubleSpinBox(parent)
            editor.setRange(0, 8760)
            editor.setSingleStep(0.25)
            editor.setDecimals(2)
            editor.setSuffix(" h")
            editor.valueChanged.connect(lambda value: index.model().setData(index, value))
            return self._guard_wheel(editor)
        if kind == "times":
            editor = TimeListEditor(parent)
            editor.valueChanged.connect(lambda value: index.model().setData(index, value))
            self._guard_wheel(editor.display)
            self._guard_wheel(editor.picker)
            return editor
        if kind == "timezone":
            editor = EditableComboBox(parent)
            editor.addItems(index.data(ConfigTableModel.OptionsRole) or [])
            editor.currentTextChanged.connect(lambda value: index.model().setData(index, value))
            return self._guard_wheel(editor)
        editor = SettingsLineEdit(parent)
        editor.textChanged.connect(lambda value: index.model().setData(index, value))
        return self._guard_wheel(editor)

    def setEditorData(self, editor, index):
        kind = index.data(ConfigTableModel.KindRole)
        value = index.data(Qt.ItemDataRole.EditRole)
        if kind == "bool":
            checked = str(value).lower() == "true"
            editor.setChecked(checked)
            editor.setText("")
        elif kind == "options":
            editor.setCurrentText(str(value))
        elif kind == "int":
            editor.setValue(int(value or 0))
        elif kind == "float":
            editor.setValue(float(value or 0))
        elif kind == "hours":
            editor.setValue(float(value or 12))
        elif kind == "times":
            editor.setValue(value)
        elif kind == "timezone":
            editor.setCurrentText(str(value))
        else:
            editor.setText(str(value or ""))
            editor.setCursorPosition(0)
            editor.deselect()

    def setModelData(self, editor, model, index):
        kind = index.data(ConfigTableModel.KindRole)
        if kind == "bool":
            value = editor.isChecked()
        elif kind == "options":
            value = editor.currentText()
        elif kind in {"int", "float", "hours"}:
            value = editor.value()
        elif kind == "times":
            value = editor.value()
        elif kind == "timezone":
            value = editor.currentText()
        else:
            value = editor.text()
        model.setData(index, value)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect.adjusted(6, 3, -6, -3))


class ElidedDescriptionDelegate(TableItemDelegate):
    def helpEvent(self, event, view, option, index):
        if event.type() != QEvent.Type.ToolTip or not index.isValid():
            return super().helpEvent(event, view, option, index)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        available_width = max(0, option.rect.width() - 12)
        if option.fontMetrics.horizontalAdvance(text) <= available_width:
            QToolTip.hideText()
            event.ignore()
            return False
        QToolTip.showText(event.globalPos(), text, view, option.rect)
        return True
