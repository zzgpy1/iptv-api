import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QItemSelectionModel, QPointF, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from desktop_ui.pages.channels import ChannelCenterPage
import utils.constants as constants
from utils.channel_repository import ensure_channel_repository, list_categories, list_channels


class ChannelRepositoryFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = os.path.join(self.temp_dir.name, "channels.db")
        ensure_channel_repository(self.db_path)
        connection = sqlite3.connect(self.db_path)
        connection.executemany(
            """
            INSERT INTO channels(
                channel_key, category, name, health, total_results,
                valid_results, selected_results, updated_at
            ) VALUES (?, ?, ?, ?, 0, 0, 0, 1)
            """,
            [
                ("news-world", "News", "World News", "healthy"),
                ("news-local", "News", "Local News", "warning"),
                ("sports-one", "Sports", "Sports One", "offline"),
                ("sports-two", "Sports", "Sports Two", "unknown"),
            ],
        )
        connection.commit()
        connection.close()

    def test_category_counts_can_be_scoped_by_search(self):
        categories = list_categories(self.db_path, search="World")

        self.assertEqual(categories, [{
            "category": "News",
            "channel_count": 1,
            "healthy_count": 1,
            "warning_count": 0,
            "offline_count": 0,
            "valid_results": 0,
        }])

    def test_channels_can_be_filtered_by_category_search_and_health(self):
        rows = list_channels(
            self.db_path,
            category="Sports",
            search="Two",
            health="unknown",
        )

        self.assertEqual([row["channel_key"] for row in rows], ["sports-two"])


class ChannelCenterViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = os.path.join(self.temp_dir.name, "channels.db")
        self.whitelist_path = os.path.join(self.temp_dir.name, "whitelist.txt")
        self.blacklist_path = os.path.join(self.temp_dir.name, "blacklist.txt")
        self.template_path = os.path.join(self.temp_dir.name, "demo.txt")
        with open(self.template_path, "w", encoding="utf-8") as file:
            file.write("Sports,#genre#\nSports One\n\nNews,#genre#\nWorld News\n")
        ensure_channel_repository(self.db_path)
        connection = sqlite3.connect(self.db_path)
        connection.executemany(
            """
            INSERT INTO channels(
                channel_key, category, name, health, total_results,
                valid_results, selected_results, updated_at
            ) VALUES (?, ?, ?, ?, 0, 0, 0, 1)
            """,
            [
                ("news-world", "News", "World News", "warning"),
                ("sports-one", "Sports", "Sports One", "offline"),
            ],
        )
        connection.commit()
        connection.close()
        self.settings = QSettings()
        self.previous_view = self.settings.value("appearance/channel_center_view")
        self.previous_drawer_height = self.settings.value(
            "appearance/channel_result_drawer_height"
        )
        self.settings.setValue("appearance/channel_center_view", "category")
        self.settings.setValue("appearance/channel_result_drawer_height", 360)
        self.addCleanup(self._restore_settings)

    def _restore_settings(self):
        if self.previous_view is None:
            self.settings.remove("appearance/channel_center_view")
        else:
            self.settings.setValue("appearance/channel_center_view", self.previous_view)
        if self.previous_drawer_height is None:
            self.settings.remove("appearance/channel_result_drawer_height")
        else:
            self.settings.setValue(
                "appearance/channel_result_drawer_height",
                self.previous_drawer_height,
            )

    def test_category_view_filters_rows_and_list_view_restores_category_column(self):
        with (
            patch.object(constants, "channel_results_path", self.db_path),
            patch.object(constants, "whitelist_path", self.whitelist_path),
            patch.object(constants, "blacklist_path", self.blacklist_path),
            patch("desktop_ui.pages.channels.resource_path", return_value=self.template_path),
        ):
            page = ChannelCenterPage()
            self.addCleanup(page.deleteLater)

            self.assertEqual(list(page.view_switch.items), ["category", "list"])
            self.assertEqual(page.view_switch.currentRouteKey(), "category")
            self.assertFalse(page.category_sidebar.isHidden())
            self.assertTrue(page.channel_table.isColumnHidden(8))
            self.assertEqual(page.category_tree.topLevelItemCount(), 3)
            self.assertEqual(page.smart_tree.topLevelItemCount(), 4)
            self.assertEqual(
                [
                    page.category_tree.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole)
                    for index in range(1, page.category_tree.topLevelItemCount())
                ],
                [("category", "Sports"), ("category", "News")],
            )
            self.assertEqual(
                [row["category"] for row in page.channel_model.rows],
                ["Sports", "News"],
            )
            self.assertEqual(
                [
                    page.category_selector.itemData(index)
                    for index in range(1, page.category_selector.count())
                ],
                ["Sports", "News"],
            )

            page._category_item_clicked(page._category_items[("category", "News")], 0)
            self.assertEqual([row["name"] for row in page.channel_model.rows], ["World News"])

            page.channel_model.setData(
                page.channel_model.index(0, 0),
                Qt.CheckState.Checked,
                Qt.ItemDataRole.CheckStateRole,
            )
            page._category_item_clicked(page._category_items[("category", "Sports")], 0)
            self.assertEqual(page._checked_channel_keys, {"news-world"})

            page._set_view_mode("list")
            self.assertTrue(page.category_sidebar.isHidden())
            self.assertFalse(page.channel_table.isColumnHidden(8))

    def test_smart_collections_include_healthy_channels(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            """
            INSERT INTO channels(
                channel_key, category, name, health, total_results,
                valid_results, selected_results, updated_at
            ) VALUES ('news-healthy', 'News', 'Healthy News', 'healthy', 0, 0, 0, 1)
            """
        )
        connection.commit()
        connection.close()
        with (
            patch.object(constants, "channel_results_path", self.db_path),
            patch.object(constants, "whitelist_path", self.whitelist_path),
            patch.object(constants, "blacklist_path", self.blacklist_path),
            patch("desktop_ui.pages.channels.resource_path", return_value=self.template_path),
        ):
            page = ChannelCenterPage()
            self.addCleanup(page.deleteLater)

            self.assertEqual(
                [
                    page.smart_tree.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole)
                    for index in range(page.smart_tree.topLevelItemCount())
                ],
                [
                    ("health", "healthy"),
                    ("health", "warning"),
                    ("health", "offline"),
                    ("health", "unknown"),
                ],
            )
            page._smart_item_clicked(page._smart_items[("health", "healthy")], 0)
            self.assertEqual([row["name"] for row in page.channel_model.rows], ["Healthy News"])

    def test_view_mode_is_restored_and_updated(self):
        self.settings.setValue("appearance/channel_center_view", "list")
        with (
            patch.object(constants, "channel_results_path", self.db_path),
            patch.object(constants, "whitelist_path", self.whitelist_path),
            patch.object(constants, "blacklist_path", self.blacklist_path),
            patch("desktop_ui.pages.channels.resource_path", return_value=self.template_path),
        ):
            page = ChannelCenterPage()
            self.addCleanup(page.deleteLater)

            self.assertEqual(page.view_switch.currentRouteKey(), "list")
            self.assertTrue(page.category_sidebar.isHidden())

            page._set_view_mode("category")

            self.assertEqual(
                self.settings.value("appearance/channel_center_view"),
                "category",
            )

    def test_result_drawer_stays_open_for_buttons_menus_and_dialogs(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            """
            INSERT INTO channel_results(
                channel_key, result_key, url, speed, delay, valid,
                selected_rank, last_seen_at
            ) VALUES (
                'sports-one', 'result-one', 'https://example.invalid/one',
                1, 20, 1, 1, 1
            )
            """
        )
        connection.commit()
        connection.close()
        with (
            patch.object(constants, "channel_results_path", self.db_path),
            patch.object(constants, "whitelist_path", self.whitelist_path),
            patch.object(constants, "blacklist_path", self.blacklist_path),
            patch("desktop_ui.pages.channels.resource_path", return_value=self.template_path),
        ):
            page = ChannelCenterPage()
            self.addCleanup(page.deleteLater)
            dialog = QDialog(page)
            dialog_button = QPushButton(dialog)
            self.addCleanup(dialog.deleteLater)
            mouse_press = QEvent(QEvent.Type.MouseButtonPress)

            page.show()
            page._drawer_channel_key = "sports-one"
            page._load_results("sports-one")
            page.result_drawer.show()
            page.result_drawer.setGeometry(page._drawer_geometry())
            self.app.processEvents()
            for watched in (
                page.more_button,
                page.result_table.viewport(),
                page.result_menu,
                dialog_button,
            ):
                with self.subTest(widget=type(watched).__name__), patch.object(
                    page,
                    "hide_result_drawer",
                ) as hide:
                    page.eventFilter(watched, mouse_press)
                    hide.assert_not_called()

            with patch.object(page, "hide_result_drawer") as hide:
                page.eventFilter(page.search, mouse_press)
                hide.assert_called_once_with()

            result_index = page.result_model.index(0, 1)
            result_position = page.result_table.visualRect(result_index).center()
            with patch.object(page, "hide_result_drawer") as hide:
                QTest.mouseClick(
                    page.result_table.viewport(),
                    Qt.MouseButton.RightButton,
                    pos=result_position,
                )
                self.app.processEvents()
                hide.assert_not_called()

            with patch.object(page.result_menu, "exec") as execute_menu:
                page._show_result_menu(result_position)
                execute_menu.assert_called_once()

            drawer_center = page.result_drawer.rect().center()
            drawer_global = page.result_drawer.mapToGlobal(drawer_center)
            attributed_elsewhere = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(0, 0),
                QPointF(drawer_global),
                Qt.MouseButton.RightButton,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
            )
            with patch.object(page, "hide_result_drawer") as hide:
                page.eventFilter(page.search, attributed_elsewhere)
                hide.assert_not_called()

    def test_result_drawer_margins_resize_and_fullscreen(self):
        with (
            patch.object(constants, "channel_results_path", self.db_path),
            patch.object(constants, "whitelist_path", self.whitelist_path),
            patch.object(constants, "blacklist_path", self.blacklist_path),
            patch("desktop_ui.pages.channels.resource_path", return_value=self.template_path),
        ):
            page = ChannelCenterPage()
            self.addCleanup(page.deleteLater)
            page.resize(1000, 700)

            geometry = page._drawer_geometry()
            self.assertEqual(geometry.left(), 12)
            self.assertEqual(page.width() - geometry.right() - 1, 12)
            self.assertEqual(page.height() - geometry.bottom() - 1, 8)

            page.result_drawer.setGeometry(geometry)
            page._resize_result_drawer(80)
            self.assertEqual(page._drawer_geometry().height(), 440)
            page._save_result_drawer_height()
            self.assertEqual(
                self.settings.value(
                    "appearance/channel_result_drawer_height",
                    type=int,
                ),
                440,
            )

            page._toggle_result_drawer_fullscreen()
            self.assertTrue(page._drawer_fullscreen)
            self.assertEqual(page.result_drawer.geometry(), page.rect())
            self.assertEqual(page.result_drawer.getBorderRadius(), 0)

            page._toggle_result_drawer_fullscreen()
            self.assertFalse(page._drawer_fullscreen)
            self.assertEqual(page.result_drawer.getBorderRadius(), 12)

    def test_screenshot_preview_auto_capture_only_when_missing(self):
        with (
            patch.object(constants, "channel_results_path", self.db_path),
            patch.object(constants, "whitelist_path", self.whitelist_path),
            patch.object(constants, "blacklist_path", self.blacklist_path),
            patch("desktop_ui.pages.channels.resource_path", return_value=self.template_path),
        ):
            page = ChannelCenterPage()
            self.addCleanup(page.deleteLater)
            dialog = Mock()

            dialog.has_screenshot.return_value = True
            page._auto_capture_missing_screenshot(
                dialog,
                {"screenshot_status": "success"},
            )
            dialog.request_capture.assert_not_called()

            page._auto_capture_missing_screenshot(
                dialog,
                {"screenshot_status": "failed"},
            )
            dialog.request_capture.assert_not_called()

            page._auto_capture_missing_screenshot(
                dialog,
                {"screenshot_status": "not_captured"},
            )
            dialog.request_capture.assert_called_once_with()

            dialog.request_capture.reset_mock()
            dialog.has_screenshot.return_value = False
            page._auto_capture_missing_screenshot(
                dialog,
                {"screenshot_status": "success"},
            )
            dialog.request_capture.assert_called_once_with()

    def test_result_actions_follow_single_and_multiple_selection(self):
        connection = sqlite3.connect(self.db_path)
        connection.executemany(
            """
            INSERT INTO channel_results(
                channel_key, result_key, url, speed, delay, valid,
                selected_rank, last_seen_at
            ) VALUES (?, ?, ?, 1, 20, 1, ?, 1)
            """,
            [
                ("sports-one", "result-one", "https://example.invalid/one", 1),
                ("sports-one", "result-two", "https://example.invalid/two", None),
                ("news-world", "news-result", "https://example.invalid/news", 1),
            ],
        )
        connection.commit()
        connection.close()
        with (
            patch.object(constants, "channel_results_path", self.db_path),
            patch.object(constants, "whitelist_path", self.whitelist_path),
            patch.object(constants, "blacklist_path", self.blacklist_path),
            patch("desktop_ui.pages.channels.resource_path", return_value=self.template_path),
        ):
            page = ChannelCenterPage()
            self.addCleanup(page.deleteLater)
            page._drawer_channel_key = "sports-one"
            page._load_results("sports-one")

            self.assertEqual(
                [row["result_key"] for row in page.selected_results()],
                ["result-one"],
            )
            self.assertFalse(page.result_model.rows[0]["batch_selected"])
            self.assertTrue(page.play_button.isEnabled())
            self.assertTrue(page.retest_result_button.isEnabled())
            self.assertTrue(page.screenshot_button.isEnabled())
            self.assertTrue(page.stream_button.isEnabled())
            self.assertTrue(page.more_button.isEnabled())

            automatic_captures = []
            page.capture_screenshot_requested.connect(
                lambda row: automatic_captures.append(row["result_key"])
            )
            page._preview_result_screenshot()
            self.app.processEvents()
            dialog = page._screenshot_dialog
            self.assertIsNotNone(dialog)
            self.assertTrue(dialog.is_loading)
            self.assertEqual(automatic_captures, ["result-one"])
            with patch("desktop_ui.pages.channels.InfoBar.success") as success:
                page.show_result_screenshot("result-one", notify=True)
                self.assertIs(success.call_args.kwargs["parent"], dialog)
            dialog.reject()
            self.app.processEvents()

            captured = []
            page.capture_screenshot_requested.connect(
                lambda row: captured.append(row["result_key"])
            )
            page._request_result_screenshot()
            self.assertEqual(captured, ["result-one"])

            selection = page.result_table.selectionModel()
            selection.select(
                page.result_model.index(1, 0),
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )
            self.app.processEvents()
            self.assertFalse(page.play_button.isEnabled())
            self.assertTrue(page.retest_result_button.isEnabled())
            self.assertFalse(page.screenshot_button.isEnabled())
            self.assertFalse(page.stream_button.isEnabled())
            self.assertTrue(page.capture_screenshot_action.isEnabled())

            captured_batches = []
            page.capture_screenshots_requested.connect(
                lambda rows: captured_batches.append(
                    [row["result_key"] for row in rows]
                )
            )
            page._request_result_screenshot()
            self.assertEqual(
                set(captured_batches[-1]),
                {"result-one", "result-two"},
            )

            selection.clearSelection()
            for row in range(2):
                page.result_model.setData(
                    page.result_model.index(row, 0),
                    Qt.CheckState.Checked,
                    Qt.ItemDataRole.CheckStateRole,
                )
            self.app.processEvents()
            self.assertFalse(page.screenshot_button.isEnabled())
            self.assertTrue(page.capture_screenshot_action.isEnabled())
            page._request_result_screenshot()
            self.assertEqual(
                set(captured_batches[-1]),
                {"result-one", "result-two"},
            )

            news_index = next(
                page.channel_model.index(index, 1)
                for index, row in enumerate(page.channel_model.rows)
                if row["channel_key"] == "news-world"
            )
            page._current_channel_changed(news_index, news_index)
            self.app.processEvents()
            self.assertEqual(page._drawer_channel_key, "news-world")
            self.assertEqual(page._checked_result_keys, set())
            self.assertEqual(
                [row["result_key"] for row in page.selected_results()],
                ["news-result"],
            )
            self.assertFalse(page.result_model.rows[0]["batch_selected"])
            self.assertTrue(page.play_button.isEnabled())
            self.assertTrue(page.screenshot_button.isEnabled())
            self.assertTrue(page.more_button.isEnabled())

            page._drawer_channel_key = "missing-channel"
            page._load_results("missing-channel")
            self.app.processEvents()
            self.assertEqual(page.selected_results(), [])
            self.assertFalse(page.play_button.isEnabled())
            self.assertFalse(page.screenshot_button.isEnabled())
            self.assertFalse(page.more_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
