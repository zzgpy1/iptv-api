import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget
from qfluentwidgets import FluentIcon, NavigationPushButton

from desktop_ui.pages.about import AboutPage
from desktop_ui.main_window import MainWindow
from desktop_ui.widgets import NavigationStatusIndicator


class NavigationStatusIndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_indicator_fits_expanded_and_compact_navigation_items(self):
        item = NavigationPushButton(FluentIcon.HOME, "Overview", True)
        indicator = NavigationStatusIndicator(item)
        indicator.move(24, 3)
        indicator.set_status(FluentIcon.PAUSE, "#D97706")

        item.setCompacted(False)
        self.assertFalse(indicator.isHidden())
        self.assertLess(indicator.geometry().right(), item.width())

        item.setCompacted(True)
        self.assertLess(indicator.geometry().right(), item.width())

    def test_about_page_emits_available_version_status(self):
        page = AboutPage()
        statuses = []
        page.status_changed.connect(lambda state, payload: statuses.append((state, payload)))

        page._checked({
            "newer": True,
            "latest": "9.9.9",
            "current": "1.0.0",
            "release_url": "https://example.com/release",
            "asset_url": "",
            "asset_name": "",
        })

        self.assertEqual(statuses[-1], ("available", {"version": "9.9.9"}))

    def test_about_page_silently_ignores_automatic_check_failure(self):
        page = AboutPage()
        statuses = []
        page.status_changed.connect(lambda state, payload: statuses.append((state, payload)))
        initial_state = page._update_state
        page._automatic_check = True

        page._check_failed("offline")

        self.assertEqual(page._update_state, initial_state)
        self.assertEqual(statuses, [])
        self.assertTrue(page.auto_check_timer.isActive())
        self.assertEqual(page.auto_check_timer.interval(), page.AUTO_CHECK_INTERVAL_MS)

    def test_active_status_is_hidden_on_its_page_and_shown_elsewhere(self):
        host = self._status_host()
        MainWindow._set_navigation_status(
            host, "dashboard", FluentIcon.SYNC, "#2563EB", "desktop.nav_update_running",
        )

        self.assertIn("dashboard", host._navigation_statuses)
        self.assertTrue(host._navigation_indicators["dashboard"].isHidden())

        host.stackedWidget.setCurrentWidget(host.other_page)
        MainWindow._navigation_page_changed(host, 1)
        self.assertFalse(host._navigation_indicators["dashboard"].isHidden())

    def test_terminal_status_is_not_shown_when_page_is_already_open(self):
        host = self._status_host()
        MainWindow._set_navigation_status(
            host,
            "dashboard",
            FluentIcon.COMPLETED,
            "#059669",
            "desktop.nav_update_completed",
            dismiss_on_visit=True,
        )

        self.assertNotIn("dashboard", host._navigation_statuses)
        self.assertTrue(host._navigation_indicators["dashboard"].isHidden())

    @staticmethod
    def _status_host():
        dashboard_page = QWidget()
        other_page = QWidget()
        stack = QStackedWidget()
        stack.addWidget(dashboard_page)
        stack.addWidget(other_page)
        stack.setCurrentWidget(dashboard_page)
        item = NavigationPushButton(FluentIcon.HOME, "Overview", True)
        indicator = NavigationStatusIndicator(item)

        class Host:
            _set_navigation_status = MainWindow._set_navigation_status
            _clear_navigation_status = MainWindow._clear_navigation_status
            _refresh_navigation_status = MainWindow._refresh_navigation_status
            _refresh_navigation_statuses = MainWindow._refresh_navigation_statuses

        host = Host()
        host.stackedWidget = stack
        host.other_page = other_page
        host._navigation_items = {
            "dashboard": (item, "desktop.dashboard", dashboard_page),
        }
        host._navigation_statuses = {}
        host._navigation_indicators = {"dashboard": indicator}
        return host
