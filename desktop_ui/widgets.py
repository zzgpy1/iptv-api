from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, IconWidget, PrimaryPushButton, PushButton, StrongBodyLabel, SubtitleLabel, isDarkTheme, qconfig


class AccentPushButton(PrimaryPushButton):
    def _postInit(self):
        super()._postInit()
        qconfig.themeChangedFinished.connect(self._apply_semantic_style)
        self._apply_semantic_style()

    def _apply_semantic_style(self, *_):
        self.setStyleSheet(
            "QPushButton { color: #FFFFFF; background-color: #2563EB; border: none; border-radius: 6px; padding: 6px 13px; }"
            "QPushButton[hasIcon=true] { padding-left: 31px; }"
            "QPushButton:hover { background-color: #1D4ED8; }"
            "QPushButton:pressed { background-color: #1E40AF; }"
            "QPushButton:disabled { color: #CBD5E1; background-color: #64748B; }"
        )

    def setIcon(self, icon):
        super().setIcon(icon.icon(color=QColor("#FFFFFF")) if hasattr(icon, "icon") else icon)


class DangerPushButton(PushButton):
    def _postInit(self):
        super()._postInit()
        qconfig.themeChangedFinished.connect(self._apply_semantic_style)
        self._apply_semantic_style()

    def _apply_semantic_style(self, *_):
        color = "#F87171" if isDarkTheme() else "#DC2626"
        border = "#EF4444" if isDarkTheme() else "#FCA5A5"
        hover = "rgba(248, 113, 113, 28)" if isDarkTheme() else "rgba(220, 38, 38, 18)"
        pressed = "rgba(248, 113, 113, 48)" if isDarkTheme() else "rgba(220, 38, 38, 34)"
        self.setStyleSheet(
            f"QPushButton {{ color: {color}; background-color: transparent; border: 1px solid {border}; border-radius: 6px; padding: 5px 12px; }}"
            "QPushButton[hasIcon=true] { padding-left: 31px; }"
            f"QPushButton:hover {{ background-color: {hover}; }}"
            f"QPushButton:pressed {{ background-color: {pressed}; }}"
            "QPushButton:disabled { color: #94A3B8; border-color: #64748B; background-color: transparent; }"
        )
        if hasattr(self, "_semantic_icon"):
            icon = self._semantic_icon
            PushButton.setIcon(self, icon.icon(color=QColor(color)) if hasattr(icon, "icon") else icon)

    def setIcon(self, icon):
        self._semantic_icon = icon
        color = QColor("#F87171" if isDarkTheme() else "#DC2626")
        super().setIcon(icon.icon(color=color) if hasattr(icon, "icon") else icon)


def play_circle_icon(color="#FFFFFF"):
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 2.1))
    painter.drawEllipse(3.5, 3.5, 25, 25)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPolygon(QPolygonF([QPointF(13, 10), QPointF(13, 22), QPointF(23, 16)]))
    painter.end()
    return QIcon(pixmap)


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
        self.layout = layout

    def setText(self, text: str):
        self.label.setText(text)

    def addWidget(self, widget):
        self.layout.addWidget(widget)


class MetricCard(CardWidget):
    def __init__(self, title: str, value: str = "--", detail: str = "", icon=None, parent=None, accent="#0E5CAD"):
        super().__init__(parent)
        self.setMinimumHeight(104)
        self.setBorderRadius(8)
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(14)
        self.icon_container = QWidget(self) if icon else None
        self.icon_widget = IconWidget(icon.icon(color=QColor(accent)) if hasattr(icon, "icon") else icon, self.icon_container) if icon else None
        if self.icon_widget:
            self.icon_container.setFixedSize(42, 42)
            color = QColor(accent)
            self.icon_container.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, 38); border-radius: 10px;"
            )
            icon_layout = QHBoxLayout(self.icon_container)
            icon_layout.setContentsMargins(9, 9, 9, 9)
            self.icon_widget.setFixedSize(24, 24)
            icon_layout.addWidget(self.icon_widget)
            root.addWidget(self.icon_container, 0, Qt.AlignmentFlag.AlignTop)
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
        self.detail_label.setStyleSheet(f"color: {'#94A3B8' if isDarkTheme() else '#64748B'}")
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
