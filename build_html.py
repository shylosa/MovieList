from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Iterator

from config import APP_VERSION, DB_PATH, HTML_PATH, POSTERS_DIR

# ---------------------------------------------------------------------------
# SVG-іконки — окремі константи, не вбудовані в f-string
# ---------------------------------------------------------------------------

_GRID_ICON_SVG: str = (
    '<svg viewBox="0 0 24 24" class="toggle-icon">'
    '<path d="M4 4h4v4H4V4m6 0h4v4h-4V4m6 0h4v4h-4V4M4 10h4v4H4v-4m6 0h4v4h-4v-4'
    "m6 0h4v4h-4v-4M4 16h4v4H4v-4m6 0h4v4h-4v-4m6 0h4v4h-4v-4Z"
    '"/></svg>'
)

_LIST_ICON_SVG: str = (
    '<svg viewBox="0 0 24 24" class="toggle-icon">'
    '<path d="M4 6h16v2H4V6m0 5h16v2H4v-2m0 5h16v2H4v-2m-3 0h2v2H1v-2m0-5h2v2H1v-2m0-5h2v2H1V6"'
    "/></svg>"
)

# Локальний fallback — без зовнішніх запитів
_POSTER_PLACEHOLDER: str = "assets/no-poster.jpg"


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Movie:
    filename: str
    title_ua: str
    title_en: str | None
    year: int | None
    genres: str | None
    cast: str | None
    plot: str | None
    local_poster_path: str | None


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------


def _iter_movies(db_path: str) -> Iterator[Movie]:
    """Ітерує фільми з БД без завантаження всього датасету в пам'ять."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT
                filename,
                title_ua,
                title_en,
                year,
                genres,
                "cast",
                plot,
                local_poster_path
            FROM movies
            ORDER BY year DESC
            """
        )
        for row in cursor:
            yield Movie(
                filename=row["filename"],
                title_ua=row["title_ua"] or "",
                title_en=row["title_en"],
                year=row["year"],
                genres=row["genres"],
                cast=row["cast"],
                plot=row["plot"],
                local_poster_path=row["local_poster_path"],
            )


def _count_movies(db_path: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]


# ---------------------------------------------------------------------------
# Poster resolution
# ---------------------------------------------------------------------------


def _resolve_poster(movie: Movie) -> str:
    """Повертає перший існуючий шлях до постера або локальний placeholder."""
    stem = os.path.splitext(movie.filename)[0]
    candidates = [
        movie.local_poster_path,
        os.path.join(POSTERS_DIR, f"{stem}.jpg"),
        os.path.join(POSTERS_DIR, f"{stem}.png"),
        os.path.join(POSTERS_DIR, f"{stem}.webp"),
    ]
    return next(
        (p for p in candidates if p and os.path.exists(p)),
        _POSTER_PLACEHOLDER,
    )


# ---------------------------------------------------------------------------
# HTML render helpers
# ---------------------------------------------------------------------------


def _render_card(movie: Movie) -> str:
    """Рендерить одну картку фільму. Усі поля екрановані від XSS."""
    title_ua = escape(movie.title_ua)
    title_en = escape(movie.title_en or "")
    year = escape(str(movie.year)) if movie.year else "—"
    genres = escape(movie.genres or "Не вказано")
    cast = escape(movie.cast or "Дані відсутні")
    plot = escape(movie.plot or "Опис відсутній")
    filename = escape(movie.filename)
    poster = escape(_resolve_poster(movie))

    return f"""
            <div class="card">
                <div class="poster-container">
                    <img class="poster" src="{poster}" alt="{title_ua}" loading="lazy">
                </div>
                <div class="info">
                    <div class="title-meta-group">
                        <h2 class="title-ua" title="{title_ua}">{title_ua}</h2>
                        <span class="year">{year}</span>
                        <span class="genre">{genres}</span>
                    </div>
                    <h3 class="title-en" title="{title_en}">{title_en}</h3>
                    <div class="details" title="{cast}"><strong>Актори:</strong> <span class="cast">{cast}</span></div>
                    <div class="plot"><strong>Сюжет:</strong><br><span class="plot-text">{plot}</span></div>
                    <div class="filename" title="{filename}">{filename}</div>
                </div>
            </div>"""


