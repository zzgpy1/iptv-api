import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from desktop_ui.widgets import paint_table_checkbox


class TableCheckBoxPaintingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _render(state):
        image = QImage(24, 24, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        paint_table_checkbox(painter, QRect(0, 0, 24, 24), state)
        painter.end()
        return bytes(image.constBits())

    def test_integer_and_enum_checked_states_render_identically(self):
        self.assertEqual(
            self._render(Qt.CheckState.Checked.value),
            self._render(Qt.CheckState.Checked),
        )


if __name__ == "__main__":
    unittest.main()
