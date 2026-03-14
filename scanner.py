from pathlib import Path
from typing import Iterator, List, Optional

class VideoScanner:
    VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov'}

    def __init__(self, directory_path: str, exclude_folders: Optional[List[str]] = None):
        self.directory_path = Path(directory_path)
        self.exclude_folders = exclude_folders or []

    def scan(self) -> Iterator[Path]:
        if not self.directory_path.exists() or not self.directory_path.is_dir():
            raise ValueError(f"Директорія не знайдена: {self.directory_path}")

        for item in self.directory_path.iterdir():
            # 🛑 ПЕРЕВІРКА НА ВИКЛЮЧЕННЯ
            if item.name in self.exclude_folders:
                continue

            if item.is_file() and item.suffix.lower() in self.VIDEO_EXTENSIONS:
                yield item
            elif item.is_dir():
                # Перевіряємо наявність відео всередині папки
                has_video = any(
                    f.suffix.lower() in self.VIDEO_EXTENSIONS
                    for f in item.rglob('*') if f.is_file()
                )
                if has_video:
                    yield item