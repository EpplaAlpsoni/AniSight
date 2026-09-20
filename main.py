import json
import re
import sys
import urllib.request
from bisect import bisect_right
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QRectF, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap, QShortcut, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QFrame,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QStackedLayout,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ani_cli_integration import fetch_anime_seasons, fetch_search_results, fetch_trending_anime, find_ani_cli
from stream_proxy import StreamProxy


class ArtworkLabel(QLabel):
    """Keep original artwork for smooth, centered crops at every window size."""
    def __init__(self, hero=False, radius=0):
        super().__init__()
        self.artwork = QPixmap()
        self.hero = hero
        self.radius = radius
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

    def setPixmap(self, pixmap):
        self.artwork = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), QColor("#101725"))
        if not self.artwork.isNull():
            scaled = self.artwork.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
        if self.hero:
            shade = QLinearGradient(0, 0, self.width(), 0)
            shade.setColorAt(0, QColor(8, 13, 24, 195))
            shade.setColorAt(0.55, QColor(8, 13, 24, 62))
            shade.setColorAt(1, QColor(8, 13, 24, 8))
            painter.fillRect(self.rect(), shade)
            fade = QLinearGradient(0, 0, 0, self.height())
            fade.setColorAt(0, QColor(11, 19, 33, 0))
            fade.setColorAt(0.62, QColor(11, 19, 33, 10))
            fade.setColorAt(0.84, QColor(11, 19, 33, 90))
            fade.setColorAt(1, QColor("#0b1321"))
            painter.fillRect(self.rect(), fade)


class AnimeCard(QWidget):
    def __init__(self, result, on_click=None):
        super().__init__()
        self.result = result
        self.on_click = on_click
        self.setFixedWidth(178)
        self.setFixedHeight(316)
        self.setObjectName("animeCard")
        self.setStyleSheet(
            "QWidget#animeCard { background: transparent; border: 1px solid transparent; border-radius: 10px; }"
            "QWidget#animeCard:hover { background: #18243a; border: 1px solid rgba(112, 165, 226, 0.34); }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        self.poster = ArtworkLabel(radius=8)
        self.poster.setFixedSize(168, 236)
        self.poster.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.poster.setStyleSheet("background: #101725; border: none; border-radius: 8px;")
        self.poster.setScaledContents(False)

        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setFixedHeight(36)
        self.title.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.title.setStyleSheet("font-size: 13px; font-weight: 600; color: #e7edf7; padding: 0 2px;")
        self.title.setText(self._format_title(result["title"]))

        self.meta = QLabel(f"<span style='color:#78a8dc;'>★</span> <span style='color:#9eabba;'>{result.get('score', '-')}/100</span>")
        self.meta.setFixedHeight(18)
        self.meta.setStyleSheet("font-size: 11px; padding: 0 2px;")

        layout.addWidget(self.poster)
        layout.addWidget(self.title)
        layout.addWidget(self.meta)

        self.setCursor(Qt.PointingHandCursor)

    def _format_title(self, title):
        metrics = QFontMetrics(self.title.font())
        available_width = self.poster.width() - 4
        lines = []
        remaining = title.strip()

        for line_number in range(2):
            if not remaining:
                break
            if metrics.horizontalAdvance(remaining) <= available_width:
                lines.append(remaining)
                break

            words = remaining.split()
            current = ""
            consumed = 0
            for word in words:
                candidate = f"{current} {word}".strip()
                if current and metrics.horizontalAdvance(candidate) > available_width:
                    break
                current = candidate
                consumed += 1

            if not current or consumed == 0:
                lines.append(metrics.elidedText(remaining, Qt.ElideRight, available_width))
                break

            if line_number == 1 or consumed == len(words):
                lines.append(metrics.elidedText(remaining, Qt.ElideRight, available_width))
                break

            lines.append(current)
            remaining = " ".join(words[consumed:])

        return "\n".join(lines)

    def set_image(self, url):
        if not url:
            self.poster.setStyleSheet("background: #101725; border: none; border-radius: 8px;")
            return
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Referer": "https://anilist.co/",
            })
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
        except Exception:
            self.poster.setStyleSheet("background: #101725; border: none; border-radius: 8px;")
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if pixmap.isNull():
            self.poster.setStyleSheet("background: #101725; border: none; border-radius: 8px;")
            return
        self.poster.setPixmap(pixmap)

    def mousePressEvent(self, event):
        if self.on_click:
            self.on_click(self.result)
        super().mousePressEvent(event)


class SidebarButton(QToolButton):
    def __init__(self, label, page_name, icon_path):
        super().__init__()
        self.setText(label)
        self.page_name = page_name
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIcon(QIcon(icon_path))
        self.setIconSize(QSize(22, 22))
        self.setAutoRaise(True)
        self.setFixedWidth(80)
        self.setFixedHeight(70)
        self.setStyleSheet(
            """
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #aeb9c9;
                padding: 7px 3px 6px 3px;
                font-size: 10px;
                font-weight: 600;
            }
            QToolButton:checked {
                background: rgba(100, 151, 210, 0.18);
                border-left: 3px solid #73a6df;
                color: #8ab7e8;
            }
            QToolButton:hover {
                background: rgba(100, 151, 210, 0.10);
                color: #edf4fc;
            }
            """
        )


class AniSightWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Madomi")
        self.setStyleSheet(
            """
            QMainWindow {
                background: #0b101b;
                color: #edf3fb;
            }
            QWidget {
                color: #edf3fb;
                font-family: "Segoe UI", sans-serif;
            }
            QLabel {
                color: #edf3fb;
            }
            QLineEdit {
                background: rgba(14, 23, 39, 0.82);
                border: 1px solid rgba(112, 151, 198, 0.20);
                border-radius: 10px;
                padding: 10px 12px;
                color: #edf3fb;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(112, 165, 226, 0.76);
            }
            QPushButton {
                background: #6f9fd3;
                border: none;
                border-radius: 10px;
                color: #08111e;
                font-weight: 700;
                padding: 10px 16px;
            }
            QPushButton:hover {
                background: #8bb9e8;
            }
            QPushButton#secondary {
                background: rgba(91, 137, 190, 0.24);
                border: 1px solid rgba(126, 174, 225, 0.30);
                color: #edf4fc;
            }
            QPushButton#ghost {
                background: rgba(8, 10, 16, 0.38);
                border: 1px solid rgba(190, 207, 230, 0.24);
                color: #e4ecf6;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:horizontal, QScrollBar:vertical {
                background: transparent;
                border: none;
                width: 6px;
                height: 6px;
            }
            QScrollBar::handle { background: #405777; border-radius: 3px; min-width: 24px; min-height: 24px; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
            QPushButton:disabled { color: #68778a; background: #182234; }
            """
        )

        self.current_result = None
        self.available_seasons = []
        self.search_results = []
        self.settings = QSettings("Madomi", "Madomi")
        self.resolve_process = None
        self.stream_proxy = None
        self.playing_title = ""
        self.playing_episode = 1
        self.caption_cues = []
        self.caption_starts = []
        self.playback_mode = "sub"
        self.pending_resume_position = 0
        stored_recents = self.settings.value("recent_searches", [])
        self.recent_searches = stored_recents if isinstance(stored_recents, list) else []

        central = QWidget()
        central.setObjectName("appSurface")
        central.setStyleSheet("QWidget#appSurface { background: #0b101b; }")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(88)
        self.sidebar.setStyleSheet(
            "background: #090e18; border: none; border-right: 1px solid #162238;"
        )
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(4, 20, 4, 16)
        sidebar_layout.setSpacing(8)

        brand = QWidget()
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(0, 4, 0, 16)
        brand_layout.setSpacing(4)

        brand_icon = QLabel()
        brand_icon.setPixmap(QIcon("madomi-logo.svg").pixmap(34, 34))
        brand_icon.setAlignment(Qt.AlignCenter)

        brand_name = QLabel("Madomi")
        brand_name.setAlignment(Qt.AlignCenter)
        brand_name.setStyleSheet("font-family: Georgia, serif; font-size: 17px; font-weight: 700; color: #dce9f8;")

        brand_layout.addWidget(brand_icon)
        brand_layout.addWidget(brand_name)
        sidebar_layout.addWidget(brand)

        self.nav_group = QWidget()
        self.nav_group.setFixedWidth(80)
        nav_inner = QVBoxLayout(self.nav_group)
        nav_inner.setContentsMargins(0, 0, 0, 0)
        nav_inner.setSpacing(8)
        nav_inner.setAlignment(Qt.AlignHCenter)

        self.nav_buttons = {}
        nav_icons = {
            "home": "home-icon.svg",
            "search": "search-icon.svg",
            "accounts": "accounts-icon.svg",
            "settings": "settings-icon.svg",
        }
        for key, label in [("home", "Home"), ("search", "Search"), ("accounts", "Accounts")]:
            btn = SidebarButton(label, key, nav_icons[key])
            btn.clicked.connect(lambda checked, current=key: self.show_page(current))
            self.nav_buttons[key] = btn
            nav_inner.addWidget(btn)

        sidebar_layout.addWidget(self.nav_group, 0, Qt.AlignHCenter)
        sidebar_layout.addStretch(1)

        settings_button = SidebarButton("Settings", "settings", nav_icons["settings"])
        settings_button.clicked.connect(lambda checked: self.show_page("settings"))
        self.nav_buttons["settings"] = settings_button
        sidebar_layout.addWidget(settings_button, 0, Qt.AlignHCenter)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: transparent; }")

        self.home_page = self.build_home_page()
        self.search_page = self.build_search_page()
        self.details_page = self.build_details_page()
        self.accounts_page = self.build_placeholder_page("Accounts")
        self.settings_page = self.build_placeholder_page("Settings")
        self.player_page = self.build_player_page()

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.search_page)
        self.stack.addWidget(self.details_page)
        self.stack.addWidget(self.accounts_page)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.player_page)

        root.addWidget(self.sidebar)
        root.addWidget(self.stack, 1)

        self.show_page("home")
        QTimer.singleShot(0, self.load_home_screen)

    def build_home_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("homeContent")
        content.setStyleSheet("QWidget#homeContent { background: #0b1321; }")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.hero = QWidget()
        self.hero.setFixedHeight(580)
        hero_layers = QStackedLayout(self.hero)
        hero_layers.setContentsMargins(0, 0, 0, 0)
        hero_layers.setStackingMode(QStackedLayout.StackAll)
        self.hero_banner = ArtworkLabel(hero=True)
        hero_layers.addWidget(self.hero_banner)

        self.hero_content = QWidget()
        self.hero_content.setObjectName("heroContent")
        self.hero_content.setStyleSheet("QWidget#heroContent { background: transparent; }")
        hero_layout = QVBoxLayout(self.hero_content)
        hero_layout.setContentsMargins(0, 0, 0, 42)
        hero_layout.setSpacing(0)
        topbar = QWidget()
        topbar.setObjectName("homeTopbar")
        topbar.setStyleSheet("QWidget#homeTopbar { background: rgba(8, 14, 25, 0.62); border-bottom: 1px solid rgba(105, 148, 198, 0.14); }")
        topbar.setFixedHeight(76)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(44, 12, 44, 12)
        topbar_layout.addStretch()
        self.home_search_input = QLineEdit()
        self.home_search_input.setPlaceholderText("Search anime…")
        self.home_search_input.setClearButtonEnabled(True)
        self.home_search_input.addAction(QIcon("search-icon.svg"), QLineEdit.LeadingPosition)
        self.home_search_input.setFixedHeight(46)
        self.home_search_input.setMinimumWidth(240)
        self.home_search_input.setMaximumWidth(440)
        self.home_search_input.setStyleSheet("QLineEdit { background: rgba(10, 17, 29, 0.86); border: 1px solid #334866; border-radius: 23px; padding: 8px 16px; color: #e8f0fa; }")
        self.home_search_input.returnPressed.connect(self.search_from_home)
        self.home_search_input.setToolTip("Search anime (Ctrl+K)")
        topbar_layout.addWidget(self.home_search_input, 1)
        hero_layout.addWidget(topbar)
        hero_layout.addStretch(1)

        copy = QWidget()
        self.hero_copy_layout = QVBoxLayout(copy)
        self.hero_copy_layout.setContentsMargins(64, 30, 48, 0)
        self.hero_copy_layout.setSpacing(15)
        self.hero_kicker = QLabel("FEATURED TODAY  •  TRENDING ON ANILIST")
        self.hero_kicker.setStyleSheet("font-size: 11px; font-weight: 700; letter-spacing: 1px; color: #88b6e8;")
        self.hero_title = QLabel("Your next favorite awaits.")
        self.hero_title.setWordWrap(True)
        self.hero_title.setMinimumHeight(174)
        self.hero_title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.hero_title.setTextFormat(Qt.PlainText)
        self.hero_title.setMaximumWidth(690)
        self.hero_title.setStyleSheet("font-family: 'Segoe UI', sans-serif; font-size: 46px; font-weight: 800; color: #f1f5fb;")
        self.hero_meta = QLabel("Discover something worth watching")
        self.hero_meta.setStyleSheet("font-size: 12px; letter-spacing: 1px; color: #83b5e9;")
        self.hero_summary = QLabel("Finding tonight’s featured anime…")
        self.hero_summary.setWordWrap(True)
        self.hero_summary.setMaximumWidth(620)
        self.hero_summary.setFixedHeight(66)
        self.hero_summary.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.hero_summary.setStyleSheet("font-size: 15px; color: #bac7d7;")
        for widget in (self.hero_kicker, self.hero_title, self.hero_meta, self.hero_summary):
            self.hero_copy_layout.addWidget(widget)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.hero_more_button = QPushButton("More info")
        self.hero_more_button.setObjectName("secondary")
        self.hero_more_button.clicked.connect(self.open_current_details)
        self.hero_more_button.setEnabled(False)
        browse = QPushButton("Browse anime")
        browse.setObjectName("ghost")
        browse.clicked.connect(lambda: self.show_page("search"))
        for button in (self.hero_more_button, browse):
            button.setFixedHeight(46)
            button.setCursor(Qt.PointingHandCursor)
            actions.addWidget(button)
        actions.addStretch()
        self.hero_copy_layout.addSpacing(12)
        self.hero_copy_layout.addLayout(actions)
        hero_layout.addWidget(copy)
        hero_layers.addWidget(self.hero_content)
        hero_layers.setCurrentWidget(self.hero_content)
        layout.addWidget(self.hero)

        self.sections = QWidget()
        self.sections.setObjectName("showSections")
        self.sections.setStyleSheet(
            "QWidget#showSections { background: #0b1321; }"
        )
        self.sections_layout = QVBoxLayout(self.sections)
        self.sections_layout.setContentsMargins(64, 42, 48, 0)
        self.sections_layout.setSpacing(36)
        self.strip_trending = self.build_strip("Trending now")
        self.strip_top = self.build_strip("Discover more")
        self.sections_layout.addWidget(self.strip_trending)
        self.sections_layout.addWidget(self.strip_top)
        layout.addWidget(self.sections)
        page.setWidget(content)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.search_shortcut.activated.connect(lambda: self.show_page("search"))
        return page

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "hero_title"):
            self.fit_hero_title()

    def fit_hero_title(self):
        available = min(690, max(240, self.hero.width() - 112))
        font = self.hero_title.font()
        for size in range(48, 23, -2):
            font.setPixelSize(size)
            bounds = QFontMetrics(font).boundingRect(0, 0, available, 1000, Qt.TextWordWrap, self.hero_title.text())
            if bounds.height() <= 174:
                break
        self.hero_title.setStyleSheet(
            f"font-family: 'Segoe UI', sans-serif; font-size: {size}px; font-weight: 800; color: #f1f5fb;"
        )
        self.hero_title.setFixedHeight(max(60, min(174, bounds.height() + 8)))

    def build_search_page(self):
        page = QWidget()
        page.setObjectName("searchPage")
        page.setStyleSheet("QWidget#searchPage { background: #0b1321; }")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 36, 48, 36)
        layout.setSpacing(24)

        topbar = QWidget()
        topbar.setObjectName("searchHeader")
        topbar.setStyleSheet("QWidget#searchHeader { background: transparent; }")
        topbar.setMaximumWidth(1480)
        topbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(0, 0, 0, 0)
        topbar_layout.setSpacing(18)

        heading = QWidget()
        heading_layout = QVBoxLayout(heading)
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(3)
        title = QLabel("Find your next anime")
        title.setStyleSheet("font-size: 28px; font-weight: 800; color: #eef4fb;")
        subtitle = QLabel("Search the AniList catalogue")
        subtitle.setStyleSheet("font-size: 12px; color: #8293aa;")
        heading_layout.addWidget(title)
        heading_layout.addWidget(subtitle)

        self.search_page_input = QLineEdit()
        self.search_page_input.setPlaceholderText("Search by title…")
        self.search_page_input.setClearButtonEnabled(True)
        self.search_page_input.addAction(QIcon("search-icon.svg"), QLineEdit.LeadingPosition)
        self.search_page_input.setFixedHeight(46)
        self.search_page_input.setMinimumWidth(280)
        self.search_page_input.setMaximumWidth(560)
        self.search_page_input.setStyleSheet("QLineEdit { background: #101b2d; border: 1px solid #2e4360; border-radius: 23px; padding: 8px 16px; color: #e8f0fa; } QLineEdit:focus { border-color: #6d9fd6; }")
        self.search_page_input.returnPressed.connect(self.search_from_search_page)

        self.search_page_button = QPushButton("Search")
        self.search_page_button.setFixedHeight(46)
        self.search_page_button.clicked.connect(self.search_from_search_page)

        topbar_layout.addWidget(heading)
        topbar_layout.addStretch(1)
        topbar_layout.addWidget(self.search_page_input, 1)
        topbar_layout.addWidget(self.search_page_button)
        layout.addWidget(topbar, 0, Qt.AlignHCenter)

        self.recents_widget = QWidget()
        self.recents_widget.setObjectName("recentSearches")
        self.recents_widget.setStyleSheet("QWidget#recentSearches { background: transparent; }")
        self.recents_layout = QHBoxLayout(self.recents_widget)
        self.recents_layout.setContentsMargins(0, 0, 0, 0)
        self.recents_layout.setSpacing(8)
        self.recents_widget.setMaximumWidth(1480)
        self.recents_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.recents_widget, 0, Qt.AlignHCenter)
        self.refresh_recent_searches()

        self.search_results_title = QLabel("Results")
        self.search_results_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #dfe9f5;")
        self.search_results_title.setMaximumWidth(1480)
        self.search_results_title.setVisible(False)
        layout.addWidget(self.search_results_title)

        self.search_results_container = QWidget()
        self.search_results_container.setStyleSheet("background: transparent;")
        self.search_results_layout = QVBoxLayout(self.search_results_container)
        self.search_results_layout.setContentsMargins(0, 0, 0, 0)
        self.search_results_layout.setSpacing(16)

        search_hint = QLabel("Search for a title to explore available shows.")
        search_hint.setAlignment(Qt.AlignCenter)
        search_hint.setStyleSheet("font-size: 15px; color: #71839a; padding: 80px 20px;")
        self.search_results_layout.addWidget(search_hint)

        self.search_scroll = QScrollArea()
        self.search_scroll.setWidgetResizable(True)
        self.search_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.search_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.search_scroll.setMaximumWidth(1480)
        self.search_scroll.setWidget(self.search_results_container)
        layout.addWidget(self.search_scroll, 1)

        return page

    def refresh_recent_searches(self):
        if not hasattr(self, "recents_layout"):
            return
        while self.recents_layout.count():
            item = self.recents_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.recents_widget.setVisible(bool(self.recent_searches))
        if not self.recent_searches:
            return

        label = QLabel("Recent")
        label.setStyleSheet("font-size: 12px; font-weight: 700; color: #8fa5bf;")
        self.recents_layout.addWidget(label)
        for query in self.recent_searches[:6]:
            button = QPushButton(query)
            button.setObjectName("recentSearch")
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(32)
            button.setStyleSheet(
                "QPushButton { background: #132238; border: 1px solid #263c58; "
                "border-radius: 16px; color: #b9c9da; padding: 0 13px; font-weight: 600; }"
                "QPushButton:hover { background: #1a304e; border-color: #4773a5; color: #eef5fc; }"
            )
            button.clicked.connect(lambda checked=False, value=query: self.search_recent(value))
            self.recents_layout.addWidget(button)
        self.recents_layout.addStretch(1)

    def search_recent(self, query):
        self.search_page_input.setText(query)
        self.search_from_search_page()

    def build_details_page(self):
        page = QScrollArea()
        page.setObjectName("detailsPage")
        page.setWidgetResizable(True)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        page.setStyleSheet("QScrollArea#detailsPage { background: #0b1321; }")

        content = QWidget()
        content.setObjectName("detailsContent")
        content.setStyleSheet("QWidget#detailsContent { background: #0b1321; }")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(48, 28, 48, 32)
        layout.setSpacing(20)

        topbar = QWidget()
        topbar.setObjectName("detailsHeader")
        topbar.setStyleSheet("QWidget#detailsHeader { background: transparent; }")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(0, 0, 0, 0)

        self.details_back_button = QPushButton("←  Back")
        self.details_back_button.setObjectName("ghost")
        self.details_back_button.setFixedHeight(42)
        self.details_back_button.clicked.connect(lambda: self.show_page("home"))
        details_label = QLabel("Show details")
        details_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #8fa5bf;")
        self.details_watch_button = QPushButton("Watch now")
        self.details_watch_button.setFixedHeight(42)
        self.details_watch_button.clicked.connect(self.watch_selected_result)
        topbar_layout.addWidget(self.details_back_button)
        topbar_layout.addWidget(details_label)
        topbar_layout.addStretch(1)
        topbar_layout.addWidget(self.details_watch_button)
        layout.addWidget(topbar)

        self.detail_banner = ArtworkLabel(radius=16)
        self.detail_banner.setFixedHeight(230)
        self.detail_banner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.detail_banner.setStyleSheet("background: #111d30; border-radius: 16px;")
        layout.addWidget(self.detail_banner)

        detail_content = QWidget()
        detail_content.setObjectName("detailCard")
        detail_content.setStyleSheet("QWidget#detailCard { background: #101b2d; border: 1px solid rgba(112, 151, 198, 0.18); border-radius: 16px; }")
        detail_content.setMinimumHeight(302)
        detail_layout = QHBoxLayout(detail_content)
        detail_layout.setContentsMargins(24, 24, 24, 24)
        detail_layout.setSpacing(28)

        self.detail_poster = ArtworkLabel(radius=12)
        self.detail_poster.setFixedSize(180, 254)
        self.detail_poster.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.detail_poster.setStyleSheet("background: #0d1726; border-radius: 12px;")

        info = QWidget()
        info.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(12)

        self.detail_title = QLabel("Title")
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet("font-size: 32px; font-weight: 800; color: #eef4fb;")
        self.detail_meta = QLabel("★ 0/100")
        self.detail_meta.setStyleSheet("font-size: 13px; color: #83b5e9;")
        season_row = QWidget()
        season_row.setStyleSheet("background: transparent;")
        season_layout = QHBoxLayout(season_row)
        season_layout.setContentsMargins(0, 0, 0, 0)
        season_layout.setSpacing(10)
        season_label = QLabel("Season")
        season_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #8fa5bf;")
        self.season_combo = QComboBox()
        self.season_combo.setMinimumWidth(230)
        self.season_combo.setFixedHeight(38)
        self.season_combo.setCursor(Qt.PointingHandCursor)
        self.season_combo.setStyleSheet(
            "QComboBox { background: #15243a; border: 1px solid #2b4465; border-radius: 9px; "
            "color: #e2ebf6; padding: 0 12px; font-weight: 600; }"
            "QComboBox:hover { border-color: #5686bc; background: #192b45; }"
            "QComboBox::drop-down { border: none; width: 30px; }"
            "QComboBox QAbstractItemView { background: #101b2d; border: 1px solid #2b4465; "
            "color: #e2ebf6; selection-background-color: #27476d; padding: 6px; }"
        )
        self.season_combo.currentIndexChanged.connect(self.select_season)
        season_layout.addWidget(season_label)
        season_layout.addWidget(self.season_combo)
        season_layout.addStretch(1)
        self.detail_genres = QLabel("")
        self.detail_genres.setWordWrap(True)
        self.detail_genres.setStyleSheet("font-size: 12px; color: #8293aa;")
        self.detail_description = QLabel("Description")
        self.detail_description.setWordWrap(True)
        self.detail_description.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.detail_description.setStyleSheet("font-size: 14px; color: #b8c5d5;")

        info_layout.addWidget(self.detail_title)
        info_layout.addWidget(self.detail_meta)
        info_layout.addWidget(season_row)
        info_layout.addWidget(self.detail_genres)
        info_layout.addSpacing(4)
        info_layout.addWidget(self.detail_description)
        info_layout.addStretch(1)

        detail_layout.addWidget(self.detail_poster)
        detail_layout.addWidget(info, 1)
        layout.addWidget(detail_content)

        episodes_title = QLabel("Episodes")
        episodes_title.setStyleSheet("font-size: 21px; font-weight: 700; color: #dbe9f8;")
        layout.addWidget(episodes_title)

        self.episodes_container = QWidget()
        self.episodes_container.setStyleSheet("background: transparent;")
        self.episodes_layout = QGridLayout(self.episodes_container)
        self.episodes_layout.setContentsMargins(0, 0, 0, 0)
        self.episodes_layout.setHorizontalSpacing(10)
        self.episodes_layout.setVerticalSpacing(10)
        layout.addWidget(self.episodes_container)
        layout.addStretch(1)

        page.setWidget(content)
        return page

    def build_player_page(self):
        page = QWidget()
        page.setObjectName("playerPage")
        page.setStyleSheet("QWidget#playerPage { background: #070b12; }")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 28)
        layout.setSpacing(16)

        toolbar = QWidget()
        toolbar.setStyleSheet("background: transparent;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(12)

        back_button = QPushButton("←  Back to details")
        back_button.setObjectName("ghost")
        back_button.setFixedHeight(42)
        back_button.clicked.connect(self.close_player)
        self.player_title = QLabel("Now playing")
        self.player_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #e5edf7;")
        toolbar_layout.addWidget(back_button)
        toolbar_layout.addWidget(self.player_title)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)

        player_shell = QWidget()
        player_shell.setObjectName("playerShell")
        player_shell.setStyleSheet("QWidget#playerShell { background: #030508; border: 1px solid #1d304a; border-radius: 12px; }")
        shell_layout = QStackedLayout(player_shell)
        shell_layout.setContentsMargins(1, 1, 1, 1)
        shell_layout.setStackingMode(QStackedLayout.StackAll)

        self.player_surface = QVideoWidget()
        self.player_surface.setStyleSheet("background: #000000; border-radius: 11px;")
        self.player_surface.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        shell_layout.addWidget(self.player_surface)

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.8)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.player_surface)
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.media_player.errorOccurred.connect(self.on_media_error)
        self.media_player.positionChanged.connect(self.on_player_position)
        self.media_player.durationChanged.connect(self.on_player_duration)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)

        self.player_status = QLabel("Select an episode to start watching")
        self.player_status.setAlignment(Qt.AlignCenter)
        self.player_status.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.player_status.setStyleSheet("background: transparent; color: #71849b; font-size: 15px;")
        shell_layout.addWidget(self.player_status)

        caption_overlay = QWidget()
        caption_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        caption_overlay.setStyleSheet("background: transparent;")
        caption_layout = QVBoxLayout(caption_overlay)
        caption_layout.setContentsMargins(60, 20, 60, 28)
        caption_layout.addStretch(1)
        self.caption_label = QLabel("")
        self.caption_label.setWordWrap(True)
        self.caption_label.setAlignment(Qt.AlignCenter)
        self.caption_label.setStyleSheet(
            "background: rgba(0, 0, 0, 0.78); color: white; border-radius: 6px; "
            "font-size: 18px; font-weight: 600; padding: 7px 12px;"
        )
        self.caption_label.hide()
        caption_layout.addWidget(self.caption_label, 0, Qt.AlignHCenter)
        shell_layout.addWidget(caption_overlay)
        shell_layout.setCurrentWidget(caption_overlay)
        layout.addWidget(player_shell, 1)

        timeline = QHBoxLayout()
        timeline.setSpacing(10)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedWidth(105)
        self.time_label.setStyleSheet("font-size: 11px; color: #8fa0b4;")
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self.media_player.setPosition)
        self.seek_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #21334b; border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #70a5df; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #dceafa; width: 13px; margin: -5px 0; border-radius: 6px; }"
        )
        timeline.addWidget(self.time_label)
        timeline.addWidget(self.seek_slider, 1)
        layout.addLayout(timeline)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        control_style = (
            "QPushButton { background: #132238; border: 1px solid #293f5c; border-radius: 8px; "
            "color: #dce7f4; padding: 8px 12px; font-weight: 600; }"
            "QPushButton:hover { background: #1b3150; border-color: #4773a5; }"
            "QPushButton:checked { background: #294e77; border-color: #6e9ed1; }"
        )
        self.previous_episode_button = QPushButton("Previous episode")
        self.rewind_button = QPushButton("−10s")
        self.play_pause_button = QPushButton("Pause")
        self.forward_button = QPushButton("+10s")
        self.next_episode_button = QPushButton("Next episode")
        for button in (
            self.previous_episode_button,
            self.rewind_button,
            self.play_pause_button,
            self.forward_button,
            self.next_episode_button,
        ):
            button.setStyleSheet(control_style)
            button.setCursor(Qt.PointingHandCursor)
        self.previous_episode_button.clicked.connect(lambda: self.change_episode(-1))
        self.rewind_button.clicked.connect(lambda: self.skip_seconds(-10))
        self.play_pause_button.clicked.connect(self.toggle_playback)
        self.forward_button.clicked.connect(lambda: self.skip_seconds(10))
        self.next_episode_button.clicked.connect(lambda: self.change_episode(1))
        controls.addWidget(self.previous_episode_button)
        controls.addWidget(self.rewind_button)
        controls.addWidget(self.play_pause_button)
        controls.addWidget(self.forward_button)
        controls.addWidget(self.next_episode_button)
        controls.addStretch(1)

        self.captions_button = QPushButton("CC On")
        self.captions_button.setCheckable(True)
        self.captions_button.setChecked(True)
        self.captions_button.setStyleSheet(control_style)
        self.captions_button.toggled.connect(self.update_caption)
        self.language_combo = QComboBox()
        self.language_combo.setMinimumWidth(180)
        self.language_combo.setFixedHeight(36)
        self.language_combo.addItem("Japanese · Subtitles", "sub")
        self.language_combo.addItem("English · Dub", "dub")
        self.language_combo.setStyleSheet(
            "QComboBox { background: #132238; border: 1px solid #293f5c; border-radius: 8px; "
            "color: #dce7f4; padding: 0 10px; }"
            "QComboBox QAbstractItemView { background: #101b2d; color: #e2ebf6; selection-background-color: #27476d; }"
        )
        self.language_combo.currentIndexChanged.connect(self.change_language)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.setToolTip("Volume")
        self.volume_slider.valueChanged.connect(lambda value: self.audio_output.setVolume(value / 100))
        fullscreen_button = QPushButton("Full screen")
        fullscreen_button.setStyleSheet(control_style)
        fullscreen_button.clicked.connect(lambda: self.player_surface.setFullScreen(not self.player_surface.isFullScreen()))
        controls.addWidget(self.captions_button)
        controls.addWidget(self.language_combo)
        controls.addWidget(QLabel("Volume"))
        controls.addWidget(self.volume_slider)
        controls.addWidget(fullscreen_button)
        layout.addLayout(controls)
        return page

    def build_placeholder_page(self, title):
        page = QWidget()
        page.setObjectName(f"{title.lower()}Page")
        page.setStyleSheet(f"QWidget#{title.lower()}Page {{ background: #0b1321; }}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 36, 48, 36)
        layout.setSpacing(24)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 28px; font-weight: 800; color: #eef4fb;")
        subtitle_text = {
            "Accounts": "Manage the services connected to Madomi.",
            "Settings": "Choose how Madomi looks and plays your anime.",
        }.get(title, "")
        subtitle = QLabel(subtitle_text)
        subtitle.setStyleSheet("font-size: 13px; color: #8293aa;")
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        card = QWidget()
        card.setObjectName("emptyStateCard")
        card.setMaximumWidth(680)
        card.setStyleSheet(
            "QWidget#emptyStateCard { background: #101b2d; "
            "border: 1px solid rgba(112, 151, 198, 0.18); border-radius: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(12)

        icon = QLabel()
        icon_path = "accounts-icon.svg" if title == "Accounts" else "settings-icon.svg"
        icon.setPixmap(QIcon(icon_path).pixmap(32, 32))
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("background: #172740; border-radius: 10px;")

        card_title = QLabel("No accounts connected" if title == "Accounts" else "Settings are coming soon")
        card_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #e8f0fa;")
        card_body = QLabel(
            "Account connections will appear here when they become available."
            if title == "Accounts"
            else "Playback and appearance controls will live here in a future update."
        )
        card_body.setWordWrap(True)
        card_body.setStyleSheet("font-size: 14px; color: #98a8bb;")

        card_layout.addWidget(icon)
        card_layout.addWidget(card_title)
        card_layout.addWidget(card_body)
        layout.addWidget(card, 0, Qt.AlignLeft)
        layout.addStretch(1)
        return page

    def show_page(self, page_name):
        mapping = {"home": 0, "search": 1, "details": 2, "accounts": 3, "settings": 4, "player": 5}
        if page_name in mapping:
            self.stack.setCurrentIndex(mapping[page_name])
            if page_name == "search":
                self.search_page_input.setFocus()
            for key, button in self.nav_buttons.items():
                button.setChecked(key == page_name)

    def build_strip(self, title):
        strip = QWidget()
        strip_layout = QVBoxLayout(strip)
        strip_layout.setContentsMargins(0, 0, 0, 0)
        strip_layout.setSpacing(12)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 21px; font-weight: 700; color: #e3ebf6;")
        context_label = QLabel("VIA ANILIST")
        context_label.setStyleSheet("font-size: 10px; font-weight: 600; letter-spacing: 1px; color: #8192a8;")
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Plain)
        divider.setStyleSheet("color: rgba(112, 151, 198, 0.28);")
        divider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        header_layout.addWidget(title_label)
        divider.setFixedWidth(40)
        header_layout.addWidget(divider)
        header_layout.addWidget(context_label)
        header_layout.addStretch()
        strip_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(334)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QHBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 2, 0, 4)
        scroll_layout.setSpacing(22)
        scroll_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        scroll.setWidget(scroll_content)
        strip_layout.addWidget(scroll)

        strip._content = scroll_content
        strip._layout = scroll_layout
        return strip

    def _populate_strip(self, strip, results):
        for _ in range(strip._layout.count()):
            item = strip._layout.itemAt(0)
            if item.widget():
                item.widget().deleteLater()
            strip._layout.removeItem(item)

        for result in results:
            card = AnimeCard(result, on_click=self.open_details)
            card.set_image(result.get("poster_url"))
            strip._layout.addWidget(card)

        strip._content.setMinimumHeight(316)

    def populate_search_results(self, results):
        self.search_results_title.setVisible(True)
        self.search_results_title.setText(f"Results  ·  {len(results)} shows")
        for _ in range(self.search_results_layout.count()):
            item = self.search_results_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        if not results:
            empty = QLabel("No results found.")
            empty.setStyleSheet("font-size: 16px; color: #b8c5d5;")
            self.search_results_layout.addWidget(empty)
            return

        grid = QWidget()
        grid_layout = QVBoxLayout(grid)
        grid_layout.setSpacing(14)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        row = []
        for result in results:
            card = AnimeCard(result, on_click=self.open_details)
            card.set_image(result.get("poster_url"))
            row.append(card)
            if len(row) == 6:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(14)
                for widget in row:
                    row_layout.addWidget(widget)
                row_layout.addStretch(1)
                grid_layout.addWidget(row_widget)
                row = []

        if row:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(14)
            for widget in row:
                row_layout.addWidget(widget)
            row_layout.addStretch(1)
            grid_layout.addWidget(row_widget)

        self.search_results_layout.addWidget(grid)

    def open_details(self, result):
        seasons = fetch_anime_seasons(result["title"])
        self.available_seasons = seasons or [result]

        selected_index = 0
        result_url = result.get("site_url", "")
        for index, season_result in enumerate(self.available_seasons):
            if (result_url and season_result.get("site_url") == result_url) or season_result["title"].casefold() == result["title"].casefold():
                selected_index = index
                break

        self.season_combo.blockSignals(True)
        self.season_combo.clear()
        for index, season_result in enumerate(self.available_seasons, start=1):
            label = f"Season {index} — {season_result['title']}"
            self.season_combo.addItem(label)
        self.season_combo.setCurrentIndex(selected_index)
        self.season_combo.setEnabled(len(self.available_seasons) > 1)
        self.season_combo.blockSignals(False)
        self.display_season(self.available_seasons[selected_index])
        self.show_page("details")

    def select_season(self, index):
        if 0 <= index < len(self.available_seasons):
            self.display_season(self.available_seasons[index])

    def display_season(self, result):
        self.current_result = result
        self.detail_title.setText(result["title"])
        self.detail_meta.setText(f"★ {result.get('score', '-')}/100  •  {result.get('episodes', '-')} eps")
        genres = result.get("genres", "")
        self.detail_genres.setText(genres if genres else "Anime")
        self.detail_description.setText((result.get("description", "")[:500] + "...") if len(result.get("description", "")) > 500 else result.get("description", ""))
        self.set_banner_image(result.get("banner_url") or result.get("poster_url"), self.detail_banner)
        self.set_poster_image(result.get("poster_url"), self.detail_poster)

        for _ in range(self.episodes_layout.count()):
            item = self.episodes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        episode_count = str(result.get("episodes", "12"))
        episode_count = int(episode_count) if episode_count.isdigit() else 12
        for episode in range(1, (episode_count or 12) + 1):
            btn = QPushButton(f"Episode {episode:02d}")
            btn.setObjectName("secondary")
            btn.setFixedHeight(46)
            btn.setStyleSheet(
                "QPushButton { background: #15243a; border: 1px solid #263d5b; "
                "border-radius: 9px; color: #dbe8f7; text-align: left; padding: 0 16px; }"
                "QPushButton:hover { background: #1c3150; border-color: #4773a5; }"
            )
            btn.clicked.connect(lambda checked, q=result["title"], episode=episode: self.watch_episode_selection(q, episode))
            self.episodes_layout.addWidget(btn, (episode - 1) // 4, (episode - 1) % 4)

    def open_current_details(self):
        if self.current_result:
            self.open_details(self.current_result)

    def set_banner_image(self, url, target):
        if not url:
            target.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d2d48, stop:1 #0b101b); border-radius: 18px;")
            return
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Referer": "https://anilist.co/",
            })
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
        except Exception:
            target.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d2d48, stop:1 #0b101b); border-radius: 18px;")
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if pixmap.isNull():
            target.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d2d48, stop:1 #0b101b); border-radius: 18px;")
            return
        target.setPixmap(pixmap)

    def set_poster_image(self, url, target):
        if not url:
            target.setStyleSheet("background: #101827; border: 1px solid rgba(112, 151, 198, 0.18); border-radius: 16px;")
            return
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Referer": "https://anilist.co/",
            })
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
        except Exception:
            target.setStyleSheet("background: #101827; border: 1px solid rgba(112, 151, 198, 0.18); border-radius: 16px;")
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if pixmap.isNull():
            target.setStyleSheet("background: #101827; border: 1px solid rgba(112, 151, 198, 0.18); border-radius: 16px;")
            return
        target.setPixmap(pixmap)

    def on_card_click(self, result):
        self.current_result = result
        self.hero_title.setText(result["title"])
        self.hero_more_button.setEnabled(True)
        self.fit_hero_title()
        self.hero_meta.setText(f"★ {result.get('score', '-')}/100  •  {result.get('episodes', '-')} episodes")
        text = result.get("description", "")
        preview_limit = 175
        if len(text) > preview_limit:
            preview = text[:preview_limit].rsplit(" ", 1)[0].rstrip(".,;:") + "…"
        else:
            preview = text
        self.hero_summary.setText(preview)
        self.set_banner_image(result.get("banner_url") or result.get("poster_url"), self.hero_banner)

    def load_home_screen(self):
        trending = fetch_trending_anime(8)
        top = fetch_search_results("shonen")[:8]
        if not trending:
            trending = fetch_search_results("anime")[:8]
        if not top:
            top = trending
        self.home_results = trending
        self._populate_strip(self.strip_trending, trending)
        self._populate_strip(self.strip_top, top)
        if trending:
            self.on_card_click(trending[0])
        else:
            self.hero_summary.setText("The catalogue is unavailable right now. Try searching for a title.")

    def search_from_home(self):
        query = self.home_search_input.text().strip()
        if not query:
            query = "naruto"
        self.search_page_input.setText(query)
        self.search_from_search_page()
        self.show_page("search")

    def search_from_search_page(self):
        query = self.search_page_input.text().strip()
        if not query:
            query = "naruto"
        self.recent_searches = [item for item in self.recent_searches if item.casefold() != query.casefold()]
        self.recent_searches.insert(0, query)
        self.recent_searches = self.recent_searches[:6]
        self.settings.setValue("recent_searches", self.recent_searches)
        self.refresh_recent_searches()
        results = fetch_search_results(query)
        self.search_results = results
        self.populate_search_results(results)
        if results:
            self.current_result = results[0]
            self.on_card_click(results[0])

    def watch_selected_result(self):
        if not self.current_result:
            return
        self.play_in_app(self.current_result["title"], 1)

    def watch_episode_selection(self, title, episode):
        self.play_in_app(title, episode)

    def play_in_app(self, title, episode, resume_position=0):
        self.stop_embedded_player()
        self.playing_title = title
        self.playing_episode = episode
        self.pending_resume_position = resume_position
        episode_count = str((self.current_result or {}).get("episodes", ""))
        maximum = int(episode_count) if episode_count.isdigit() else episode
        self.previous_episode_button.setEnabled(episode > 1)
        self.next_episode_button.setEnabled(episode < maximum)
        self.player_title.setText(f"{title}  ·  Episode {episode}")
        self.player_status.setText("Resolving stream…")
        self.player_status.show()
        self.show_page("player")

        self.resolve_process = QProcess(self)
        self.resolve_process.setProcessChannelMode(QProcess.MergedChannels)
        environment = QProcessEnvironment.systemEnvironment()
        capture_player = str(Path(__file__).with_name("madomi_mpv_capture").resolve())
        environment.insert("ANI_CLI_PLAYER", capture_player)
        environment.insert("ANI_CLI_MENU", "grep")
        environment.insert("ANI_CLI_LOG", "0")
        environment.insert("ANI_CLI_MODE", self.playback_mode)
        self.resolve_process.setProcessEnvironment(environment)
        self.resolve_process.finished.connect(self.stream_resolved)
        self.resolve_process.start(
            find_ani_cli(),
            ["--no-detach", "--exit-after-play", "-S", "1", "-e", str(episode), title],
        )

    def stream_resolved(self, exit_code, exit_status):
        if not self.resolve_process:
            return
        output = bytes(self.resolve_process.readAll()).decode("utf-8", errors="replace")
        output = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)
        match = re.search(r"MADOMI_STREAM:(\{.*\})", output)
        if not match:
            message = next((line.strip() for line in reversed(output.splitlines()) if line.strip()), "Unable to resolve this episode.")
            self.player_status.setText(message)
            self.player_status.show()
            return

        try:
            stream = json.loads(match.group(1))
            stream_url = stream["url"]
            referrer = stream["referrer"]
            subtitle_url = stream.get("subtitle", "")
        except (json.JSONDecodeError, KeyError):
            self.player_status.setText("ani-cli returned an invalid stream.")
            self.player_status.show()
            return

        if not self.stream_proxy:
            self.stream_proxy = StreamProxy()
        local_stream = self.stream_proxy.url_for(stream_url, referrer)
        self.load_captions(subtitle_url, referrer)
        self.player_status.setText("Loading episode…")
        self.player_status.show()
        self.media_player.setSource(QUrl(local_stream))
        self.media_player.play()

    def on_media_status_changed(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.player_status.hide()
            if self.pending_resume_position > 0:
                resume_position = self.pending_resume_position
                self.pending_resume_position = 0
                self.media_player.setPosition(resume_position)
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.change_episode(1)
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.player_status.setText("This stream could not be played.")
            self.player_status.show()

    def on_media_error(self, error, message):
        if error != QMediaPlayer.Error.NoError:
            self.player_status.setText(message or "Playback failed.")
            self.player_status.show()

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def on_playback_state_changed(self, state):
        self.play_pause_button.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    def skip_seconds(self, seconds):
        target = self.media_player.position() + seconds * 1000
        self.media_player.setPosition(max(0, min(target, self.media_player.duration())))

    def change_episode(self, offset):
        episode_count = str((self.current_result or {}).get("episodes", ""))
        maximum = int(episode_count) if episode_count.isdigit() else self.playing_episode
        target = self.playing_episode + offset
        if 1 <= target <= maximum:
            self.play_in_app(self.playing_title, target)

    def on_player_position(self, position):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)
        self.time_label.setText(f"{self.format_time(position)} / {self.format_time(self.media_player.duration())}")
        self.update_caption()

    def on_player_duration(self, duration):
        self.seek_slider.setRange(0, max(0, duration))
        self.time_label.setText(f"{self.format_time(self.media_player.position())} / {self.format_time(duration)}")

    @staticmethod
    def format_time(milliseconds):
        seconds = max(0, milliseconds // 1000)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    def load_captions(self, subtitle_url, referrer):
        self.caption_cues = []
        self.caption_starts = []
        self.caption_label.hide()
        self.captions_button.setEnabled(False)
        if not subtitle_url or not self.stream_proxy:
            return
        try:
            local_url = self.stream_proxy.url_for(subtitle_url, referrer)
            text = urllib.request.urlopen(local_url, timeout=12).read().decode("utf-8", errors="replace")
        except Exception:
            return

        timestamp = r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})"
        for block in re.split(r"\r?\n\s*\r?\n", text):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            timing_index = next((index for index, line in enumerate(lines) if "-->" in line), -1)
            if timing_index < 0:
                continue
            match = re.match(rf"{timestamp}\s*-->\s*{timestamp}", lines[timing_index])
            if not match:
                continue
            values = [int(value or 0) for value in match.groups()]
            start = ((values[0] * 60 + values[1]) * 60 + values[2]) * 1000 + values[3]
            end = ((values[4] * 60 + values[5]) * 60 + values[6]) * 1000 + values[7]
            caption = "\n".join(lines[timing_index + 1:])
            caption = re.sub(r"<[^>]+>", "", caption)
            if caption:
                self.caption_cues.append((start, end, caption))
        self.caption_starts = [cue[0] for cue in self.caption_cues]
        self.captions_button.setEnabled(bool(self.caption_cues))

    def update_caption(self, *args):
        self.captions_button.setText("CC On" if self.captions_button.isChecked() else "CC Off")
        if not self.captions_button.isChecked() or not self.caption_cues:
            self.caption_label.hide()
            return
        position = self.media_player.position()
        index = bisect_right(self.caption_starts, position) - 1
        if index >= 0:
            start, end, text = self.caption_cues[index]
            if start <= position <= end:
                self.caption_label.setText(text)
                self.caption_label.show()
                return
        self.caption_label.hide()

    def change_language(self, index):
        mode = self.language_combo.itemData(index)
        if not mode or mode == self.playback_mode or not self.playing_title:
            return
        resume_position = self.media_player.position()
        self.playback_mode = mode
        self.play_in_app(self.playing_title, self.playing_episode, resume_position)

    def stop_embedded_player(self):
        if hasattr(self, "media_player"):
            self.media_player.stop()
            self.media_player.setSource(QUrl())
        if self.resolve_process and self.resolve_process.state() != QProcess.NotRunning:
            self.resolve_process.kill()
            self.resolve_process.waitForFinished(500)
        self.resolve_process = None

    def close_player(self):
        self.stop_embedded_player()
        self.player_status.show()
        self.show_page("details")

    def closeEvent(self, event):
        self.stop_embedded_player()
        if self.stream_proxy:
            self.stream_proxy.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = AniSightWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
