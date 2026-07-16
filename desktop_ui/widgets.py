from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, IconWidget, StrongBodyLabel, SubtitleLabel


class PageTitle(QWidget):
    def __init__(self, icon, text: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.icon_widget = IconWidget(icon, self)
        self.icon_widget.setFixedSize(26, 26)
        self.label = SubtitleLabel(text, self)
        layout.addWidget(self.icon_widget)
        layout.addWidget(self.label)
        layout.addStretch(1)

    def setText(self, text: str):
        self.label.setText(text)


class MetricCard(CardWidget):
    def __init__(self, title: str, value: str = "--", detail: str = "", icon=None, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(104)
        self.setBorderRadius(8)
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(14)
        self.icon_widget = IconWidget(icon, self) if icon else None
        if self.icon_widget:
            self.icon_widget.setFixedSize(30, 30)
            root.addWidget(self.icon_widget, 0, Qt.AlignmentFlag.AlignTop)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
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
        root.addLayout(layout, 1)

    def set_clickable(self, clickable: bool = True):
        self.setClickEnabled(clickable)
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)

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
