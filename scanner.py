from pathlib import Path
from collections.abc import Iterator

class VideoScanner:
    VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov'}

    def __init__(self, directory_path: str, exclude_folders: list[str] | None = None):
        self.directory_path = Path(directory_path)
        # 🟠 Оптимізація: Set для миттєвого пошуку O(1)
        self.exclude_folders = set(exclude_folders) if exclude_folders else set()

    def scan(self) -> Iterator[Path]:
        if not self.directory_path.exists() or not self.directory_path.is_dir():
            raise ValueError(f"Директорія не знайдена: {self.directory_path}")

        for item in self.directory_path.iterdir():
            # 🛑 ПЕРЕВІРКА НА ВИКЛЮЧЕННЯ (миттєва)
            if item.name in self.exclude_folders:
                continue

            if item.is_file() and item.suffix.lower() in self.VIDEO_EXTENSIONS:
                yield item
            elif item.is_dir():
                try:
                    # ⚡ any() гарантує миттєву зупинку на першому відео
                    has_video = any(
                        f.suffix.lower() in self.VIDEO_EXTENSIONS
                        for f in item.rglob('*') if f.is_file()
                    )
                    if has_video:
                        yield item
                except PermissionError:
                    # 🟡 Надійність: Захист від падіння на системних папках Windows
                    pass