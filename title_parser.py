from guessit import guessit
from typing import Any


class MovieParser:
    @staticmethod
    def parse_filename(filename: str) -> dict[str, Any]:
        """
        Аналізує сиру назву файлу і витягує з неї чисті метадані.
        """
        # guessit робить всю брудну роботу за нас
        guess = guessit(filename)

        # 🟡 Надійність: Гарантуємо, що рік завжди буде рядком або порожнім (захист від списків)
        raw_year = guess.get('year')
        year_str = ""
        if isinstance(raw_year, list) and raw_year:
            year_str = str(raw_year[0])
        elif raw_year:
            year_str = str(raw_year)

        return {
            'original_filename': filename,
            'title': guess.get('title'),
            'year': year_str,
            'type': guess.get('type')  # 'movie' або 'episode'
        }