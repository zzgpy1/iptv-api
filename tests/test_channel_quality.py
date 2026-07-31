import copy
import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import PropertyMock, patch

from utils.channel import (
    check_channel_need_frozen,
    get_speed_test_status,
    is_valid_speed_result,
)
from utils.channel_quality import is_channel_result_valid
from utils.channel_repository import (
    _is_valid,
    list_channel_results,
    sync_channel_snapshot,
)
from utils.config import config
from utils.identity import stable_channel_id, stable_result_id
from utils.speed import get_sort_result


def make_result(*, speed=5.0, delay=10.0, resolution="1920x1080", origin="subscribe"):
    url = "https://example.com/live.m3u8"
    return {
        "id": stable_result_id(url),
        "url": url,
        "host": "example.com",
        "origin": origin,
        "ipv_type": "ipv4",
        "speed": speed,
        "delay": delay,
        "resolution": resolution,
    }


class ChannelQualityTests(unittest.TestCase):
    def quality_config(self, *, supply=False):
        stack = ExitStack()
        values = {
            "open_supply": supply,
            "open_filter_speed": True,
            "min_speed": 1.0,
            "resolution_speed_map": {},
            "open_filter_resolution": True,
            "min_resolution_value": 1280 * 720,
            "max_resolution_value": 1920 * 1080,
        }
        for name, value in values.items():
            stack.enter_context(
                patch.object(type(config), name, new=PropertyMock(return_value=value))
            )
        stack.enter_context(patch("utils.speed.resolution_speed_map", {}))
        return stack

    def sort_results(self, *items, supply=False):
        return get_sort_result(
            [copy.deepcopy(item) for item in items],
            supply=supply,
            filter_speed=True,
            min_speed=1.0,
            filter_resolution=True,
            min_resolution=1280 * 720,
            max_resolution=1920 * 1080,
        )

    def test_maximum_resolution_is_consistent_across_pipeline_and_repository(self):
        result = make_result(resolution="3840x2160")

        with self.quality_config():
            self.assertFalse(is_valid_speed_result(result))
            self.assertFalse(_is_valid(result))
            self.assertTrue(check_channel_need_frozen(result))
            self.assertEqual(get_speed_test_status(result, False), "filtered_resolution")
            self.assertEqual(self.sort_results(result), [])

    def test_low_speed_is_not_reported_as_valid_in_repository(self):
        result = make_result(speed=0.25)

        with self.quality_config(), tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "channels.db")
            data = {"News": {"Demo": [result]}}
            sync_channel_snapshot(db_path, data, tested_data=data)
            rows = list_channel_results(
                db_path,
                stable_channel_id("News", "Demo"),
            )

            self.assertFalse(is_valid_speed_result(result))
            self.assertEqual(self.sort_results(result), [])
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]["valid"])

    def test_missing_resolution_is_allowed_when_measurement_is_reachable(self):
        result = make_result(resolution=None)

        with self.quality_config():
            self.assertTrue(is_valid_speed_result(result))
            self.assertTrue(_is_valid(result))
            self.assertEqual(self.sort_results(result), [result])

    def test_supply_mode_bypasses_thresholds_but_not_reachability(self):
        fallback = make_result(speed=0.25, resolution="3840x2160")
        unreachable = make_result(speed=0, resolution="3840x2160")

        with self.quality_config(supply=True):
            self.assertTrue(is_valid_speed_result(fallback))
            self.assertTrue(_is_valid(fallback))
            self.assertFalse(check_channel_need_frozen(fallback))
            self.assertEqual(self.sort_results(fallback, supply=True), [fallback])

            self.assertFalse(is_valid_speed_result(unreachable))
            self.assertFalse(_is_valid(unreachable))
            self.assertTrue(check_channel_need_frozen(unreachable))
            self.assertEqual(self.sort_results(unreachable, supply=True), [])

    def test_retained_origins_remain_valid_without_measurements(self):
        retained = make_result(
            speed=None,
            delay=None,
            resolution=None,
            origin="whitelist",
        )

        with self.quality_config():
            self.assertFalse(is_channel_result_valid(retained))
            self.assertTrue(is_channel_result_valid(retained, retain_special=True))
            self.assertTrue(_is_valid(retained))


if __name__ == "__main__":
    unittest.main()