def _render_header(total_movies: int, generation_time: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="app-version" content="{escape(APP_VERSION)}">
    <title>MovieList {escape(APP_VERSION)}</title>
    <link rel="icon" type="image/x-icon" href="logo.ico">
    <style>
        body {{ background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; line-height: 1.6; }}
        .sticky-header {{ position: sticky; top: 0; background: rgba(18, 18, 18, 0.95); backdrop-filter: blur(10px); z-index: 1000; padding: 15px 0; border-bottom: 1px solid #333; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }}
        .controls {{ max-width: 95%; margin: 0 auto; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
        .logo {{ font-size: 1.5em; font-weight: bold; color: #e50914; text-transform: uppercase; margin-right: auto; }}
        .search-input, .sort-select, .btn-action {{ padding: 10px 15px; border-radius: 8px; border: 1px solid #444; background: #222; color: #fff; font-size: 1em; }}
        .search-input {{ flex-grow: 1; min-width: 200px; }}
        .search-input:focus {{ outline: none; border-color: #e50914; }}
        .btn-action {{ background: #2b2b2b; cursor: pointer; font-weight: bold; transition: background 0.2s; display: flex; align-items: center; gap: 8px; }}
        .btn-action:hover {{ background: #3b3b3b; }}
        .btn-action.primary {{ background: #e50914; border-color: #e50914; }}
        .btn-action.primary:hover {{ background: #b2070f; }}
        .toggle-icon {{ width: 1.2em; height: 1.2em; fill: currentColor; vertical-align: middle; }}

        .stats-bar {{ max-width: 95%; margin: 15px auto 0; padding: 10px 20px; background: #1a1a1a; border-radius: 8px; border: 1px solid #333; display: flex; gap: 15px; font-size: 0.9em; color: #aaa; align-items: center; box-sizing: border-box; }}
        .stats-bar strong {{ color: #fff; font-size: 1.1em; }}
        .stats-divider {{ color: #444; }}
        #filteredCount {{ color: #e50914; margin-left: -5px; }}
        #filteredCount strong {{ color: #e50914; }}

        .container {{ max-width: 95%; margin: 20px auto 30px; }}
        .movie-list {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(650px, 1fr)); gap: 30px; transition: all 0.3s; }}
        .card {{ display: flex; background: #1e1e1e; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 20px rgba(0,0,0,0.3); border: 1px solid #333; transition: transform 0.2s; }}
        .card:hover {{ transform: translateY(-3px); border-color: #555; }}
        .poster-container {{ flex-shrink: 0; width: 220px; background: #000; overflow: hidden; }}
        .poster {{ width: 100%; height: 100%; object-fit: cover; display: block; cursor: zoom-in; transition: transform 0.3s, opacity 0.2s; }}
        .poster:hover {{ opacity: 0.85; transform: scale(1.03); }}
        .info {{ padding: 25px; display: flex; flex-direction: column; width: 100%; }}
        .title-meta-group {{ display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 5px; }}
        .title-ua {{ width: 100%; font-size: 1.6em; font-weight: bold; margin: 0 0 5px 0; color: #ffffff; line-height: 1.2; }}
        .year {{ background: #e50914; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; }}
        .genre {{ color: #e50914; font-size: 0.9em; font-weight: bold; }}
        .title-en {{ font-size: 1em; color: #888; margin: 0 0 15px 0; font-style: italic; }}
        .details {{ margin-bottom: 10px; font-size: 0.9em; }}
        .details strong {{ color: #bbb; margin-right: 5px; }}
        .plot {{ margin-top: 10px; font-size: 0.95em; color: #ccc; flex-grow: 1; text-align: justify; }}
        .filename {{ margin-top: 20px; font-size: 0.85em; color: #aaa; font-family: monospace; text-align: right; border-top: 1px solid #333; padding-top: 5px; }}

        .movie-list.list-view {{ grid-template-columns: 1fr; gap: 12px; }}
        .movie-list.list-view .card {{ flex-direction: row; height: 145px; align-items: stretch; }}
        .movie-list.list-view .poster-container {{ width: 95px; height: 100%; }}
        .movie-list.list-view .info {{ padding: 12px 20px; display: grid; grid-template-columns: 48% 1fr; grid-template-rows: auto auto 1fr auto; gap: 2px 25px; width: 100%; }}
        .movie-list.list-view .title-meta-group {{ grid-column: 1; grid-row: 1; display: grid; grid-template-columns: 240px 50px 1fr; gap: 12px; align-items: start; width: 100%; }}
        .movie-list.list-view .title-ua {{ width: auto; margin: 0; font-size: 1.25em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2; }}
        .movie-list.list-view .year {{ text-align: center; padding: 2px 5px; font-size: 0.8em; line-height: 1.2; }}
        .movie-list.list-view .genre {{ margin: 0; font-size: 0.85em; line-height: 1.2; }}
        .movie-list.list-view .title-en {{ grid-column: 1; grid-row: 2; font-size: 0.85em; margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .movie-list.list-view .details {{ grid-column: 1; grid-row: 3 / 5; font-size: 0.85em; margin: 0; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
        .movie-list.list-view .plot {{ grid-column: 2; grid-row: 1 / 4; margin: 0; font-size: 0.85em; color: #bbb; text-align: left; display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; }}
        .movie-list.list-view .filename {{ grid-column: 2; grid-row: 4; margin: 0; text-align: right; align-self: end; font-size: 0.75em; border: none; padding: 0; color: #bbb; }}

        .no-results {{ grid-column: 1 / -1; text-align: center; padding: 50px; font-size: 1.2em; color: #888; display: none; }}

        .modal {{ display: none; position: fixed; z-index: 2000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); backdrop-filter: blur(8px); justify-content: center; align-items: center; cursor: zoom-out; }}
        .modal-content {{ max-width: 90vw; max-height: 90vh; border-radius: 8px; box-shadow: 0 10px 40px rgba(0,0,0,0.8); object-fit: contain; }}

        @media (max-width: 768px) {{
            .controls {{ flex-direction: column; align-items: stretch; }}
            .logo {{ text-align: center; margin: 0 0 10px 0; }}
            .stats-bar {{ flex-direction: column; gap: 5px; align-items: flex-start; }}
            .stats-divider {{ display: none; }}
            .movie-list {{ grid-template-columns: 1fr; }}
            .card {{ flex-direction: column; height: auto !important; }}
            .poster-container {{ width: 100% !important; aspect-ratio: 2/3; }}
            .movie-list.list-view .info {{ display: flex; flex-direction: column; padding: 15px; gap: 10px; }}
            .movie-list.list-view .title-meta-group {{ display: flex; flex-wrap: wrap; }}
            .movie-list.list-view .title-ua {{ white-space: normal; }}
        }}
    </style>
</head>
<body>
    <header class="sticky-header">
        <div class="controls">
            <div class="logo">🍿 MovieList</div>
            <button id="viewToggle" class="btn-action">{_LIST_ICON_SVG}Список</button>
            <input type="text" id="searchInput" class="search-input" placeholder="Шукати за назвою, актором, жанром чи роком...">
            <select id="sortSelect" class="sort-select">
                <option value="year-desc">Новіші (за роком)</option>
                <option value="year-asc">Старіші (за роком)</option>
                <option value="title-asc">А-Я (за назвою)</option>
                <option value="title-desc">Я-А (за назвою)</option>
            </select>
            <button id="resetBtn" class="btn-action primary">Скинути</button>
        </div>
    </header>

    <div class="stats-bar">
        <span>🎬 Всього у базі: <strong>{total_movies}</strong></span>
        <span id="filteredCount" style="display: none;">(Знайдено: <strong id="filteredNum">0</strong>)</span>
        <span class="stats-divider">|</span>
        <span>📅 Останнє оновлення: <strong>{generation_time}</strong></span>
    </div>

    <div class="container">
        <div class="movie-list" id="movieList">
            <div id="noResults" class="no-results">За вашим запитом нічого не знайдено 🤷‍♂️</div>"""


def _render_footer() -> str:
    grid_icon_json = json.dumps(_GRID_ICON_SVG)
    list_icon_json = json.dumps(_LIST_ICON_SVG)

    return f"""
        </div>
    </div>

    <div id="imageModal" class="modal">
        <img class="modal-content" id="modalImage" alt="Постер">
    </div>

    <script>
        const searchInput = document.getElementById('searchInput');
        const sortSelect = document.getElementById('sortSelect');
        const resetBtn = document.getElementById('resetBtn');
        const viewToggle = document.getElementById('viewToggle');
        const movieList = document.getElementById('movieList');
        const noResults = document.getElementById('noResults');
        const filteredCountSpan = document.getElementById('filteredCount');
        const filteredNum = document.getElementById('filteredNum');

        let cards = Array.from(document.querySelectorAll('.card'));

        const gridIconSvg = {grid_icon_json};
        const listIconSvg = {list_icon_json};

        // Відновлення режиму перегляду — з fallback якщо localStorage недоступний
        let savedView = 'grid';
        try {{
            savedView = localStorage.getItem('viewMode') || 'grid';
        }} catch (e) {{}}

        if (savedView === 'list') {{
            movieList.classList.add('list-view');
            viewToggle.innerHTML = gridIconSvg + 'Сітка';
        }} else {{
            viewToggle.innerHTML = listIconSvg + 'Список';
        }}

        viewToggle.addEventListener('click', () => {{
            movieList.classList.toggle('list-view');
            const isList = movieList.classList.contains('list-view');
            try {{
                localStorage.setItem('viewMode', isList ? 'list' : 'grid');
            }} catch (e) {{}}
            viewToggle.innerHTML = isList ? gridIconSvg + 'Сітка' : listIconSvg + 'Список';
        }});

        function filterAndSort() {{
            const searchTerm = searchInput.value.toLowerCase().trim();
            const sortValue = sortSelect.value;
            let visibleCards = [];

            cards.forEach(card => {{
                const titleUa   = card.querySelector('.title-ua')?.textContent   || '';
                const titleEn   = card.querySelector('.title-en')?.textContent   || '';
                const year      = card.querySelector('.year')?.textContent       || '';
                const genre     = card.querySelector('.genre')?.textContent      || '';
                const cast      = card.querySelector('.cast')?.textContent       || '';
                const plot      = card.querySelector('.plot-text')?.textContent  || '';

                const haystack = `${{titleUa}} ${{titleEn}} ${{year}} ${{genre}} ${{cast}} ${{plot}}`.toLowerCase();
                const visible = haystack.includes(searchTerm);

                card.style.display = visible ? 'flex' : 'none';
                if (visible) visibleCards.push(card);
            }});

            noResults.style.display = visibleCards.length === 0 ? 'block' : 'none';

            if (searchTerm === '') {{
                filteredCountSpan.style.display = 'none';
            }} else {{
                filteredCountSpan.style.display = 'inline';
                filteredNum.textContent = visibleCards.length;
            }}

            visibleCards.sort((a, b) => {{
                const yearA  = parseInt(a.querySelector('.year').innerText)  || 0;
                const yearB  = parseInt(b.querySelector('.year').innerText)  || 0;
                const titleA = a.querySelector('.title-ua').innerText.toLowerCase();
                const titleB = b.querySelector('.title-ua').innerText.toLowerCase();

                switch (sortValue) {{
                    case 'year-desc':  return yearB - yearA;
                    case 'year-asc':   return yearA - yearB;
                    case 'title-asc':  return titleA.localeCompare(titleB, 'uk');
                    case 'title-desc': return titleB.localeCompare(titleA, 'uk');
                    default:           return 0;
                }}
            }});

            const hidden = cards.filter(c => !visibleCards.includes(c));
            [...visibleCards, ...hidden].forEach(card => movieList.appendChild(card));
        }}

        searchInput.addEventListener('input', filterAndSort);
        sortSelect.addEventListener('change', filterAndSort);
        resetBtn.addEventListener('click', () => {{
            searchInput.value = '';
            sortSelect.value = 'year-desc';
            filterAndSort();
        }});

        // Модальне вікно для постера
        const modalWrapper = document.getElementById('imageModal');
        const modalImage   = document.getElementById('modalImage');

        movieList.addEventListener('click', e => {{
            if (e.target.classList.contains('poster')) {{
                modalImage.src = e.target.src;
                modalWrapper.style.display = 'flex';
            }}
        }});

        modalWrapper.addEventListener('click', () => {{
            modalWrapper.style.display = 'none';
            modalImage.src = '';
        }});
    </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_html() -> None:
    """Генерує статичний HTML-каталог фільмів з БД.

    Особливості:
    - Ітерація курсором замість fetchall() — O(1) пам'ять
    - html.escape() на всіх полях — захист від XSS
    - list + "".join() замість str += — O(n) замість O(n²)
    - Локальний fallback для постерів — без зовнішніх запитів
    """
    print(f"🎨 Генерація локального веб-каталогу {APP_VERSION}...")

    try:
        total_movies: int = _count_movies(DB_PATH)
        generation_time: str = datetime.now().strftime("%d.%m.%Y о %H:%M")

        parts: list[str] = [_render_header(total_movies, generation_time)]

        rendered_count = 0
        for movie in _iter_movies(DB_PATH):
            parts.append(_render_card(movie))
            rendered_count += 1

        parts.append(_render_footer())

        html_content: str = "".join(parts)

        with open(HTML_PATH, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"✅ Файл '{HTML_PATH}' успішно оновлено! ({rendered_count} фільмів)")

    except sqlite3.Error as e:
        print(f"❌ Помилка бази даних: {e}")
    except OSError as e:
        print(f"❌ Помилка запису файлу: {e}")


if __name__ == "__main__":
    generate_html()