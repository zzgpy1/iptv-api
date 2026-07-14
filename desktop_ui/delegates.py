from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QStyledItemDelegate, QToolTip
from qfluentwidgets import ComboBox, DoubleSpinBox, LineEdit, SpinBox, SwitchButton

from desktop_ui.models import ConfigTableModel


class ConfigValueDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        kind = index.data(ConfigTableModel.KindRole)
        if kind == "bool":
            editor = SwitchButton(parent)
            editor.setOnText("")
            editor.setOffText("")
            editor.setText("")
            editor.checkedChanged.connect(lambda checked: index.model().setData(index, checked))
            return editor
        if kind == "options":
            editor = ComboBox(parent)
            editor.addItems(index.data(ConfigTableModel.OptionsRole) or [])
            editor.currentTextChanged.connect(lambda value: index.model().setData(index, value))
            return editor
        if kind == "int":
            editor = SpinBox(parent)
            editor.setRange(-1_000_000, 1_000_000)
            editor.valueChanged.connect(lambda value: index.model().setData(index, value))
            return editor
        if kind == "float":
            editor = DoubleSpinBox(parent)
            editor.setRange(-1_000_000, 1_000_000)
            editor.setDecimals(3)
            editor.valueChanged.connect(lambda value: index.model().setData(index, value))
            return editor
        editor = LineEdit(parent)
        editor.textChanged.connect(lambda value: index.model().setData(index, value))
        return editor

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
        else:
            editor.setText(str(value or ""))

    def setModelData(self, editor, model, index):
        kind = index.data(ConfigTableModel.KindRole)
        if kind == "bool":
            value = editor.isChecked()
        elif kind == "options":
            value = editor.currentText()
        elif kind in {"int", "float"}:
            value = editor.value()
        else:
            value = editor.text()
        model.setData(index, value)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect.adjusted(6, 3, -6, -3))


class ElidedDescriptionDelegate(QStyledItemDelegate):
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
