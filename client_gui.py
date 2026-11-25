import sys
import json
import asyncio
import qasync
import websockets
import aiohttp

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QMessageBox,
    QStackedWidget, QTabWidget, QCheckBox, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPixmap, QDesktopServices

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

AVAILABLE_GENRES = [
    "Хоррор", "Фантастика", "Триллер", "Детектив",
    "Комедия", "Драма", "Боевик", "Мультфильмы",
]

SERVER_URL = "ws://127.0.0.1:8765"


class CineSyncClient(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CineSync")
        self.resize(900, 680)

        self.ws = None
        self.listen_task = None
        self.current_user = None
        self.current_room = ""
        self.movies = []
        self.current_index = 0
        self.matched_movie = None

        self._apply_styles()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack)

        self._build_auth_screen()   # index 0
        self._build_lobby_screen()  # index 1
        self._build_swipe_screen()  # index 2
        self._build_match_screen()  # index 3

        self.stack.setCurrentIndex(0)

    def _apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #f2f2f7;
                font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
                font-size: 14px;
            }
            QFrame#Card {
                background-color: #262628;
                border: 1px solid #353538;
                border-radius: 14px;
            }
            QFrame#ReviewCard {
                background-color: #2c2c2e;
                border-radius: 10px;
                padding: 8px;
            }
            QLineEdit {
                background-color: #2d2d2f;
                border: 1px solid #3f3f42;
                border-radius: 8px;
                padding: 10px;
                color: #ffffff;
            }
            QLineEdit:focus {
                border: 1px solid #d4a33d;
            }
            QPushButton {
                background-color: #3a3a3c;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 11px 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #4a4a4d; }
            QPushButton:disabled { background-color: #2c2c2e; color: #666666; }

            QPushButton#PrimaryBtn, QPushButton#LikeBtn {
                background-color: #d4a33d;
                color: #1e1e1e;
            }
            QPushButton#PrimaryBtn:hover, QPushButton#LikeBtn:hover {
                background-color: #c29334;
            }
            QPushButton#SkipBtn {
                background-color: #555555;
                color: #ffffff;
            }
            QPushButton#SkipBtn:hover { background-color: #666666; }

            QTabWidget::pane {
                border: 1px solid #353538;
                border-radius: 10px;
                background-color: #262628;
                padding: 12px;
            }
            QTabBar::tab {
                background-color: #2c2c2e;
                color: #aaaaaa;
                padding: 9px 20px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #3a3a3c;
                color: #d4a33d;
                font-weight: bold;
            }
            QCheckBox {
                spacing: 8px;
                background: transparent;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

    # ================= ЭКРАН 0: АВТОРИЗАЦИЯ =================
    def _build_auth_screen(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("Card")
        card.setFixedWidth(460)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(14)

        title = QLabel("CineSync")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #d4a33d; background: transparent;")
        subtitle = QLabel("Совместный выбор и просмотр трейлеров")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #9e9ea4; background: transparent;")
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        tabs = QTabWidget()

        # Вкладка Вход
        login_tab = QWidget()
        l_lay = QVBoxLayout(login_tab)
        l_lay.setSpacing(12)
        self.login_user_input = QLineEdit(placeholderText="Логин")
        self.login_pass_input = QLineEdit(placeholderText="Пароль")
        self.login_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        login_btn = QPushButton("Войти")
        login_btn.setObjectName("PrimaryBtn")
        login_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.do_login()))
        l_lay.addWidget(self.login_user_input)
        l_lay.addWidget(self.login_pass_input)
        l_lay.addWidget(login_btn)
        l_lay.addStretch()

        # Вкладка Регистрация
        reg_tab = QWidget()
        r_lay = QVBoxLayout(reg_tab)
        r_lay.setSpacing(10)
        self.reg_user_input = QLineEdit(placeholderText="Придумайте логин")
        self.reg_pass_input = QLineEdit(placeholderText="Придумайте пароль (от 4 символов)")
        self.reg_pass_input.setEchoMode(QLineEdit.EchoMode.Password)

        genres_lbl = QLabel("Ваши любимые жанры:")
        genres_lbl.setStyleSheet("color: #b5b5bb; font-weight: bold; background: transparent;")
        genres_grid = QGridLayout()
        self.reg_genre_checks: list[QCheckBox] = []
        for idx, genre in enumerate(AVAILABLE_GENRES):
            cb = QCheckBox(genre)
            self.reg_genre_checks.append(cb)
            genres_grid.addWidget(cb, idx // 2, idx % 2)

        self.reg_fav_movies_input = QLineEdit(placeholderText="Любимые фильмы (например: Синистер, Начало)")
        reg_btn = QPushButton("Зарегистрироваться")
        reg_btn.setObjectName("PrimaryBtn")
        reg_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.do_register()))

        r_lay.addWidget(self.reg_user_input)
        r_lay.addWidget(self.reg_pass_input)
        r_lay.addWidget(genres_lbl)
        r_lay.addLayout(genres_grid)
        r_lay.addWidget(self.reg_fav_movies_input)
        r_lay.addWidget(reg_btn)

        tabs.addTab(login_tab, "Вход (Sign In)")
        tabs.addTab(reg_tab, "Регистрация (Sign Up)")
        card_layout.addWidget(tabs)

        self.auth_status_lbl = QLabel("")
        self.auth_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.auth_status_lbl.setStyleSheet("color: #e06c75; background: transparent;")
        card_layout.addWidget(self.auth_status_lbl)

        outer.addWidget(card)
        self.stack.addWidget(page)
    # ================= ЭКРАН 1: ЛОББИ КОМНАТЫ =================
    def _build_lobby_screen(self):
        page = QWidget()
        main = QVBoxLayout(page)
        main.setContentsMargins(24, 20, 24, 20)
        main.setSpacing(16)

        header = QHBoxLayout()
        self.profile_lbl = QLabel("Профиль")
        self.profile_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #d4a33d;")
        header.addWidget(self.profile_lbl)
        header.addStretch()
        main.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(18)

        # Левая колонка: комната и участники
        left_card = QFrame()
        left_card.setObjectName("Card")
        left_card.setFixedWidth(320)
        l_lay = QVBoxLayout(left_card)
        l_lay.setContentsMargins(18, 18, 18, 18)
        l_lay.setSpacing(12)

        step1_lbl = QLabel("1. Подключение к комнате")
        step1_lbl.setStyleSheet("font-weight: bold; font-size: 15px; background: transparent;")
        l_lay.addWidget(step1_lbl)

        self.room_input = QLineEdit(placeholderText="Код комнаты (например: 123)")
        self.join_room_btn = QPushButton("Войти в комнату")
        self.join_room_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.join_room()))

        self.members_lbl = QLabel("Участники комнаты:\n— пока не подключены —")
        self.members_lbl.setWordWrap(True)
        self.members_lbl.setStyleSheet("color: #b5b5bb; background: transparent; padding-top: 8px;")

        l_lay.addWidget(self.room_input)
        l_lay.addWidget(self.join_room_btn)
        l_lay.addWidget(self.members_lbl)
        l_lay.addStretch()

        # Правая колонка: выбор жанров
        right_card = QFrame()
        right_card.setObjectName("Card")
        r_lay = QVBoxLayout(right_card)
        r_lay.setContentsMargins(20, 18, 20, 18)
        r_lay.setSpacing(14)

        step2_lbl = QLabel("2. Выберите жанры на вечер")
        step2_lbl.setStyleSheet("font-weight: bold; font-size: 15px; background: transparent;")
        hint_lbl = QLabel("Если ничего не отмечать, сервер автоматически возьмет любимые жанры из ваших профилей.")
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet("color: #9e9ea4; background: transparent;")

        r_lay.addWidget(step2_lbl)
        r_lay.addWidget(hint_lbl)

        g_grid = QGridLayout()
        g_grid.setVerticalSpacing(14)
        g_grid.setHorizontalSpacing(20)
        self.lobby_genre_checks: list[QCheckBox] = []
        for idx, genre in enumerate(AVAILABLE_GENRES):
            cb = QCheckBox(genre)
            cb.setStyleSheet("font-size: 15px; background: transparent;")
            self.lobby_genre_checks.append(cb)
            g_grid.addWidget(cb, idx // 2, idx % 2)
        r_lay.addLayout(g_grid)
        r_lay.addStretch()

        btns_row = QHBoxLayout()
        self.ready_btn = QPushButton("Подтвердить жанры (Готов)")
        self.ready_btn.setEnabled(False)
        self.ready_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.submit_prefs()))

        self.start_btn = QPushButton("Начать выбор фильмов")
        self.start_btn.setObjectName("PrimaryBtn")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.start_session()))

        btns_row.addWidget(self.ready_btn)
        btns_row.addWidget(self.start_btn)
        r_lay.addLayout(btns_row)

        self.lobby_status_lbl = QLabel("")
        self.lobby_status_lbl.setStyleSheet("color: #d4a33d; background: transparent;")
        r_lay.addWidget(self.lobby_status_lbl)

        body.addWidget(left_card)
        body.addWidget(right_card, stretch=1)
        main.addLayout(body)
        self.stack.addWidget(page)

    # ================= ЭКРАН 2: КАРТОЧКА ФИЛЬМА + ОПИСАНИЕ + ОТЗЫВЫ =================
    def _build_swipe_screen(self):
        page = QWidget()
        main = QVBoxLayout(page)
        main.setContentsMargins(20, 16, 20, 16)
        main.setSpacing(12)

        top_bar = QHBoxLayout()
        self.swipe_room_lbl = QLabel("Комната")
        self.swipe_room_lbl.setStyleSheet("font-weight: bold; color: #d4a33d;")
        self.activity_lbl = QLabel("")
        self.activity_lbl.setStyleSheet("color: #9e9ea4;")
        hist_btn = QPushButton("История мэтчей")
        hist_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.request_history()))
        back_lobby_btn = QPushButton("В лобби")
        back_lobby_btn.clicked.connect(lambda checked=False: self.stack.setCurrentIndex(1))

        top_bar.addWidget(self.swipe_room_lbl)
        top_bar.addSpacing(12)
        top_bar.addWidget(self.activity_lbl)
        top_bar.addStretch()
        top_bar.addWidget(hist_btn)
        top_bar.addWidget(back_lobby_btn)
        main.addLayout(top_bar)

        content = QHBoxLayout()
        content.setSpacing(20)

        # Левая панель: постер и кнопки
        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        self.poster_label = QLabel("Загрузка...")
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setFixedSize(290, 430)
        self.poster_label.setStyleSheet("background-color: #2b2b2b; border-radius: 14px;")
        self.poster_label.setScaledContents(True)

        self.like_btn = QPushButton("Лайк (Match)")
        self.like_btn.setObjectName("LikeBtn")
        self.like_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.vote("like")))

        self.skip_btn = QPushButton("Скип")
        self.skip_btn.setObjectName("SkipBtn")
        self.skip_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.vote("skip")))

        left_col.addWidget(self.poster_label)
        left_col.addWidget(self.like_btn)
        left_col.addWidget(self.skip_btn)
        left_col.addStretch()

        # Правая панель: описание и отзывы в ScrollArea
        right_card = QFrame()
        right_card.setObjectName("Card")
        right_outer = QVBoxLayout(right_card)
        right_outer.setContentsMargins(18, 18, 18, 18)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        info_container = QWidget()
        info_container.setStyleSheet("background: transparent;")
        self.info_layout = QVBoxLayout(info_container)
        self.info_layout.setSpacing(12)

        self.movie_title_lbl = QLabel("Название фильма")
        self.movie_title_lbl.setWordWrap(True)
        self.movie_title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")

        self.movie_meta_lbl = QLabel("Жанр | Год | Рейтинг")
        self.movie_meta_lbl.setStyleSheet("font-size: 14px; color: #d4a33d; font-weight: bold;")

        desc_header = QLabel("Описание")
        desc_header.setStyleSheet("font-size: 15px; font-weight: bold; color: #cccccc; margin-top: 6px;")

        self.movie_desc_lbl = QLabel("")
        self.movie_desc_lbl.setWordWrap(True)
        self.movie_desc_lbl.setStyleSheet("color: #e5e5ea; line-height: 1.4;")

        rev_header = QLabel("Отзывы зрителей")
        rev_header.setStyleSheet("font-size: 15px; font-weight: bold; color: #cccccc; margin-top: 10px;")

        self.reviews_container = QVBoxLayout()
        self.reviews_container.setSpacing(10)

        self.info_layout.addWidget(self.movie_title_lbl)
        self.info_layout.addWidget(self.movie_meta_lbl)
        self.info_layout.addWidget(desc_header)
        self.info_layout.addWidget(self.movie_desc_lbl)
        self.info_layout.addWidget(rev_header)
        self.info_layout.addLayout(self.reviews_container)
        self.info_layout.addStretch()

        scroll.setWidget(info_container)
        right_outer.addWidget(scroll)

        content.addLayout(left_col)
        content.addWidget(right_card, stretch=1)
        main.addLayout(content)
        self.stack.addWidget(page)

    # ================= ЭКРАН 3: МЭТЧ, ТРЕЙЛЕР И ГДЕ ПОСМОТРЕТЬ =================
    def _build_match_screen(self):
        page = QWidget()
        main = QVBoxLayout(page)
        main.setContentsMargins(22, 18, 22, 18)
        main.setSpacing(14)

        top = QHBoxLayout()
        self.match_header_lbl = QLabel("МЭТЧ!")
        self.match_header_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #d4a33d;")
        back_btn = QPushButton("Искать еще")
        back_btn.clicked.connect(lambda checked=False: self.stack.setCurrentIndex(2))
        top.addWidget(self.match_header_lbl)
        top.addStretch()
        top.addWidget(back_btn)
        main.addLayout(top)

        if HAS_WEBENGINE:
            self.player = QWebEngineView()
            self.player.setMinimumHeight(390)
            main.addWidget(self.player, stretch=1)
        else:
            self.player = None
            fallback_lbl = QLabel(
                "Модуль PyQt6-WebEngine не установлен — установите его командой `pip install PyQt6-WebEngine`,\n"
                "или откройте трейлер в браузере кнопкой ниже."
            )
            fallback_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback_lbl.setStyleSheet("background-color: #262628; border-radius: 12px; padding: 30px;")
            main.addWidget(fallback_lbl, stretch=1)

        # Панель синхронизации WatchParty
        sync_row = QHBoxLayout()
        play_btn = QPushButton("▶ Play для всей комнаты")
        play_btn.setObjectName("PrimaryBtn")
        play_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.send_player_sync("play")))

        pause_btn = QPushButton("⏸ Pause для всей комнаты")
        pause_btn.clicked.connect(lambda checked=False: asyncio.ensure_future(self.send_player_sync("pause")))

        open_yt_btn = QPushButton("Открыть трейлер в браузере")
        open_yt_btn.clicked.connect(self.open_trailer_external)

        self.sync_status_lbl = QLabel("")
        self.sync_status_lbl.setStyleSheet("color: #9e9ea4;")

        sync_row.addWidget(play_btn)
        sync_row.addWidget(pause_btn)
        sync_row.addWidget(open_yt_btn)
        sync_row.addStretch()
        sync_row.addWidget(self.sync_status_lbl)
        main.addLayout(sync_row)

        # Блок "Где посмотреть"
        watch_card = QFrame()
        watch_card.setObjectName("Card")
        w_lay = QVBoxLayout(watch_card)
        w_lay.setContentsMargins(16, 12, 16, 12)
        w_title = QLabel("Где посмотреть фильм полностью:")
        w_title.setStyleSheet("font-weight: bold; color: #cccccc; background: transparent;")
        w_lay.addWidget(w_title)

        self.watch_links_row = QHBoxLayout()
        self.watch_links_row.setSpacing(10)
        w_lay.addLayout(self.watch_links_row)
        main.addWidget(watch_card)

        self.stack.addWidget(page)

    # ================= СЕТЕВАЯ ЛОГИКА =================
    async def ensure_connected(self) -> bool:
        if self.ws is not None:
            return True
        try:
            self.ws = await websockets.connect(SERVER_URL)
            self.listen_task = asyncio.create_task(self.listen_server())
            return True
        except Exception as e:
            self.auth_status_lbl.setText(f"Не удалось подключиться к серверу: {e}")
            return False

    async def send_json(self, payload: dict):
        if await self.ensure_connected():
            await self.ws.send(json.dumps(payload, ensure_ascii=False))

    async def do_login(self):
        self.auth_status_lbl.setText("")
        await self.send_json({
            "action": "login",
            "username": self.login_user_input.text(),
            "password": self.login_pass_input.text(),
        })

    async def do_register(self):
        self.auth_status_lbl.setText("")
        fav_genres = [cb.text() for cb in self.reg_genre_checks if cb.isChecked()]
        await self.send_json({
            "action": "register",
            "username": self.reg_user_input.text(),
            "password": self.reg_pass_input.text(),
            "fav_genres": fav_genres,
            "fav_movies": self.reg_fav_movies_input.text(),
        })

    async def join_room(self):
        room = self.room_input.text().strip()
        if not room:
            return
        self.current_room = room
        await self.send_json({"action": "join_room", "room": room})
        self.ready_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.lobby_status_lbl.setText(f"Вы в комнате {room}. Выберите жанры и нажмите «Начать выбор фильмов».")

    def _get_selected_genres(self) -> list[str]:
        return [cb.text() for cb in self.lobby_genre_checks if cb.isChecked()]

    async def submit_prefs(self):
        await self.send_json({
            "action": "submit_prefs",
            "genres": self._get_selected_genres(),
        })
        self.lobby_status_lbl.setText("Жанры подтверждены! Ждем остальных или жмите «Начать выбор фильмов».")

    async def start_session(self):
        await self.send_json({
            "action": "start_session",
            "genres": self._get_selected_genres(),
        })

    async def vote(self, vote_type: str):
        if self.current_index >= len(self.movies):
            return
        movie = self.movies[self.current_index]
        await self.send_json({
            "action": "vote",
            "movie": movie["title"],
            "vote": vote_type,
        })
        self.current_index += 1
        await self.show_current_movie()

    async def request_history(self):
        await self.send_json({"action": "get_history"})

    # ================= ОТРИСОВКА КАРТОЧЕК И ТРЕЙЛЕРА =================
    async def load_poster(self, url: str):
        if not url:
            self.poster_label.setText("Нет постера")
            return
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        try:
            async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        pixmap = QPixmap()
                        pixmap.loadFromData(data)
                        self.poster_label.setPixmap(pixmap)
                    else:
                        self.poster_label.setText(f"Постер недоступен ({resp.status})")
        except Exception:
            self.poster_label.setText("Не удалось загрузить постер")

    async def show_current_movie(self):
        while self.reviews_container.count():
            item = self.reviews_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.current_index >= len(self.movies):
            self.movie_title_lbl.setText("Подборка закончилась!")
            self.movie_meta_lbl.setText("Вернитесь в лобби, чтобы выбрать другие жанры.")
            self.movie_desc_lbl.setText("")
            self.poster_label.clear()
            self.poster_label.setText("Фильмы закончились")
            self.like_btn.setEnabled(False)
            self.skip_btn.setEnabled(False)
            return

        movie = self.movies[self.current_index]
        self.like_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)

        self.movie_title_lbl.setText(movie["title"])
        self.movie_meta_lbl.setText(
            f"{movie.get('genre', '')}  •  {movie.get('year', '')}  •  Рейтинг: {movie.get('rating', '-')}"
        )
        self.movie_desc_lbl.setText(movie.get("description", "Описание отсутствует."))

        for rev in movie.get("reviews", []):
            card = QFrame()
            card.setObjectName("ReviewCard")
            rev_type = rev.get("type", "NEUTRAL")
            border_color = "#4caf50" if rev_type == "POSITIVE" else ("#e06c75" if rev_type == "NEGATIVE" else "#8e8e93")
            card.setStyleSheet(
                f"QFrame#ReviewCard {{ background-color: #2c2c2e; border-left: 4px solid {border_color}; border-radius: 8px; }}"
            )
            r_lay = QVBoxLayout(card)
            r_lay.setContentsMargins(10, 8, 10, 8)
            author_lbl = QLabel(rev.get("author", "Зритель"))
            author_lbl.setStyleSheet("font-weight: bold; color: #d4a33d; background: transparent;")
            text_lbl = QLabel(rev.get("text", ""))
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet("color: #dcdce0; background: transparent;")
            r_lay.addWidget(author_lbl)
            r_lay.addWidget(text_lbl)
            self.reviews_container.addWidget(card)

        await self.load_poster(movie.get("poster", ""))

    def open_match_screen(self, movie: dict):
        self.matched_movie = movie
        self.match_header_lbl.setText(f"МЭТЧ! Смотрим: {movie['title']} ({movie.get('year', '')})")
        self.sync_status_lbl.setText("Трейлер загружен")

        if self.player is not None:
            trailer_id = movie.get("trailer_id", "")
            if trailer_id:
                html = f"""
                <!DOCTYPE html>
                <html>
                <body style="margin:0; background:#000; overflow:hidden;">
                    <iframe id="ytplayer" width="100%" height="100%" style="position:fixed; inset:0; border:0;"
                        src="https://www.youtube.com/embed/{trailer_id}?enablejsapi=1&rel=0"
                        allow="autoplay; encrypted-media" allowfullscreen>
                    </iframe>
                    <script>
                        function controlVideo(funcName) {{
                            var iframe = document.getElementById('ytplayer');
                            if (iframe && iframe.contentWindow) {{
                                iframe.contentWindow.postMessage(
                                    JSON.stringify({{"event": "command", "func": funcName, "args": []}}),
                                    "*"
                                );
                            }}
                        }}
                    </script>
                </body>
                </html>
                """
                self.player.setHtml(html, QUrl("https://www.youtube.com"))
            else:
                self.player.setHtml(
                    "<body style='background:#1e1e1e;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;'>"
                    "Трейлер не найден — откройте поиск в браузере кнопкой ниже.</body>"
                )

        while self.watch_links_row.count():
            item = self.watch_links_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for link in movie.get("watch_links", []):
            btn = QPushButton(f"Смотреть на {link['name']}")
            btn.clicked.connect(lambda checked=False, url=link["url"]: QDesktopServices.openUrl(QUrl(url)))
            self.watch_links_row.addWidget(btn)
        self.watch_links_row.addStretch()

        self.stack.setCurrentIndex(3)

    def _exec_player_state(self, state: str):
        if self.player is not None:
            js_func = "playVideo" if state == "play" else "pauseVideo"
            self.player.page().runJavaScript(f"controlVideo('{js_func}');")

    async def send_player_sync(self, state: str):
        self._exec_player_state(state)
        self.sync_status_lbl.setText("Вы нажали Play" if state == "play" else "Вы нажали Pause")
        await self.send_json({"action": "player_sync", "state": state})

    def open_trailer_external(self):
        if self.matched_movie:
            url = self.matched_movie.get("trailer_watch_url", "")
            if url:
                QDesktopServices.openUrl(QUrl(url))

    # ================= СЛУШАТЕЛЬ СЕРВЕРА =================
    async def listen_server(self):
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                action = data.get("action")

                if action == "auth_ok":
                    self.current_user = data["user"]
                    favs = ", ".join(self.current_user.get("fav_genres", [])) or "не выбраны"
                    self.profile_lbl.setText(
                        f"Пользователь: {self.current_user['username']}  |  Любимые жанры: {favs}"
                    )
                    for cb in self.lobby_genre_checks:
                        cb.setChecked(cb.text() in self.current_user.get("fav_genres", []))
                    self.stack.setCurrentIndex(1)

                elif action == "auth_error":
                    self.auth_status_lbl.setText(data.get("message", "Ошибка входа"))

                elif action == "room_state":
                    lines = [f"Участники комнаты {data['room']}:"]
                    for m in data.get("members", []):
                        mark = "Готов" if m["ready"] else "выбирает..."
                        g_note = f" ({', '.join(m['genres'])})" if m.get("genres") else ""
                        lines.append(f"• {m['username']} — {mark}{g_note}")
                    self.members_lbl.setText("\n".join(lines))

                elif action == "loading_deck":
                    self.lobby_status_lbl.setText("Загружаем фильмы с Кинопоиска...")

                elif action == "deck_ready":
                    self.movies = data.get("movies", [])
                    self.current_index = 0
                    self.swipe_room_lbl.setText(f"Комната: {self.current_room}")
                    self.activity_lbl.setText(f"Загружено фильмов: {len(self.movies)}")
                    self.stack.setCurrentIndex(2)
                    await self.show_current_movie()

                elif action == "vote_update":
                    vote_ru = "лайкнул(а)" if data["vote"] == "like" else "пропустил(а)"
                    self.activity_lbl.setText(f"{data['user']} {vote_ru} «{data['movie']}»")

                elif action == "match":
                    self.open_match_screen(data["movie"])

                elif action == "sync_video":
                    state = data.get("state")
                    self._exec_player_state(state)
                    sender = data.get("sender", "Участник")
                    self.sync_status_lbl.setText(f"{sender} нажал(а) {state.upper()}")

                elif action == "history_data":
                    matches = data.get("matches", [])
                    if not matches:
                        text = "В этой комнате пока не было мэтчей."
                    else:
                        text = "\n".join(f"• {m['title']} ({m['year']}) — {m['timestamp']}" for m in matches)
                    QMessageBox.information(self, "История мэтчей комнаты", text)

        except websockets.ConnectionClosed:
            self.ws = None


def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = CineSyncClient()
    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()