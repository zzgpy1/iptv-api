import re

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QTextBrowser

from utils.config import resource_path
from utils.i18n import get_language, t


def extract_release_notes(markdown: str, version: str, language: str | None = None) -> str:
    """Return one release's notes in the requested language."""
    version = str(version or "").lstrip("vV")
    if not version:
        return ""
    heading = re.escape(version)
    match = re.search(
        rf"^##\s+v?{heading}\s*$([\s\S]*?)(?=^##\s+v|\Z)",
        markdown,
        re.MULTILINE,
    )
    if not match:
        return ""

    section = match.group(0).strip()
    language = language or get_language()
    english = re.search(r"<details>\s*<summary>English</summary>([\s\S]*?)</details>", section, re.IGNORECASE)
    if language.startswith("en"):
        english_content = english.group(1).strip() if english else section
        content = f"## v{version}\n\n{english_content}" if english else english_content
    else:
        content = re.sub(r"<details>[\s\S]*?</details>", "", section, flags=re.IGNORECASE).strip()
    return content


class ChangelogDialog(QDialog):
    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.version = str(version or "")
        self.setWindowTitle(t("desktop.changelog_title").format(version=self.version))
        self.resize(760, 620)

        self.viewer = QTextBrowser(self)
        self.viewer.setOpenExternalLinks(True)
        self.viewer.setMarkdown(self._read_changelog(self.version))

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.viewer)
        layout.addWidget(self.buttons)

    @staticmethod
    def _read_changelog(version):
        path = resource_path("CHANGELOG.md")
        try:
            with open(path, "r", encoding="utf-8") as file:
                content = extract_release_notes(file.read(), version)
                return content or t("desktop.changelog_version_unavailable").format(version=version)
        except OSError:
            return t("desktop.changelog_unavailable")
