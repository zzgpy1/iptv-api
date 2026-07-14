import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, FluentIcon, HyperlinkButton, InfoBar, InfoBarPosition, PrimaryPushButton, ProgressBar, PushButton, StrongBodyLabel, SubtitleLabel

from desktop_ui.update_manager import REPOSITORY_URL, UpdateManager
from utils.config import resource_path
from utils.i18n import t
from utils.tools import get_version_info


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aboutPage")
        info = get_version_info()
        self.release_url = REPOSITORY_URL + "/releases/latest"
        self.asset_url = ""
        self.asset_name = ""
        self.manager = UpdateManager(str(info.get("version") or "0"), self)

        logo = QLabel(self)
        logo.setFixedSize(88, 88)
        logo.setPixmap(QPixmap(resource_path("favicon.ico")).scaled(88, 88))
        identity = QVBoxLayout()
        identity.addWidget(SubtitleLabel(str(info.get("name") or "IPTV-API"), self))
        identity.addWidget(BodyLabel(t("desktop.version_value").format(version=info.get("version") or "--"), self))
        identity.addWidget(BodyLabel(t("desktop.author_value").format(author="Guovin"), self))
        identity.addStretch(1)
        hero = QHBoxLayout()
        hero.addWidget(logo)
        hero.addSpacing(16)
        hero.addLayout(identity, 1)

        self.version_card = CardWidget(self)
        card_layout = QVBoxLayout(self.version_card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        self.version_status = StrongBodyLabel(t("desktop.update_not_checked"), self.version_card)
        self.version_detail = BodyLabel(t("desktop.update_check_desc"), self.version_card)
        self.progress = ProgressBar(self.version_card)
        self.progress.hide()
        actions = QHBoxLayout()
        self.check_button = PrimaryPushButton(FluentIcon.SYNC, t("desktop.check_updates"), self.version_card)
        self.download_button = PushButton(FluentIcon.DOWNLOAD, t("desktop.download_update"), self.version_card)
        self.download_button.hide()
        self.release_button = HyperlinkButton(FluentIcon.GLOBE, self.release_url, t("desktop.open_release"), self.version_card)
        actions.addWidget(self.check_button)
        actions.addWidget(self.download_button)
        actions.addWidget(self.release_button)
        actions.addStretch(1)
        card_layout.addWidget(self.version_status)
        card_layout.addWidget(self.version_detail)
        card_layout.addWidget(self.progress)
        card_layout.addLayout(actions)

        links = QHBoxLayout()
        links.addWidget(HyperlinkButton(FluentIcon.GITHUB, REPOSITORY_URL, t("desktop.github_repository"), self))
        links.addWidget(HyperlinkButton(FluentIcon.PEOPLE, "https://github.com/Guovin", t("desktop.author_homepage"), self))
        links.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(SubtitleLabel(t("desktop.about"), self))
        layout.addLayout(hero)
        layout.addWidget(self.version_card)
        layout.addLayout(links)
        layout.addStretch(1)

        self.check_button.clicked.connect(self.manager.check)
        self.download_button.clicked.connect(self._download)
        self.manager.check_started.connect(self._checking)
        self.manager.check_finished.connect(self._checked)
        self.manager.failed.connect(self._failed)
        self.manager.download_progress.connect(self._download_progress)
        self.manager.download_finished.connect(self._download_finished)

    def _checking(self):
        self.check_button.setEnabled(False)
        self.version_status.setText(t("desktop.checking_updates"))

    def _checked(self, result: dict):
        self.check_button.setEnabled(True)
        self.release_url = result["release_url"]
        self.release_button.setUrl(self.release_url)
        self.asset_url = result["asset_url"]
        self.asset_name = result["asset_name"]
        if result["newer"]:
            self.version_status.setText(t("desktop.update_available").format(version=result["latest"]))
            self.version_detail.setText(t("desktop.update_available_desc"))
            self.download_button.setVisible(bool(self.asset_url))
        else:
            self.version_status.setText(t("desktop.up_to_date"))
            self.version_detail.setText(t("desktop.current_version_latest").format(version=result["current"]))
            self.download_button.hide()

    def _download(self):
        if self.asset_url and self.asset_name:
            self.progress.setValue(0)
            self.progress.show()
            self.download_button.setEnabled(False)
            self.manager.download(self.asset_url, self.asset_name)

    def _download_progress(self, value: int):
        self.progress.setValue(value)

    def _download_finished(self, path: str):
        self.download_button.setEnabled(True)
        self.version_status.setText(t("desktop.update_downloaded"))
        self.version_detail.setText(path)
        InfoBar.success(t("desktop.update_downloaded"), path, parent=self, position=InfoBarPosition.TOP)
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def _failed(self, message: str):
        self.check_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self.version_status.setText(t("desktop.update_check_failed"))
        InfoBar.error(t("desktop.update_check_failed"), message, parent=self, position=InfoBarPosition.TOP)
