import configparser
import io
import os
import time
import zipfile

import utils.constants as constants
from utils.config import config, resource_path


def export_diagnostics() -> str:
    target_dir = os.path.join(constants.output_dir, "diagnostics")
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, time.strftime("iptv-api-diagnostics-%Y%m%d-%H%M%S.zip"))
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, name in [
            (resource_path("version.json"), "version.json"),
            (resource_path("config/config.ini"), "config/default_config.ini"),
            (constants.log_path, "logs/runtime.log"),
            (constants.result_log_path, "logs/result.log"),
            (constants.speed_test_log_path, "logs/speed_test.log"),
            (constants.statistic_log_path, "logs/statistic.log"),
            (constants.unmatch_log_path, "logs/unmatch.log"),
        ]:
            if os.path.exists(source):
                archive.write(source, name)
        redacted = configparser.ConfigParser()
        for section in config.config.sections():
            redacted.add_section(section)
            for key, value in config.config.items(section):
                sensitive = any(part in key.lower() for part in ("password", "secret", "token", "proxy", "header"))
                redacted.set(section, key, "***" if sensitive and value else value)
        buffer = io.StringIO()
        redacted.write(buffer)
        archive.writestr("config/effective_redacted.ini", buffer.getvalue())
    return os.path.abspath(path)
