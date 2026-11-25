import asyncio
import json
import websockets

from database import (
    init_db,
    register_user,
    login_user,
    log_room,
    save_match,
    log_watch_session,
    get_room_matches,
)
from api_parser import fetch_movies_by_genres

# websocket -> {"username": str, "fav_genres": list, "fav_movies": str, "room": str | None}
clients: dict = {}

# room_code -> состояние комнаты
rooms: dict[str, dict] = {}


async def safe_send(ws, payload: dict):
    try:
        await ws.send(json.dumps(payload, ensure_ascii=False))
    except websockets.ConnectionClosed:
        pass


async def broadcast_room(room_code: str, payload: dict, exclude=None):
    room = rooms.get(room_code)
    if not room:
        return
    for member_ws in list(room["members"]):
        if member_ws != exclude:
            await safe_send(member_ws, payload)


async def broadcast_room_state(room_code: str):
    room = rooms.get(room_code)
    if not room:
        return
    members_info = []
    for ws in room["members"]:
        info = clients.get(ws)
        if info:
            uname = info["username"]
            members_info.append({
                "username": uname,
                "ready": uname in room["ready"],
                "genres": room["genres"].get(uname, []),
            })
    await broadcast_room(room_code, {
        "action": "room_state",
        "room": room_code,
        "members": members_info,
    })


