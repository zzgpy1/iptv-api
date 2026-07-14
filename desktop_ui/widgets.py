from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, StrongBodyLabel


class MetricCard(CardWidget):
    def __init__(self, title: str, value: str = "--", detail: str = "", parent=None):
        super().__init__(parent)
        self.setMinimumHeight(104)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)
        self.title_label = BodyLabel(title, self)
        self.value_label = StrongBodyLabel(value, self)
        font = self.value_label.font()
        font.setPointSize(20)
        font.setBold(True)
        self.value_label.setFont(font)
        self.detail_label = BodyLabel(detail, self)
        self.detail_label.setStyleSheet("color: #64748b")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_value(self, value, detail: str | None = None):
        self.value_label.setText(str(value))
        if detail is not None:
            self.detail_label.setText(detail)


def metric_row(cards: list[MetricCard]) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    for card in cards:
        layout.addWidget(card, 1)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    return widget
