import os
import tempfile

import utils.constants as constants
from utils.config import resource_path


def _append_unique(path: str, value: str) -> bool:
    target = resource_path(path, persistent=True)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    lines = []
    if os.path.exists(target):
        with open(target, "r", encoding="utf-8") as file:
            lines = file.read().splitlines()
    normalized = value.strip()
    if normalized in {line.strip() for line in lines}:
        return False
    lines.append(normalized)
    with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False,
            dir=os.path.dirname(target) or ".", prefix=os.path.basename(target) + ".tmp."
    ) as file:
        file.write("\n".join(lines).rstrip() + "\n")
        temporary = file.name
    os.replace(temporary, target)
    return True


def add_to_whitelist(channel_name: str, url: str) -> bool:
    return _append_unique(constants.whitelist_path, f"{channel_name},{url}")


def add_to_blacklist(url: str) -> bool:
    return _append_unique(constants.blacklist_path, url)
