from guessit import guessit
from typing import Dict, Any

class MovieParser:
    @staticmethod
    def parse_filename(filename: str) -> Dict[str, Any]:
        """
        Аналізує сиру назву файлу і витягує з неї чисті метадані.
        """
        # guessit робить всю брудну роботу за нас
        guess = guessit(filename)
        
        return {
            'original_filename': filename,
            'title': guess.get('title'),
            'year': guess.get('year'),
            'type': guess.get('type')  # 'movie' або 'episode'
        }