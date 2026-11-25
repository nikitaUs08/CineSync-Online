import os
import re
import asyncio
import urllib.parse
import aiohttp

# Ключ от @kinopoiskdev_bot (задается через Environment Variables в PyCharm или прямо здесь для теста)
KP_API_KEY = os.getenv("KP_API_KEY", "GK11WEQ-Z5B40W5-P7FTSQR-7VJ1JQ0")
KP_DEV_BASE = "https://api.kinopoisk.dev/v1.4"

# В Kinopoisk.dev жанры передаются строками в нижнем регистре
GENRE_TO_KP_DEV = {
    "Хоррор": "ужасы",
    "Фантастика": "фантастика",
    "Триллер": "триллер",
    "Детектив": "детектив",
    "Комедия": "комедия",
    "Драма": "драма",
    "Боевик": "боевик",
    "Мультфильмы": "мультфильм",
}

REVIEW_TYPE_MAP = {
    "Позитивный": "POSITIVE",
    "Негативный": "NEGATIVE",
    "Нейтральный": "NEUTRAL",
}


def build_watch_links(title: str, kp_id: int | None = None) -> list[dict]:
    q = urllib.parse.quote(title)
    kp_url = f"https://www.kinopoisk.ru/film/{kp_id}/" if kp_id else f"https://www.kinopoisk.ru/index.php?kp_query={q}"
    return [
        {"name": "Кинопоиск", "url": kp_url},
        {"name": "Okko", "url": f"https://okko.tv/search/{q}"},
        {"name": "Иви", "url": f"https://www.ivi.ru/search/?q={q}"},
    ]


