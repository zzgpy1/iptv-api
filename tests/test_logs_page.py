import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import utils.constants as constants
from desktop_ui.pages.logs import LogsPage
from desktop_ui.pages.sources import SourcesPage


class LogsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.runtime_log = os.path.join(self.temp_dir.name, "runtime.log")
        with patch.object(constants, "log_path", self.runtime_log):
            self.page = LogsPage()
        self.page.timer.stop()
        self.page.resize(640, 240)
        self.page.show()
        self.app.processEvents()
        self.addCleanup(self.page.deleteLater)

    def _write_runtime_log(self, lines):
        with open(self.runtime_log, "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")

    def test_refresh_preserves_manual_position_when_auto_scroll_is_disabled(self):
        self._write_runtime_log([f"line {index}" for index in range(100)])
        self.page.refresh()
        scrollbar = self.page.viewer.verticalScrollBar()
        scrollbar.setValue(20)
        self.page.autoscroll.setChecked(False)

        self._write_runtime_log([f"line {index}" for index in range(101)])
        self.page.refresh()

        self.assertEqual(scrollbar.value(), 20)

    def test_auto_scroll_does_not_interrupt_manual_browsing(self):
        self._write_runtime_log([f"line {index}" for index in range(100)])
        self.page.refresh()
        scrollbar = self.page.viewer.verticalScrollBar()
        scrollbar.setValue(20)

        self._write_runtime_log([f"line {index}" for index in range(101)])
        self.page.refresh()

        self.assertEqual(scrollbar.value(), 20)

    def test_source_actions_share_the_tab_row(self):
        with patch.object(SourcesPage, "load"):
            page = SourcesPage()
        self.addCleanup(page.deleteLater)
        page.resize(1000, 720)
        page.show()
        self.app.processEvents()

        actions = page.tabs.cornerWidget()
        self.assertIsNotNone(actions)
        self.assertIs(actions.parent(), page.tabs)
        self.assertEqual(actions.layout().count(), 2)
        self.assertIs(actions.layout().itemAt(0).widget(), page.reload_button)
        self.assertIs(actions.layout().itemAt(1).widget(), page.save_button)
        self.assertLessEqual(actions.y(), page.tabs.tabBar().height())
        self.assertGreaterEqual(actions.x(), page.tabs.tabBar().width())