async def handler(websocket):
    try:
        async for raw_message in websocket:
            data = json.loads(raw_message)
            action = data.get("action")

            # --- 1. РЕГИСТРАЦИЯ ---
            if action == "register":
                ok, result = await register_user(
                    data.get("username", ""),
                    data.get("password", ""),
                    data.get("fav_genres", []),
                    data.get("fav_movies", ""),
                )
                if ok:
                    clients[websocket] = {**result, "room": None}
                    await safe_send(websocket, {"action": "auth_ok", "user": result})
                else:
                    await safe_send(websocket, {"action": "auth_error", "message": result})

            # --- 2. ВХОД ---
            elif action == "login":
                ok, result = await login_user(data.get("username", ""), data.get("password", ""))
                if ok:
                    clients[websocket] = {**result, "room": None}
                    await safe_send(websocket, {"action": "auth_ok", "user": result})
                else:
                    await safe_send(websocket, {"action": "auth_error", "message": result})

            # --- 3. ВХОД В КОМНАТУ ---
            elif action == "join_room":
                user_info = clients.get(websocket)
                if not user_info:
                    continue
                room_code = data.get("room", "").strip()
                if not room_code:
                    continue

                old_room = user_info.get("room")
                if old_room and old_room in rooms:
                    rooms[old_room]["members"].discard(websocket)
                    await broadcast_room_state(old_room)

                if room_code not in rooms:
                    rooms[room_code] = {
                        "members": set(),
                        "genres": {},
                        "ready": set(),
                        "deck": [],
                        "likes": {},
                    }

                rooms[room_code]["members"].add(websocket)
                user_info["room"] = room_code
                print(f"[Сервер] {user_info['username']} вошел в комнату {room_code}")
                await broadcast_room_state(room_code)

            # --- 4. ОТПРАВКА ВЫБРАННЫХ ЖАНРОВ / ГОТОВНОСТИ ---
            elif action == "submit_prefs":
                user_info = clients.get(websocket)
                if not user_info or not user_info.get("room"):
                    continue
                room_code = user_info["room"]
                room = rooms[room_code]
                uname = user_info["username"]

                room["genres"][uname] = data.get("genres", [])
                room["ready"].add(uname)
                await broadcast_room_state(room_code)

            # --- 5. ЗАПУСК ПОДБОРА ФИЛЬМОВ ПО ЖАНРАМ ---
            elif action == "start_session":
                user_info = clients.get(websocket)
                if not user_info or not user_info.get("room"):
                    continue
                room_code = user_info["room"]
                room = rooms[room_code]
                uname = user_info["username"]

                if data.get("genres"):
                    room["genres"][uname] = data.get("genres", [])

                await broadcast_room(room_code, {"action": "loading_deck"})
                await log_room(room_code, "genres")

                merged_genres = set()
                for g_list in room["genres"].values():
                    merged_genres.update(g_list)

                # Если никто не отметил жанры в лобби — берем любимые жанры из профилей
                if not merged_genres:
                    for ws in room["members"]:
                        if ws in clients:
                            merged_genres.update(clients[ws].get("fav_genres", []))

                deck = await fetch_movies_by_genres(list(merged_genres))
                room["deck"] = deck
                room["likes"] = {}
                room["ready"].clear()

                print(f"[Сервер] Комната {room_code}: выдано {len(deck)} фильмов (жанры: {list(merged_genres)}).")
                await broadcast_room(room_code, {"action": "deck_ready", "movies": deck})

            # --- 6. ГОЛОСОВАНИЕ И ПРОВЕРКА МЭТЧА НА ВСЕХ УЧАСТНИКОВ ---
            elif action == "vote":
                user_info = clients.get(websocket)
                if not user_info or not user_info.get("room"):
                    continue
                room_code = user_info["room"]
                room = rooms.get(room_code)
                if not room:
                    continue

                uname = user_info["username"]
                movie_title = data.get("movie")
                vote = data.get("vote")
                print(f"[Сервер] [{room_code}] {uname}: {movie_title} -> {vote}")

                if vote == "like":
                    room["likes"].setdefault(movie_title, set()).add(uname)
                    total_members = len(room["members"])
                    likes_count = len(room["likes"][movie_title])

                    if likes_count >= total_members:
                        matched_movie = next(
                            (m for m in room["deck"] if m["title"] == movie_title),
                            {"title": movie_title},
                        )
                        print(f"[Сервер] МЭТЧ в комнате {room_code}: {movie_title} ({likes_count}/{total_members})")
                        await save_match(room_code, movie_title, matched_movie.get("year", 0))
                        await log_watch_session(room_code, movie_title)
                        await broadcast_room(room_code, {"action": "match", "movie": matched_movie})

                await broadcast_room(
                    room_code,
                    {"action": "vote_update", "user": uname, "movie": movie_title, "vote": vote},
                    exclude=websocket,
                )

            # --- 7. СИНХРОНИЗАЦИЯ ТРЕЙЛЕРА (WATCHPARTY) ---
            elif action == "player_sync":
                user_info = clients.get(websocket)
                if not user_info or not user_info.get("room"):
                    continue
                room_code = user_info["room"]
                state = data.get("state")
                print(f"[Сервер] [{room_code}] Плеер -> {state} (от {user_info['username']})")
                await broadcast_room(
                    room_code,
                    {"action": "sync_video", "state": state, "sender": user_info["username"]},
                    exclude=websocket,
                )

            # --- 8. ИСТОРИЯ МЭТЧЕЙ КОМНАТЫ ---
            elif action == "get_history":
                user_info = clients.get(websocket)
                if not user_info or not user_info.get("room"):
                    continue
                matches = await get_room_matches(user_info["room"])
                await safe_send(websocket, {"action": "history_data", "matches": matches})

    except websockets.ConnectionClosed:
        pass
    finally:
        user_info = clients.pop(websocket, None)
        if user_info and user_info.get("room"):
            room_code = user_info["room"]
            room = rooms.get(room_code)
            if room:
                room["members"].discard(websocket)
                room["ready"].discard(user_info["username"])
                if not room["members"]:
                    del rooms[room_code]
                    print(f"[Сервер] Комната {room_code} закрыта.")
                else:
                    await broadcast_room_state(room_code)


async def main():
    await init_db()
    print("[Сервер] CineSync запущен на ws://127.0.0.1:8765")
    async with websockets.serve(handler, "127.0.0.1", 8765):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())