def _extract_youtube_id(url: str) -> str:
    if not url:
        return ""
    patterns = [
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


FALLBACK_MOVIES = [
    {
        "title": "Синистер",
        "year": 2012,
        "genres": ["Хоррор", "Детектив", "Триллер"],
        "rating": 6.8,
        "poster": "https://placehold.co/300x450/1c1c1e/d4a33d/png?text=Sinister%0A2012",
        "description": "Автор детективов переезжает с семьей в дом, где год назад произошло загадочное убийство. На чердаке он находит коробку со старыми кинопленками, которые оказываются ключом к древнему проклятию.",
        "trailer_id": "_kbQAJR9YWQ",
        "reviews": [
            {"author": "Алексей К.", "type": "POSITIVE", "text": "Один из самых жутких саундтреков в истории жанра. Сцены с пленками реально держат в напряжении до титров."},
            {"author": "Марина", "type": "NEUTRAL", "text": "Атмосфера на высоте, но ближе к финалу чуть перегнули со скримерами."},
        ],
    },
    {
        "title": "Реинкарнация",
        "year": 2018,
        "genres": ["Хоррор", "Драма", "Детектив"],
        "rating": 7.3,
        "poster": "https://placehold.co/300x450/241b1b/e0b84c/png?text=Hereditary%0A2018",
        "description": "После смерти матери в семье Энни начинают происходить необъяснимые и пугающие события. Постепенно наружу выходят мрачные семейные тайны, от которых невозможно сбежать.",
        "trailer_id": "V6wWKNij_1M",
        "reviews": [
            {"author": "Дмитрий", "type": "POSITIVE", "text": "Гениальная игра Тони Коллетт и давящая атмосфера без дешевых приемов. Настоящий психологический ужас."},
            {"author": "Кинокритик_99", "type": "POSITIVE", "text": "Фильм, который хочется пересматривать ради скрытых деталей на заднем плане."},
        ],
    },
    {
        "title": "Интерстеллар",
        "year": 2014,
        "genres": ["Фантастика", "Драма"],
        "rating": 8.6,
        "poster": "https://placehold.co/300x450/101824/d4a33d/png?text=Interstellar%0A2014",
        "description": "Когда засуха и пыльные бури приводят человечество к продовольственному кризису, группа исследователей отправляется сквозь червоточину в космос в поисках новой планеты для жизни.",
        "trailer_id": "zSWdZVtXT7E",
        "reviews": [
            {"author": "Сергей", "type": "POSITIVE", "text": "Музыка Ханса Циммера и визуал черной дыры — абсолютный восторг. Смотреть строго с хорошим звуком."},
            {"author": "Ольга", "type": "POSITIVE", "text": "Редкий случай, когда научная фантастика пробивает на сильные эмоции."},
        ],
    },
    {
        "title": "Начало",
        "year": 2010,
        "genres": ["Фантастика", "Боевик", "Триллер"],
        "rating": 8.7,
        "poster": "https://placehold.co/300x450/1b222c/ffffff/png?text=Inception%0A2010",
        "description": "Кобб — талантливый вор, лучший в опасном искусстве извлечения секретов из глубин подсознания во время сна. Но в этот раз ему предстоит не украсть идею, а внедрить ее.",
        "trailer_id": "YoHD9XEInc0",
        "reviews": [
            {"author": "Макс", "type": "POSITIVE", "text": "Многослойный сюжет, который не отпускает ни на секунду. Финал обсуждают до сих пор."},
            {"author": "Аня", "type": "NEUTRAL", "text": "Очень круто снято, но если отвлечься на 5 минут — легко потерять нить сна."},
        ],
    },
    {
        "title": "Остров проклятых",
        "year": 2010,
        "genres": ["Триллер", "Детектив", "Драма"],
        "rating": 8.5,
        "poster": "https://placehold.co/300x450/1d2428/d4a33d/png?text=Shutter+Island%0A2010",
        "description": "Два судебных пристава прибывают на изолированный остров, чтобы расследовать исчезновение пациентки клиники для умалишенных преступников. Ураган отрезает их от большой земли.",
        "trailer_id": "5iaYLCiq5RM",
        "reviews": [
            {"author": "Илья", "type": "POSITIVE", "text": "Один из лучших сюжетных поворотов в кино. Второй просмотр ощущается как совсем другой фильм."},
            {"author": "Вера", "type": "POSITIVE", "text": "ДиКаприо здесь невероятен, атмосфера тревоги чувствуется физически."},
        ],
    },
    {
        "title": "Достать ножи",
        "year": 2019,
        "genres": ["Детектив", "Комедия", "Драма"],
        "rating": 8.1,
        "poster": "https://placehold.co/300x450/2b211a/d4a33d/png?text=Knives+Out%0A2019",
        "description": "На следующее утро после 85-летия известного автора криминальных романов его находят мертвым в особняке. За дело берется харизматичный детектив Бенуа Блан, а под подозрением вся эксцентричная семья.",
        "trailer_id": "qGqiHJTsRkQ",
        "reviews": [
            {"author": "Роман", "type": "POSITIVE", "text": "Идеальный фильм для компании: остроумный, динамичный и с шикарным актерским составом."},
            {"author": "Лена", "type": "POSITIVE", "text": "Уютный особняк, отличный юмор и детектив в лучших традициях Агаты Кристи."},
        ],
    },
    {
        "title": "Паразиты",
        "year": 2019,
        "genres": ["Триллер", "Драма", "Комедия"],
        "rating": 8.0,
        "poster": "https://placehold.co/300x450/1f261e/e0b84c/png?text=Parasite%0A2019",
        "description": "Обычная небогатая семья хитростью постепенно устраивается на работу в роскошный дом состоятельного бизнесмена. Но вскоре они узнают, что у дома есть собственный жуткий секрет.",
        "trailer_id": "5xH0HfJHsaY",
        "reviews": [
            {"author": "Тимур", "type": "POSITIVE", "text": "Начинается как черная комедия, а во второй половине превращается в безумный триллер. Заслуженный Оскар."},
            {"author": "Катя", "type": "POSITIVE", "text": "Невозможно предсказать, что произойдет в следующую минуту."},
        ],
    },
    {
        "title": "Исчезнувшая",
        "year": 2014,
        "genres": ["Триллер", "Детектив", "Драма"],
        "rating": 8.0,
        "poster": "https://placehold.co/300x450/1e2229/cccccc/png?text=Gone+Girl%0A2014",
        "description": "В день пятой годовщины свадьбы бесследно исчезает жена главного героя. Все улики и дневник пропавшей начинают указывать на самого мужа.",
        "trailer_id": "2-_-1nJf8Vg",
        "reviews": [
            {"author": "Артем", "type": "POSITIVE", "text": "Финчер мастерски играет со зрителем. Постоянно меняешь мнение о героях."},
            {"author": "Юля", "type": "POSITIVE", "text": "Очень умный, холодный и цепляющий триллер."},
        ],
    },
    {
        "title": "Дюна",
        "year": 2021,
        "genres": ["Фантастика", "Боевик", "Драма"],
        "rating": 7.7,
        "poster": "https://placehold.co/300x450/302418/d4a33d/png?text=Dune%0A2021",
        "description": "Наследник знаменитого дома Атрейдесов отправляется на самую опасную пустынную планету Арракис, где добывают ценнейший ресурс во Вселенной — пряность.",
        "trailer_id": "8g18jFHCLXk",
        "reviews": [
            {"author": "Влад", "type": "POSITIVE", "text": "Масштаб, звук и операторская работа — просто космос. Погружение стопроцентное."},
            {"author": "Игорь", "type": "NEUTRAL", "text": "Очень красиво, но темп неспешный — скорее как огромная завязка ко второй части."},
        ],
    },
    {
        "title": "Темный рыцарь",
        "year": 2008,
        "genres": ["Боевик", "Триллер", "Драма"],
        "rating": 8.5,
        "poster": "https://placehold.co/300x450/16181c/d4a33d/png?text=The+Dark+Knight%0A2008",
        "description": "Бэтмен поднимает ставки в войне с преступностью, но на арену выходит криминальный гений Джокер, который намерен погрузить Готэм в абсолютный хаос.",
        "trailer_id": "EXeTwQWrcwY",
        "reviews": [
            {"author": "Денис", "type": "POSITIVE", "text": "Эталонный криминальный триллер, который давно перерос жанр кинокомиксов."},
            {"author": "Павел", "type": "POSITIVE", "text": "Хит Леджер в роли Джокера — легендарный перформанс."},
        ],
    },
    {
        "title": "1+1",
        "year": 2011,
        "genres": ["Комедия", "Драма"],
        "rating": 8.8,
        "poster": "https://placehold.co/300x450/242830/e0b84c/png?text=Intouchables%0A2011",
        "description": "Парализованный богатый аристократ нанимает в помощники парня из пригорода, который совсем не подходит для этой работы, но возвращает ему вкус к жизни.",
        "trailer_id": "34WIbmXkewU",
        "reviews": [
            {"author": "Наташа", "type": "POSITIVE", "text": "Добрый, искренний и смешной фильм. Идеально поднимает настроение вечером."},
            {"author": "Егор", "type": "POSITIVE", "text": "Дуэт актеров работает безупречно, хочется пересматривать снова."},
        ],
    },
    {
        "title": "Человек-паук: Через вселенные",
        "year": 2018,
        "genres": ["Мультфильмы", "Фантастика", "Боевик", "Комедия"],
        "rating": 8.2,
        "poster": "https://placehold.co/300x450/261724/d4a33d/png?text=Spider-Verse%0A2018",
        "description": "Подросток Майлз Моралес обретает паучьи способности и узнает, что существует целая мультивселенная с другими Человеками-пауками, которым нужно объединиться.",
        "trailer_id": "g4Hbz2jLxvQ",
        "reviews": [
            {"author": "Кирилл", "type": "POSITIVE", "text": "Революция в анимации и потрясающий хип-хоп саундтрек. Каждый кадр как постер."},
            {"author": "Соня", "type": "POSITIVE", "text": "Смотрится на одном дыхании, драйвово и очень стильно."},
        ],
    },
]


def _enrich_fallback(item: dict) -> dict:
    movie = dict(item)
    movie["genre"] = ", ".join(movie["genres"])
    movie["trailer_url"] = f"https://www.youtube.com/embed/{movie['trailer_id']}?enablejsapi=1"
    movie["trailer_watch_url"] = f"https://www.youtube.com/watch?v={movie['trailer_id']}"
    movie["watch_links"] = build_watch_links(movie["title"])
    return movie


def get_all_fallback_movies() -> list[dict]:
    return [_enrich_fallback(m) for m in FALLBACK_MOVIES]


async def _fetch_reviews(session: aiohttp.ClientSession, kp_id: int, headers: dict) -> list[dict]:
    try:
        async with session.get(
            f"{KP_DEV_BASE}/review",
            headers=headers,
            params={"movieId": kp_id, "limit": 2},
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                reviews = []
                for rev in data.get("docs", []):
                    text = (rev.get("review") or "").strip()
                    text = re.sub(r"<[^>]+>", "", text)  # Убираем HTML-теги, если попадутся
                    if len(text) > 260:
                        text = text[:260] + "..."
                    if text:
                        reviews.append({
                            "author": rev.get("author") or "Зритель",
                            "type": REVIEW_TYPE_MAP.get(rev.get("type", ""), "NEUTRAL"),
                            "text": text,
                        })
                if reviews:
                    return reviews
    except Exception as e:
        print(f"[API] Не удалось загрузить отзывы для {kp_id}: {e}")

    return [{"author": "Кинопоиск", "type": "NEUTRAL", "text": "Отзывов пока немного, станьте первыми!"}]


async def _format_kp_dev_doc(session: aiohttp.ClientSession, doc: dict, headers: dict) -> dict:
    kp_id = doc.get("id")
    title = doc.get("name") or doc.get("alternativeName") or "Без названия"
    year = doc.get("year") or 0
    genres = [g.get("name", "").capitalize() for g in doc.get("genres", []) if g.get("name")]

    rating_obj = doc.get("rating") or {}
    rating = round(float(rating_obj.get("kp") or rating_obj.get("imdb") or 7.0), 1)

    poster_obj = doc.get("poster") or {}
    poster = poster_obj.get("previewUrl") or poster_obj.get("url") or ""

    description = doc.get("description") or doc.get("shortDescription") or "Описание отсутствует."

    # Трейлер с YouTube
    trailer_id = ""
    videos = (doc.get("videos") or {}).get("trailers") or []
    for vid in videos:
        vid_id = _extract_youtube_id(vid.get("url", ""))
        if vid_id:
            trailer_id = vid_id
            break

    trailer_url = f"https://www.youtube.com/embed/{trailer_id}?enablejsapi=1" if trailer_id else ""
    trailer_watch_url = (
        f"https://www.youtube.com/watch?v={trailer_id}"
        if trailer_id
        else f"https://www.youtube.com/results?search_query={urllib.parse.quote(title + ' трейлер')}"
    )

    # Прямые площадки для просмотра из watchability + ссылка на сам Кинопоиск
    watch_links = []
    if kp_id:
        watch_links.append({"name": "Кинопоиск", "url": f"https://www.kinopoisk.ru/film/{kp_id}/"})

    watch_items = (doc.get("watchability") or {}).get("items") or []
    for item in watch_items[:3]:
        name = item.get("name")
        url = item.get("url")
        if name and url and name.lower() != "кинопоиск":
            watch_links.append({"name": name, "url": url})

    if len(watch_links) <= 1:
        watch_links = build_watch_links(title, kp_id)

    reviews = await _fetch_reviews(session, kp_id, headers) if kp_id else []

    return {
        "title": title,
        "year": year,
        "genres": genres,
        "genre": ", ".join(genres),
        "rating": rating,
        "poster": poster,
        "description": description,
        "trailer_id": trailer_id,
        "trailer_url": trailer_url,
        "trailer_watch_url": trailer_watch_url,
        "reviews": reviews,
        "watch_links": watch_links,
    }


async def fetch_movies_by_genres(selected_genres: list[str], limit: int = 6) -> list[dict]:
    if KP_API_KEY:
        headers = {"X-API-KEY": KP_API_KEY, "Accept": "application/json"}
        params = [
            ("limit", str(limit)),
            ("type", "movie"),
            ("rating.kp", "6.5-10"),
            ("sortField", "votes.kp"),
            ("sortType", "-1"),
            ("notNullFields", "poster.url"),
            ("notNullFields", "description"),
        ]
        # Передаем первый выбранный жанр для фильтрации
        for g in selected_genres:
            mapped = GENRE_TO_KP_DEV.get(g)
            if mapped:
                params.append(("genres.name", mapped))
                break

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(f"{KP_DEV_BASE}/movie", headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        docs = data.get("docs", [])
                        if docs:
                            tasks = [_format_kp_dev_doc(session, doc, headers) for doc in docs]
                            movies = await asyncio.gather(*tasks)
                            print(f"[API] Kinopoisk.dev вернул {len(movies)} фильмов.")
                            return list(movies)
                    else:
                        print(f"[API] Kinopoisk.dev статус {resp.status}, переход на локальную базу.")
        except Exception as e:
            print(f"[API] Ошибка Kinopoisk.dev: {e}")

    # Локальный фоллбэк
    all_movies = get_all_fallback_movies()
    if not selected_genres:
        return all_movies[:limit]

    wanted = {g.lower() for g in selected_genres}
    filtered = [m for m in all_movies if wanted & {g.lower() for g in m["genres"]}]
    return (filtered if filtered else all_movies)[:limit]


async def fetch_movies_by_titles(titles: list[str]) -> list[dict]:
    if KP_API_KEY:
        headers = {"X-API-KEY": KP_API_KEY, "Accept": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async def search_one(title: str):
                    async with session.get(
                        f"{KP_DEV_BASE}/movie/search",
                        headers=headers,
                        params={"query": title, "limit": 1},
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            docs = data.get("docs", [])
                            if docs:
                                return await _format_kp_dev_doc(session, docs[0], headers)
                    return None

                results = await asyncio.gather(*(search_one(t) for t in titles[:6]))
                movies = [m for m in results if m is not None]
                if movies:
                    print(f"[API] Kinopoisk.dev нашел {len(movies)} фильмов по списку ИИ.")
                    return movies
        except Exception as e:
            print(f"[API] Ошибка поиска по названиям в Kinopoisk.dev: {e}")

    # Локальный поиск
    all_movies = get_all_fallback_movies()
    by_title = {m["title"].lower(): m for m in all_movies}
    result = [by_title[t.lower()] for t in titles if t.lower() in by_title]
    return result if result else all_movies[:6]