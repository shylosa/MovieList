import sqlite3
import os
import json
from config import APP_VERSION  # Беремо версію з нашого центру налаштувань!

grid_icon_svg = '<svg viewBox="0 0 24 24" class="toggle-icon"><path d="M4 4h4v4H4V4m6 0h4v4h-4V4m6 0h4v4h-4V4M4 10h4v4H4v-4m6 0h4v4h-4v-4m6 0h4v4h-4v-4M4 16h4v4H4v-4m6 0h4v4h-4v-4m6 0h4v4h-4v-4Z"/></svg>'
list_icon_svg = '<svg viewBox="0 0 24 24" class="toggle-icon"><path d="M4 6h16v2H4V6m0 5h16v2H4v-2m0 5h16v2H4v-2m-3 0h2v2H1v-2m0-5h2v2H1v-2m0-5h2v2H1V6"/></svg>'


def generate_html():
    print(f"🎨 Генерація локального веб-каталогу v{APP_VERSION}...")
    try:
        conn = sqlite3.connect("movies.db")
        cursor = conn.cursor()

        cursor.execute(
            'SELECT filename, title_ua, title_en, year, genres, "cast", plot, local_poster_path FROM movies ORDER BY year DESC')
        movies = cursor.fetchall()

        html_content = f"""
        <!DOCTYPE html>
        <html lang="uk">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>MovieList - Локальний Каталог</title>
            <link rel="icon" type="image/x-icon" href="logo.ico">
            <style>
                /* Той самий CSS залишається без змін */
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
                .container {{ max-width: 95%; margin: 30px auto; }}
                .movie-list {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(650px, 1fr)); gap: 30px; transition: all 0.3s; }}
                .card {{ display: flex; background: #1e1e1e; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 20px rgba(0,0,0,0.3); border: 1px solid #333; transition: transform 0.2s; }}
                .card:hover {{ transform: translateY(-3px); border-color: #555; }}
                .poster-container {{ flex-shrink: 0; width: 220px; background: #000; }}
                .poster {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
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
                @media (max-width: 768px) {{
                    .controls {{ flex-direction: column; align-items: stretch; }}
                    .logo {{ text-align: center; margin: 0 0 10px 0; }}
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
                    <div class="logo">🍿 MovieList <span style="font-size: 0.5em; color: #555;">v{APP_VERSION}</span></div>
                    <button id="viewToggle" class="btn-action">{list_icon_svg}Список</button>
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

            <div class="container">
                <div class="movie-list" id="movieList">
                    <div id="noResults" class="no-results">За вашим запитом нічого не знайдено 🤷‍♂️</div>
        """

        for m in movies:
            filename, title_ua, title_en, year, genres, cast_members, plot, poster_path = m

            # Фронтенд-заглушки для порожніх значень
            title_en_display = title_en if title_en else ""
            year_display = year if year else "—"
            genres_display = genres if genres else "Не вказано"
            cast_display = cast_members if cast_members else "Дані відсутні"
            plot_display = plot if plot else "Опис відсутній"

            if poster_path and os.path.exists(poster_path):
                img_src = poster_path
            else:
                manual_path = os.path.join("posters", f"{os.path.splitext(filename)[0]}.jpg")
                if os.path.exists(manual_path):
                    img_src = manual_path
                else:
                    img_src = "https://via.placeholder.com/220x330/222222/e50914?text=No+Poster"

            html_content += f"""
                    <div class="card">
                        <div class="poster-container">
                            <img class="poster" src="{img_src}" alt="{title_ua}" loading="lazy">
                        </div>
                        <div class="info">
                            <div class="title-meta-group">
                                <h2 class="title-ua" title="{title_ua}">{title_ua}</h2>
                                <span class="year">{year_display}</span>
                                <span class="genre">{genres_display}</span>
                            </div>
                            <h3 class="title-en" title="{title_en_display}">{title_en_display}</h3>
                            <div class="details" title="{cast_display}"><strong>Актори:</strong> <span class="cast">{cast_display}</span></div>
                            <div class="plot"><strong>Сюжет:</strong><br><span class="plot-text">{plot_display}</span></div>
                            <div class="filename" title="{filename}">{filename}</div>
                        </div>
                    </div>
            """

        html_content += """
                </div>
            </div>

            <script>
                const searchInput = document.getElementById('searchInput');
                const sortSelect = document.getElementById('sortSelect');
                const resetBtn = document.getElementById('resetBtn');
                const viewToggle = document.getElementById('viewToggle');
                const movieList = document.getElementById('movieList');
                const noResults = document.getElementById('noResults');

                let cards = Array.from(document.querySelectorAll('.card'));

        """

        html_content += f"""
                const gridIconSvg = {json.dumps(grid_icon_svg)};
                const listIconSvg = {json.dumps(list_icon_svg)};
        """

        html_content += """
                if (localStorage.getItem('viewMode') === 'list') {
                    movieList.classList.add('list-view');
                    viewToggle.innerHTML = gridIconSvg + 'Сітка';
                } else {
                    viewToggle.innerHTML = listIconSvg + 'Список';
                }

                viewToggle.addEventListener('click', () => {
                    movieList.classList.toggle('list-view');
                    if (movieList.classList.contains('list-view')) {
                        localStorage.setItem('viewMode', 'list');
                        viewToggle.innerHTML = gridIconSvg + 'Сітка';
                    } else {
                        localStorage.setItem('viewMode', 'grid');
                        viewToggle.innerHTML = listIconSvg + 'Список';
                    }
                });

                function filterAndSort() {
                    const searchTerm = searchInput.value.toLowerCase().trim();
                    const sortValue = sortSelect.value;
                    let visibleCount = 0;

                    let visibleCards = [];
                    cards.forEach(card => {
                        const titleUa = card.querySelector('.title-ua')?.textContent || "";
                        const titleEn = card.querySelector('.title-en')?.textContent || "";
                        const year = card.querySelector('.year')?.textContent || "";
                        const genre = card.querySelector('.genre')?.textContent || "";
                        const cast = card.querySelector('.cast')?.textContent || "";
                        const plot = card.querySelector('.plot-text')?.textContent || "";

                        const textContent = `${titleUa} ${titleEn} ${year} ${genre} ${cast} ${plot}`.toLowerCase();

                        if (textContent.includes(searchTerm)) {
                            card.style.display = 'flex';
                            visibleCards.push(card);
                            visibleCount++;
                        } else {
                            card.style.display = 'none';
                        }
                    });

                    noResults.style.display = visibleCount === 0 ? 'block' : 'none';

                    visibleCards.sort((a, b) => {
                        const yearA = parseInt(a.querySelector('.year').innerText) || 0;
                        const yearB = parseInt(b.querySelector('.year').innerText) || 0;
                        const titleA = a.querySelector('.title-ua').innerText.toLowerCase();
                        const titleB = b.querySelector('.title-ua').innerText.toLowerCase();

                        if (sortValue === 'year-desc') return yearB - yearA;
                        if (sortValue === 'year-asc') return yearA - yearB;
                        if (sortValue === 'title-asc') return titleA.localeCompare(titleB, 'uk');
                        if (sortValue === 'title-desc') return titleB.localeCompare(titleA, 'uk');
                    });

                    cards.forEach(card => card.remove());
                    visibleCards.forEach(card => movieList.appendChild(card));
                    cards.filter(c => !visibleCards.includes(c)).forEach(c => movieList.appendChild(c));
                }

                searchInput.addEventListener('input', filterAndSort);
                sortSelect.addEventListener('change', filterAndSort);

                resetBtn.addEventListener('click', () => {
                    searchInput.value = '';
                    sortSelect.value = 'year-desc';
                    filterAndSort();
                });
            </script>
        </body>
        </html>
        """

        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✅ Файл 'index.html' успішно оновлено!")

    except Exception as e:
        print(f"❌ Помилка генерації HTML: {e}")


if __name__ == "__main__":
    generate_html()