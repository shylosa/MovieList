import tkinter as tk
from tkinter import ttk
import threading
import sys
import os
import webbrowser
import ctypes
from tkinter import messagebox

# --- ПОПЕРЕДНЯ ПЕРЕВІРКА ---
if not os.path.exists(".env"):
    error_root = tk.Tk()
    error_root.withdraw() # Ховаємо фонове вікно, залишаємо тільки попап
    messagebox.showerror(
        "Відсутні налаштування",
        "Файл '.env' не знайдено!\n\n"
        "Для роботи програми необхідні API-ключі та вказаний шлях до папки з фільмами.\n\n"
        "Що робити:\n"
        "1. Створіть файл .env у папці з програмою.\n"
        "2. Скопіюйте в нього налаштування з .env.example та додайте свої ключі.\n\n"
        "Програма зараз завершить роботу."
    )
    sys.exit()

import main
import build_html
from config import APP_VERSION

class TextRedirector:
    def __init__(self, widget):
        self.widget = widget

    def write(self, text):
        self.widget.configure(state='normal')
        self.widget.insert(tk.END, text)
        self.widget.see(tk.END)
        self.widget.configure(state='disabled')

    def flush(self):
        pass


def run_in_thread(func):
    console.configure(state='normal')
    console.delete(1.0, tk.END)
    console.configure(state='disabled')
    threading.Thread(target=func, daemon=True).start()


def action_scan():
    def task():
        print("🚀 Запуск локального сканування...\n" + "-" * 40)
        main.run_scan()
        print("\n✅ Процес успішно завершено!")

    run_in_thread(task)


def action_sync():
    def task():
        print("☁️ Відправка даних у Google Sheets...\n" + "-" * 40)
        main.run_sync()
        print("\n✅ Синхронізація успішна!")

    run_in_thread(task)


def action_html():
    def task():
        db_path = "movies.db"
        html_path = "index.html"
        script_path = "build_html.py"  # Додаємо наш скрипт

        need_update = True
        if os.path.exists(html_path) and os.path.exists(db_path):
            db_mtime = os.path.getmtime(db_path)
            html_mtime = os.path.getmtime(html_path)

            # Якщо база старіша за HTML, перевіряємо ще й версію всередині файлу
            if html_mtime > db_mtime:
                from config import APP_VERSION
                with open(html_path, "r", encoding="utf-8") as f:
                    # Читаємо перші 1000 символів, де знаходиться тег <title>
                    head_content = f.read(1000)
                    if f"MovieList v{APP_VERSION}" in head_content:
                        need_update = False  # Тільки якщо і база стара, і версія актуальна!

        if need_update:
            print("🎨 База або версія програми змінилися. Оновлюю вітрину...")
            import build_html
            build_html.generate_html()
        else:
            print("✨ Вітрина актуальна. Відкриваю...")

        webbrowser.open('file://' + os.path.realpath(html_path))

    run_in_thread(task)

try:
    myappid = f"my.custom.movielist.app.{APP_VERSION}"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass # На випадок, якщо запустимо не на Windows

root = tk.Tk()
root.title(f"MovieList {APP_VERSION}")
root.geometry("750x450")
root.configure(bg="#121212")

# Функція для примусового перефарбування шапки
def apply_dark_mode():
    try:
        # Використовуємо GetParent, щоб дістатися до справжньої рамки Windows
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())

        # Насильно встановлюємо атрибути
        dark_mode = ctypes.c_int(2)
        # Спробуємо відразу три версії атрибута (для різних збірок Win 10/11)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark_mode), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 8, ctypes.byref(dark_mode), 4)  # Додатковий для Win10

        # ПРИМУСОВЕ ПЕРЕМАЛЬОВУВАННЯ
        # SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)

        # Фокусуємо вікно на собі, щоб Windows оновив стиль активного вікна
        root.focus_force()
    except Exception as e:
        print(f"Помилка темного режиму: {e}")


# Викликаємо відразу після старту циклу
root.after(0, apply_dark_mode)

# --- ДОДАЄМО ЛОГОТИП ДО ВІКНА ---
try:
    # Якщо logo.ico лежить у папці, вікно отримає фірмову іконку
    root.iconbitmap("logo.ico")
except Exception:
    pass  # Якщо файлу немає, програма просто проігнорує це і не впаде

# --- ЖОРСТКА СТИЛІЗАЦІЯ СКРОЛБАРА (Плоский темний дизайн) ---
style = ttk.Style()
style.theme_use('clam')
style.configure("Dark.Vertical.TScrollbar",
                gripcount=0,
                background="#404040",  # Темно-сірий повзунок
                troughcolor="#1e1e1e",  # Темний фон канавки (в тон консолі)
                bordercolor="#1e1e1e",  # Прибираємо рамки
                darkcolor="#404040",  # Вбиваємо 3D-тіні
                lightcolor="#404040",  # Вбиваємо 3D-відблиски
                arrowcolor="#ffffff")  # Білі стрілочки

# Робимо повзунок трохи світлішим, коли на нього наводиш мишку
style.map("Dark.Vertical.TScrollbar",
          background=[('active', '#5a5a5a')])

btn_frame = tk.Frame(root, bg="#121212")
btn_frame.pack(pady=20)

btn_style = {
    "font": ("Segoe UI", 11, "bold"), "bg": "#004a77", "fg": "#c2e7ff",
    "activebackground": "#005A9E", "activeforeground": "white",
    "bd": 0, "padx": 15, "pady": 8, "cursor": "hand2", "width": 18
}

tk.Button(btn_frame, text="🔍 Оновити базу", command=action_scan, **btn_style).grid(row=0, column=0, padx=10)
tk.Button(btn_frame, text="☁️ Синхронізувати", command=action_sync, **btn_style).grid(row=0, column=1, padx=10)
tk.Button(btn_frame, text="🎬 Відкрити вітрину", command=action_html, **btn_style).grid(row=0, column=2, padx=10)

# Робимо фон рамки таким самим, як у консолі, щоб не було чорних стиків
console_frame = tk.Frame(root, bg="#1e1e1e")
console_frame.pack(expand=True, fill='both', padx=20, pady=(0, 20))

console = tk.Text(console_frame, bg="#1e1e1e", fg="#cccccc", font=("Consolas", 10), state='disabled', bd=0, padx=10,
                  pady=10)
console.pack(side=tk.LEFT, expand=True, fill='both')

scrollbar = ttk.Scrollbar(console_frame, orient='vertical', command=console.yview, style="Dark.Vertical.TScrollbar")
scrollbar.pack(side=tk.RIGHT, fill='y')
console.configure(yscrollcommand=scrollbar.set)

sys.stdout = TextRedirector(console)
sys.stderr = TextRedirector(console)

print(f"👋 Вітаємо у MovieList {APP_VERSION}!\nОберіть потрібну дію на панелі зверху.\n")

root.mainloop()
