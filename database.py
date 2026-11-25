import json
import os
import hashlib
import aiosqlite

DB_PATH = "cinesync.db"


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return pwd_hash.hex(), salt.hex()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                fav_genres TEXT DEFAULT '[]',
                fav_movies TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT NOT NULL,
                mode TEXT DEFAULT 'genres',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT NOT NULL,
                movie_title TEXT NOT NULL,
                movie_year INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS watch_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT NOT NULL,
                movie_title TEXT NOT NULL,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'watching'
            )
        """)
        await db.commit()
    print("[БД] Таблицы инициализированы.")


async def register_user(username: str, password: str, fav_genres: list, fav_movies: str) -> tuple[bool, dict | str]:
    username = username.strip()
    if len(username) < 2 or len(password) < 4:
        return False, "Логин от 2 символов, пароль от 4 символов."

    pwd_hash, salt_hex = _hash_password(password)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO users (username, password_hash, salt, fav_genres, fav_movies)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, pwd_hash, salt_hex, json.dumps(fav_genres, ensure_ascii=False), fav_movies.strip()),
            )
            await db.commit()
        return True, {
            "username": username,
            "fav_genres": fav_genres,
            "fav_movies": fav_movies.strip(),
        }
    except aiosqlite.IntegrityError:
        return False, "Пользователь с таким логином уже существует."


async def login_user(username: str, password: str) -> tuple[bool, dict | str]:
    username = username.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT username, password_hash, salt, fav_genres, fav_movies FROM users WHERE username = ?",
            (username,),
        )
        row = await cursor.fetchone()

    if not row:
        return False, "Пользователь не найден."

    db_username, db_hash, salt_hex, fav_genres_raw, fav_movies = row
    check_hash, _ = _hash_password(password, bytes.fromhex(salt_hex))
    if check_hash != db_hash:
        return False, "Неверный пароль."

    return True, {
        "username": db_username,
        "fav_genres": json.loads(fav_genres_raw or "[]"),
        "fav_movies": fav_movies or "",
    }


async def log_room(room_code: str, mode: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO rooms (room_code, mode) VALUES (?, ?)", (room_code, mode))
        await db.commit()


async def save_match(room_code: str, movie_title: str, movie_year: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO matches (room_code, movie_title, movie_year) VALUES (?, ?, ?)",
            (room_code, movie_title, movie_year),
        )
        await db.commit()
    print(f"[БД] Сохранен мэтч: {movie_title} в комнате {room_code}")


async def log_watch_session(room_code: str, movie_title: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO watch_sessions (room_code, movie_title, status) VALUES (?, ?, 'watching')",
            (room_code, movie_title),
        )
        await db.commit()


async def get_room_matches(room_code: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT movie_title, movie_year, timestamp FROM matches WHERE room_code = ? ORDER BY id DESC LIMIT 20",
            (room_code,),
        )
        rows = await cursor.fetchall()
    return [{"title": r[0], "year": r[1], "timestamp": r[2]} for r in rows]