import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

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
        self.settings.setValue("appearance/channel_center_view", "category")
        self.addCleanup(self._restore_settings)

    def _restore_settings(self):
        if self.previous_view is None:
            self.settings.remove("appearance/channel_center_view")
        else:
            self.settings.setValue("appearance/channel_center_view", self.previous_view)

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
            self.assertEqual(page.smart_tree.topLevelItemCount(), 3)
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


if __name__ == "__main__":
    unittest.main()
