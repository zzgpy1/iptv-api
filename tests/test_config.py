import configparser
import os
import tempfile
import unittest

from utils.config import CONFIG_SCHEMA, ConfigManager, ConfigValidationError


class ConfigValidationTests(unittest.TestCase):
    def _write(self, path, content):
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)

    def _manager(self, default_content, user_content=None, environ=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        default_path = os.path.join(temp_dir.name, "config.ini")
        user_path = os.path.join(temp_dir.name, "user_config.ini")
        self._write(default_path, default_content)
        if user_content is not None:
            self._write(user_path, user_content)
        manager = ConfigManager(
            default_config_path=default_path,
            user_config_path=user_path,
            environ={} if environ is None else environ,
        )
        return manager, default_path, user_path

    def test_shipped_default_config_is_covered_by_schema(self):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read("config/config.ini", encoding="utf-8")

        unknown = set(parser["Settings"]) - set(CONFIG_SCHEMA)

        self.assertEqual(unknown, set())
        ConfigManager(
            default_config_path="config/config.ini",
            user_config_path=os.path.join(
                tempfile.gettempdir(),
                "iptv-api-missing-user-config.ini",
            ),
            environ={},
        )

    def test_invalid_values_and_unknown_key_are_reported_together(self):
        default = """\
[Settings]
open_update = True
app_port = 5180
update_mode = interval
"""
        user = """\
[Settings]
open_update = Ture
app_port = 70000
update_mode = timer
open_udpate = False
"""
        with self.assertRaises(ConfigValidationError) as raised:
            self._manager(default, user)

        message = str(raised.exception)
        self.assertEqual(len(raised.exception.issues), 4)
        self.assertIn("open_update = 'Ture'", message)
        self.assertIn('是否想填写 "True"', message)
        self.assertIn("app_port = '70000'", message)
        self.assertIn("不能大于 65535", message)
        self.assertIn("update_mode = 'timer'", message)
        self.assertIn("open_udpate", message)
        self.assertIn('是否想填写 "open_update"', message)
        self.assertIn("user_config.ini", message)

    def test_environment_override_is_validated_and_identified(self):
        default = """\
[Settings]
open_update = True
"""
        with self.assertRaises(ConfigValidationError) as raised:
            self._manager(default, environ={"OPEN_UPDATE": "Ture"})

        message = str(raised.exception)
        self.assertIn("环境变量 OPEN_UPDATE", message)
        self.assertIn("open_update = 'Ture'", message)

    def test_public_port_environment_variable_is_validated(self):
        default = """\
[Settings]
app_port = 5180
"""
        with self.assertRaises(ConfigValidationError) as raised:
            self._manager(default, environ={"PUBLIC_PORT": "outside"})

        message = str(raised.exception)
        self.assertIn("环境变量 PUBLIC_PORT", message)
        self.assertIn("应为 1～65535 的整数", message)

    def test_special_formats_and_cross_field_constraints_are_validated(self):
        default = """\
[Settings]
update_times = 25:00
time_zone = Mars/Olympus
min_resolution = 3840x2160
max_resolution = 1280x720
resolution_speed_map = 1920x1080:fast
sort_by = speed,quality
"""
        with self.assertRaises(ConfigValidationError) as raised:
            self._manager(default)

        message = str(raised.exception)
        self.assertIn("应为 HH:MM", message)
        self.assertIn("不是有效的 IANA 时区", message)
        self.assertIn("不能小于 min_resolution", message)
        self.assertIn("速率应为不小于 0 的数字", message)
        self.assertIn('"quality" 无效', message)

    def test_save_validates_before_overwriting_user_config(self):
        manager, _, user_path = self._manager(
            """\
[Settings]
open_update = True
""",
            """\
[Settings]
open_update = True
""",
        )
        manager.set("Settings", "open_update", "Ture")

        with self.assertRaises(ConfigValidationError):
            manager.save()

        with open(user_path, encoding="utf-8") as file:
            self.assertIn("open_update = True", file.read())


if __name__ == "__main__":
    unittest.main()
