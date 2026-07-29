import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from desktop_ui.pages.settings import SettingsPage
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


class SettingsEditorLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_persistent_editors_relayout_when_hidden_page_is_shown(self):
        page = SettingsPage()
        self.addCleanup(page.close)
        self.app.processEvents()

        index = next(
            page.model.index(row, 1)
            for row in range(page.model.rowCount())
            if page.model.flags(page.model.index(row, 1)) & Qt.ItemFlag.ItemIsEditable
        )
        editor = page.table.indexWidget(index)
        self.assertIsNotNone(editor)

        page.resize(900, 600)
        page.show()
        for _ in range(3):
            self.app.processEvents()

        cell = page.table.visualRect(index)
        self.assertEqual(editor.geometry().left(), cell.left() + 6)
        self.assertEqual(editor.geometry().right(), cell.right() - 6)
        self.assertGreaterEqual(editor.geometry().top(), cell.top())
        self.assertLessEqual(editor.geometry().bottom(), cell.bottom())


if __name__ == "__main__":
    unittest.main()
