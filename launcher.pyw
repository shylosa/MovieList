import customtkinter as ctk
import tkinter as tk
import threading
import queue
import sys
import os
import webbrowser
import ctypes
from tkinter import messagebox
import sqlite3
from tkinter import ttk
from datetime import datetime
# Для точного вимірювання тексту без update_idletasks
from tkinter.font import Font

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# --- ПОПЕРЕДНЯ ПЕРЕВІРКА ---
if not os.path.exists(".env"):
    error_root = tk.Tk()
    error_root.withdraw()
    messagebox.showerror(
        "Відсутні налаштування",
        "Файл '.env' не знайдено!\n\n"
        "Для роботи програми необхідні API-ключі та вказаний шлях до папки з фільмами.\n\n"
        "Програма зараз завершить роботу."
    )
    sys.exit()

import main
import build_html
from config import cancel_event
from config import APP_VERSION, DB_PATH, HTML_PATH, GITHUB_NAME, GITHUB_URL

# --- ГЛОБАЛЬНІ ЗМІННІ GUI ---
lbl_total = None
lbl_unrec = None
lbl_last_scan = None
lbl_status_card_sub = None
console = None

_reload_funcs = {}

# ---------------------------------------------------------------------------
# ПАЛІТРА PYCHARM (Darcula New UI) + Gemini Blue
# ---------------------------------------------------------------------------
C = {
    "bg": "#1e1f22",
    "sidebar_bg": "#2b2d30",
    "sidebar_brd": "#393b40",
    "nav_active": "#2e436e",
    "nav_hover": "#35373c",
    "nav_active_fg": "#dfe1e5",
    "nav_fg": "#adb1bb",
    "stat_bg": "#2b2d30",
    "stat_brd": "#393b40",
    "console_bg": "#1e1f22",
    "console_brd": "#393b40",
    "console_topbar": "#2b2d30",
    "editor_bg": "#1e1f22",
    "editor_row": "#2b2d30",
    "editor_row_alt": "#242527",
    "editor_header": "#35383f",
    "editor_input": "#393b40",
    "accent": "#3574f0",
    "accent_hover": "#4e85f2",
    "text_primary": "#dfe1e5",
    "text_muted": "#868a91",
    "text_normal": "#dfe1e5",
    "text_dim": "#6f737a",
    "ok_green": "#59a869",
    "warn_yellow": "#e2b040",
    "progress": "#3574f0",
    "blue_text": "#4db8ff",
    "gemini_blue": "#1557b0",
    "gemini_hover": "#1a73e8",
}

# ---------------------------------------------------------------------------
# THREAD-SAFE ЛОГУВАННЯ
# ---------------------------------------------------------------------------
log_queue: queue.Queue = queue.Queue()


class TextRedirector:
    def write(self, text: str) -> None:
        log_queue.put(text)

    def flush(self) -> None:
        pass


def _process_log_queue() -> None:
    if not log_queue.empty():
        console.configure(state="normal")
        while not log_queue.empty():
            text = log_queue.get_nowait()
            console.insert(tk.END, text)
        console.see(tk.END)
        console.configure(state="disabled")
    root.after(100, _process_log_queue)


# ---------------------------------------------------------------------------
# ХЕЛПЕРИ
# ---------------------------------------------------------------------------
def _apply_dark_titlebar(window: tk.Misc) -> None:
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        dark = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark), 4)
    except Exception:
        pass


def _center_window(window: ctk.CTk, width: int, height: int) -> None:
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def run_in_thread(func) -> None:
    # 1. Скидаємо прапорець перед новим запуском
    cancel_event.clear()

    # 2. Показуємо кнопку зупинки (зліва від кнопки копіювання)
    stop_btn.place(relx=1.0, rely=0.5, anchor="e", x=-125)

    console.configure(state="normal")
    console.delete("1.0", tk.END)
    console.configure(state="disabled")

    if _active_panel_key != "overview":
        _show_panel("overview")
        _set_active_nav("scan")

    progress_bar.pack(fill="x")
    progress_bar.configure(mode="indeterminate")
    progress_bar.start()
    _set_nav_loading(True)

    def wrapped():
        try:
            func()
        finally:
            root.after(0, progress_bar.stop)
            root.after(0, lambda: progress_bar.configure(mode="determinate"))
            root.after(0, lambda: progress_bar.set(0))
            root.after(0, progress_bar.pack_forget)
            root.after(0, lambda: _set_nav_loading(False))
            root.after(0, stop_btn.place_forget)

    threading.Thread(target=wrapped, daemon=True).start()


def _set_nav_loading(loading: bool) -> None:
    state = "disabled" if loading else "normal"
    for btn in _nav_buttons.values():
        try:
            btn.configure(state=state)
        except Exception:
            pass


def refresh_stats() -> None:
    stats = main.get_db_stats()
    total = stats.get("total", 0)
    unrec = stats.get("unrecognized", 0)
    last = stats.get("last_scan", "Ніколи")

    lbl_total.configure(text=str(total))
    lbl_last_scan.configure(text=last)

    if unrec > 0:
        lbl_unrec.configure(text=f"⚠ {unrec} не розпізнано", text_color=C["warn_yellow"])
        lbl_status_card_sub.configure(text="Потребує уваги", text_color=C["warn_yellow"])
        if "editor_badge_lbl" in _nav_meta:
            _nav_meta["editor_badge_lbl"].configure(text=str(unrec), fg_color="#3a2e00", text_color=C["warn_yellow"])
            _nav_meta["editor_badge_lbl"].grid()
    else:
        lbl_unrec.configure(text="✓ Всі розпізнані", text_color=C["ok_green"])
        lbl_status_card_sub.configure(text="База актуальна", text_color=C["ok_green"])
        if "editor_badge_lbl" in _nav_meta:
            _nav_meta["editor_badge_lbl"].grid_remove()


# ---------------------------------------------------------------------------
# SIDEBAR NAV ITEM
# ---------------------------------------------------------------------------
_nav_buttons: dict[str, ctk.CTkFrame] = {}
_nav_meta: dict = {}
_active_nav_key: str = ""


def _make_nav_item(parent, key, icon, label, command, show_badge=False):
    row = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=7, cursor="hand2", height=38)
    row.pack(fill="x", padx=8, pady=2)
    row.pack_propagate(False)
    row.grid_propagate(False)

    row.columnconfigure(0, weight=0)
    row.columnconfigure(1, weight=0)
    row.columnconfigure(2, weight=1)
    row.rowconfigure(0, weight=1)

    lbl_icon = ctk.CTkLabel(row, text=icon, font=("Segoe UI Emoji", 15), width=28, anchor="center")
    lbl_icon.grid(row=0, column=0, padx=(10, 8))

    lbl_text = ctk.CTkLabel(row, text=label, font=("Arial", 12, "bold"), text_color=C["nav_fg"], anchor="w")
    lbl_text.grid(row=0, column=1)

    if show_badge:
        badge = ctk.CTkLabel(row, text="0", font=("Arial", 10, "bold"),
                             fg_color="#3a2e00", text_color=C["warn_yellow"],
                             corner_radius=8, width=24, height=16)
        _nav_meta["editor_badge_lbl"] = badge
        badge.grid(row=0, column=2, sticky="e", padx=(0, 10))
        badge.grid_remove()

    def _on_click(e=None):
        if key != "logs":
            _set_active_nav(key)
        command()

    def on_enter(_):
        if key != _active_nav_key: row.configure(fg_color=C["nav_hover"])

    def on_leave(e):
        if key != _active_nav_key: row.configure(fg_color="transparent")

    for w in (row, lbl_icon, lbl_text):
        w.bind("<Enter>", on_enter)
        w.bind("<Leave>", on_leave)
        w.bind("<Button-1>", _on_click)

    _nav_buttons[key] = row
    return row


def _set_active_nav(key: str) -> None:
    global _active_nav_key
    if _active_nav_key in _nav_buttons:
        _nav_buttons[_active_nav_key].configure(fg_color="transparent")
        for child in _nav_buttons[_active_nav_key].winfo_children():
            if isinstance(child, ctk.CTkLabel) and child.cget("anchor") == "w":
                child.configure(text_color=C["nav_fg"])
    _active_nav_key = key
    if key in _nav_buttons:
        _nav_buttons[key].configure(fg_color=C["nav_active"])
        for child in _nav_buttons[key].winfo_children():
            if isinstance(child, ctk.CTkLabel) and child.cget("anchor") == "w":
                child.configure(text_color=C["nav_active_fg"])


# ---------------------------------------------------------------------------
# PANEL SWITCHER ТА ВІДМАЛЬОВКА ВКЛАДКИ
# ---------------------------------------------------------------------------
_panels: dict[str, ctk.CTkFrame] = {}
_active_panel_key: str = ""

# Кешований об'єкт шрифту для вимірювання тексту вкладки — без update_idletasks()
_tab_font_obj: Font | None = None


def _update_tab_shape(title: str) -> None:
    global _tab_font_obj
    slant = 20
    pad_right = 16
    pad_left = 14

    # Ліниво ініціалізуємо Font-об'єкт один раз
    if _tab_font_obj is None:
        _tab_font_obj = Font(family="Arial", size=14, weight="bold")

    # Font.measure() — синхронний, не потребує update_idletasks()
    text_w = _tab_font_obj.measure(title)

    tab_w = text_w + pad_left + pad_right + slant
    h = 58

    tab_canvas.configure(width=tab_w, height=h)

    tab_canvas.coords(tab_poly,
                      slant, 0,
                      tab_w, 0,
                      tab_w, h,
                      0, h,
                      )

    tab_canvas.coords(tab_text, tab_w - pad_right, h // 2)
    tab_canvas.itemconfig(tab_text, text=title, anchor="e")


def _show_panel(key: str) -> None:
    global _active_panel_key
    if _active_panel_key in _panels:
        _panels[_active_panel_key].grid_remove()
    _active_panel_key = key
    if key in _panels:
        _panels[key].grid()

    titles = {"overview": "Огляд", "editor": "Редактор"}
    _update_tab_shape(titles.get(key, ""))


# ---------------------------------------------------------------------------
# ОСНОВНІ ДІЇ
# ---------------------------------------------------------------------------
def action_scan():
    def task():
        main.run_scan()
        root.after(0, refresh_stats)

    run_in_thread(task)


def action_sync():
    def task():
        main.run_sync()

    run_in_thread(task)


def action_html():
    def task():
        need_update = True
        if os.path.exists(HTML_PATH) and os.path.exists(DB_PATH):
            if os.path.getmtime(HTML_PATH) > os.path.getmtime(DB_PATH):
                import re
                try:
                    with open(HTML_PATH, "r", encoding="utf-8") as f:
                        head = f.read(2048)
                    m = re.search(r'<meta\s+name="app-version"\s+content="([^"]+)"', head)
                    if m and m.group(1) == APP_VERSION:
                        need_update = False
                except Exception:
                    pass
        if need_update:
            build_html.generate_html()
        webbrowser.open("file://" + os.path.realpath(HTML_PATH))

    run_in_thread(task)


def action_logs():
    if not os.path.exists("logs"):
        os.makedirs("logs")
    os.startfile(os.path.realpath("logs"))


def action_open_sheet():
    sheet_url = os.getenv("GOOGLE_SHEET_URL")
    if sheet_url:
        print("🌐 Відкриття Google Таблиці у браузері...")
        webbrowser.open(sheet_url)
    else:
        print("❌ Помилка: GOOGLE_SHEET_URL не знайдено у файлі .env")


# ---------------------------------------------------------------------------
# PANEL: OVERVIEW
# ---------------------------------------------------------------------------
def _build_overview_panel(parent: ctk.CTkFrame) -> ctk.CTkFrame:
    panel = ctk.CTkFrame(parent, fg_color="transparent")
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(1, weight=1)

    cards = ctk.CTkFrame(panel, fg_color="transparent")
    cards.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
    cards.columnconfigure((0, 1, 2), weight=1)

    def _card(col, title, sub_default, sub_color=None):
        card = ctk.CTkFrame(cards, fg_color=C["stat_bg"], corner_radius=8, border_width=1,
                            border_color=C["stat_brd"])
        card.grid(row=0, column=col, sticky="ew", padx=5, pady=2)
        ctk.CTkLabel(card, text=title, font=("Arial", 9, "bold"), text_color=C["text_dim"], anchor="w").pack(
            anchor="w", padx=12, pady=(6, 0))
        val = ctk.CTkLabel(card, text="—", font=("Arial", 16, "bold"), text_color=C["text_primary"], anchor="w")
        val.pack(anchor="w", padx=12, pady=(0, 2))
        sub = ctk.CTkLabel(card, text=sub_default, font=("Arial", 11),
                           text_color=sub_color or C["text_muted"], anchor="w")
        sub.pack(anchor="w", padx=12, pady=(0, 6))
        return val, sub

    global lbl_total, lbl_unrec, lbl_last_scan, lbl_status_card_sub
    lbl_total, _ = _card(0, "ФАЙЛІВ У БАЗІ", "у базі даних")
    lbl_unrec, lbl_status_card_sub = _card(1, "СТАТУС", "Завантаження...", C["text_muted"])
    lbl_last_scan, _ = _card(2, "ОСТАННІЙ СКАН", "—")

    console_outer = ctk.CTkFrame(panel, fg_color=C["console_bg"], corner_radius=10, border_width=1,
                                 border_color=C["console_brd"])
    console_outer.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))
    console_outer.columnconfigure(0, weight=1)
    console_outer.rowconfigure(1, weight=1)

    ctopbar = ctk.CTkFrame(console_outer, fg_color=C["console_topbar"], corner_radius=0, height=30)
    ctopbar.grid(row=0, column=0, sticky="ew")
    ctopbar.grid_propagate(False)

    def _copy():
        root.clipboard_clear()
        root.clipboard_append(console.get("1.0", "end-1c"))
        copy_btn.configure(text="✅ Скопійовано", text_color=C["ok_green"])
        root.after(2000, lambda: copy_btn.configure(text="📋 Копіювати", text_color=C["nav_fg"]))

    copy_btn = ctk.CTkButton(ctopbar, text="📋 Копіювати", command=_copy, width=110, height=22, font=("Arial", 11),
                             fg_color="#1c1c1c", text_color=C["nav_fg"], corner_radius=5)
    copy_btn.place(relx=1.0, rely=0.5, anchor="e", x=-8)

    global stop_btn
    stop_btn = ctk.CTkButton(
        ctopbar, text="🛑 Зупинити",
        command=lambda: cancel_event.set(),  # Піднімаємо прапорець зупинки
        width=100, height=22, font=("Arial", 11, "bold"),
        fg_color="#6b2121", hover_color="#8f2a2a", text_color="white", corner_radius=5
    )

    global console
    console = tk.Text(
        console_outer,
        font=("Consolas", 12),
        bg=C["console_bg"],
        fg=C["text_primary"],
        bd=0,
        highlightthickness=0,
        relief="flat",
        wrap="word",
        state="disabled",
        padx=10, pady=10
    )
    console.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))

    return panel


# ---------------------------------------------------------------------------
# PANEL: EDITOR  — оптимізована версія
# ---------------------------------------------------------------------------
def _build_editor_panel(parent: ctk.CTkFrame) -> ctk.CTkFrame:
    panel = ctk.CTkFrame(parent, fg_color=C["editor_bg"])
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(2, weight=1)

    toolbar = ctk.CTkFrame(panel, fg_color="transparent")
    toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(24, 6))
    toolbar.columnconfigure(1, weight=1)

    search_var = tk.StringVar()
    ctk.CTkEntry(toolbar, textvariable=search_var, placeholder_text="Пошук...", height=34).grid(
        row=0, column=1, sticky="ew", padx=(0, 10))

    ctk.CTkButton(
        toolbar, text="✨ Виправити вибрані",
        fg_color=C["nav_active"], hover_color=C["gemini_hover"],
        text_color=C["blue_text"],
        font=("Arial", 12, "bold"), height=34, width=190,
        command=lambda: _process_selected()
    ).grid(row=0, column=2)

    header_f = ctk.CTkFrame(panel, fg_color=C["editor_header"], height=32, corner_radius=6)
    header_f.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
    header_f.pack_propagate(False)

    tk.Label(header_f, text="", bg=C["editor_header"], width=4).pack(side="left")
    tk.Label(header_f, text="Файл", bg=C["editor_header"], fg=C["text_primary"],
             font=("Arial", 10, "bold"), width=38, anchor="w").pack(side="left")
    tk.Label(header_f, text="", bg=C["editor_header"], fg=C["text_primary"],
             font=("Arial", 10, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
    tk.Label(header_f, text="Розпізнано як", bg=C["editor_header"], fg=C["text_primary"],
             font=("Arial", 10, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
    tk.Label(header_f, text="Рік / ID / URL (підказка)", bg=C["editor_header"], fg=C["text_primary"],
             font=("Arial", 10, "bold")).pack(side="right", padx=16)

    scroll_wrap = ctk.CTkFrame(panel, fg_color="transparent")
    scroll_wrap.grid(row=2, column=0, sticky="nsew", padx=16)
    scroll_wrap.columnconfigure(0, weight=1)
    scroll_wrap.rowconfigure(0, weight=1)

    canvas = tk.Canvas(scroll_wrap, bg=C["editor_bg"], highlightthickness=0, bd=0)
    scrollbar = ctk.CTkScrollbar(scroll_wrap, orientation="vertical", command=canvas.yview, fg_color="transparent")
    scroll_frame = tk.Frame(canvas, bg=C["editor_bg"])

    scroll_window_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

    canvas._last_w = 0

    def _on_canvas_configure(e):
        if e.width == canvas._last_w:
            return
        canvas._last_w = e.width
        canvas.itemconfig(scroll_window_id, width=e.width)

    scroll_frame._last_h = 0

    def _on_frame_configure(e):
        if e.height == scroll_frame._last_h:
            return
        scroll_frame._last_h = e.height
        canvas.configure(scrollregion=canvas.bbox("all"))

    canvas.bind("<Configure>", _on_canvas_configure)
    scroll_frame.bind("<Configure>", _on_frame_configure)

    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ✅ CTk забороняє bind_all на своїх віджетах, тому використовуємо Enter/Leave:
    # при вході курсора в зону Editor-скролу — вішаємо обробник на рівні root через
    # чистий tk (tk.Misc.bind обходить CTk-перевірку), при виході — знімаємо.
    # Це стандартна практика для CTk-сумісного глобального скролу.
    _scroll_bound = [False]

    def _bind_scroll(e=None):
        if not _scroll_bound[0]:
            tk.Misc.bind(root, "<MouseWheel>", _on_mousewheel, add="+")
            _scroll_bound[0] = True

    def _unbind_scroll(e=None):
        if _scroll_bound[0]:
            tk.Misc.bind(root, "<MouseWheel>", lambda e: None)
            _scroll_bound[0] = False

    canvas.bind("<Enter>", _bind_scroll)
    canvas.bind("<Leave>", _unbind_scroll)
    scroll_frame.bind("<Enter>", _bind_scroll)
    scroll_frame.bind("<Leave>", _unbind_scroll)
    # Прямий bind на canvas і scroll_frame — fallback
    canvas.bind("<MouseWheel>", _on_mousewheel)
    scroll_frame.bind("<MouseWheel>", _on_mousewheel)

    check_vars: dict[str, tk.BooleanVar] = {}
    hint_vars: dict[str, tk.StringVar] = {}
    all_rows: list = []

    # ✅ ОПТИМІЗАЦІЯ: dirty flag — перезавантаження з БД тільки коли потрібно
    _state = {"db_loaded": False, "db_mtime": 0.0}

    def _load_db_if_needed():
        nonlocal all_rows
        try:
            current_mtime = os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else 0.0
        except OSError:
            current_mtime = 0.0

        if _state["db_loaded"] and _state["db_mtime"] == current_mtime:
            return  # БД не змінювалась — пропускаємо зайвий SQL

        if not os.path.exists(DB_PATH):
            return

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT filename, title_ua, title_en, year FROM movies ORDER BY rowid DESC")
        all_rows = cur.fetchall()
        conn.close()

        # Ініціалізуємо тільки нові ключі, не скидаємо вже виставлені чекбокси
        for f, *_ in all_rows:
            if f not in check_vars:
                check_vars[f] = tk.BooleanVar()
                hint_vars[f] = tk.StringVar()

        _state["db_loaded"] = True
        _state["db_mtime"] = current_mtime

    # ✅ ОПТИМІЗАЦІЯ: пул віджетів рядків — reuse замість destroy/create
    # Зберігаємо посилання на існуючі рядки для перевикористання
    _row_pool: list[dict] = []

    def _get_or_create_row(index: int) -> dict:
        """Повертає існуючий або новий словник з віджетами рядка."""
        if index < len(_row_pool):
            return _row_pool[index]

        bg = C["editor_row"]  # Placeholder, буде оновлено в _render()

        row_f = tk.Frame(scroll_frame, bg=bg, pady=4)

        cb = tk.Label(
            row_f,
            text="",
            font=("Segoe UI Symbol", 14, "bold"),
            width=2, height=1,
            bg=C["editor_input"],
            fg="white",
            bd=0,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=C["sidebar_brd"]
        )
        cb.pack(side="left", padx=(12, 8), pady=4)

        lbl_f = tk.Label(row_f, text="", bg=bg, fg=C["text_normal"], font=("Consolas", 12), width=40, anchor="w")
        lbl_f.pack(side="left")

        lbl_arr = tk.Label(row_f, text="➜", bg=bg, fg=C["text_dim"], width=3)
        lbl_arr.pack(side="left")

        lbl_title = tk.Label(row_f, text="", bg=bg, fg=C["blue_text"], font=("Arial", 12, "bold"), anchor="w")
        lbl_title.pack(side="left", fill="x", expand=True)

        hint_e = tk.Entry(
            row_f,
            bg=C["editor_input"], fg=C["text_primary"],
            insertbackground="white", bd=0, highlightthickness=1,
            highlightbackground=C["sidebar_brd"], font=("Arial", 11), width=18
        )
        hint_e.pack(side="right", padx=16, pady=2, ipady=3)

        widgets = {
            "frame": row_f, "cb": cb, "lbl_f": lbl_f,
            "lbl_arr": lbl_arr, "lbl_title": lbl_title, "hint_e": hint_e,
            "fname": None,  # Поточний fname прив'язаний до цього рядка
        }
        _row_pool.append(widgets)
        return widgets

    def _render(rows: list) -> None:
        """
        Оптимізований рендер: reuse існуючих tk-віджетів, hide зайвих.
        Замість destroy/create O(n) — тільки configure() на існуючих.
        """
        needed = len(rows)
        pool_size = len(_row_pool)

        # 1. Розширюємо пул якщо потрібно більше рядків
        for i in range(pool_size, needed):
            _get_or_create_row(i)

        # 2. Оновлюємо дані в існуючих рядках (тільки configure, без destroy)
        for i, (fname, t_ua, t_en, yr) in enumerate(rows):
            w = _row_pool[i]
            bg = C["editor_row"] if i % 2 == 0 else C["editor_row_alt"]

            # Оновлюємо fname прив'язку тільки якщо вона змінилась
            if w["fname"] != fname:
                w["fname"] = fname

                # Перев'язуємо чекбокс до нового fname
                cb = w["cb"]
                cb.bind("<Button-1>", lambda e, l=cb, f=fname: _toggle_cb(l, f))

                # Прив'язуємо Entry до нової StringVar
                w["hint_e"].configure(textvariable=hint_vars[fname])

            # Оновлюємо візуальний стан
            is_selected = check_vars[fname].get()
            w["cb"].configure(
                text="✔" if is_selected else "",
                highlightbackground=C["editor_input"] if is_selected else C["sidebar_brd"]
            )

            short_fname = fname if len(fname) <= 40 else fname[:37] + "…"
            title_text = f"{t_ua or t_en} ({yr})"

            # Оновлюємо лейбли тільки якщо текст змінився (економимо configure-calls)
            if w["lbl_f"].cget("text") != short_fname:
                w["lbl_f"].configure(text=short_fname, bg=bg)
            if w["lbl_title"].cget("text") != title_text:
                w["lbl_title"].configure(text=title_text, bg=bg)

            w["frame"].configure(bg=bg)
            w["lbl_arr"].configure(bg=bg)

            # Показуємо рядок якщо він був захований
            if not w["frame"].winfo_ismapped():
                w["frame"].pack(fill="x")

        # 3. Ховаємо зайві рядки з пулу (замість destroy)
        for i in range(needed, len(_row_pool)):
            w = _row_pool[i]
            if w["frame"].winfo_ismapped():
                w["frame"].pack_forget()

    def _toggle_cb(label_widget, f_key):
        new_val = not check_vars[f_key].get()
        check_vars[f_key].set(new_val)
        if new_val:
            label_widget.configure(text="✔", bg=C["editor_input"], fg="white",
                                   highlightbackground=C["editor_input"])
        else:
            label_widget.configure(text="", bg=C["editor_input"],
                                   highlightbackground=C["sidebar_brd"])

    # ✅ ОПТИМІЗАЦІЯ: debounce для пошуку — не рендеримо на кожен символ
    _filter_after_id = [None]

    def _filter(*_):
        if _filter_after_id[0] is not None:
            root.after_cancel(_filter_after_id[0])

        def _do_filter():
            q = search_var.get().lower()
            filtered = (
                [r for r in all_rows if q in r[0].lower() or q in (r[1] or r[2] or "").lower()]
                if q else all_rows
            )
            _render(filtered)
            _filter_after_id[0] = None

        # 120ms debounce — непомітно для юзера, але знімає навантаження при швидкому друку
        _filter_after_id[0] = root.after(120, _do_filter)

    search_var.trace_add("write", _filter)

    def _process_selected():
        sel = [{"filename": f, "hint": hint_vars[f].get().strip()} for f, v in check_vars.items() if v.get()]
        if not sel:
            return

        _show_panel("overview")
        _set_active_nav("scan")

        def task():
            main.fix_recognition(sel)

            def _update_ui_after_fix():
                for item in sel:
                    fname = item["filename"]
                    if fname in check_vars:
                        check_vars[fname].set(False)
                    if fname in hint_vars:
                        hint_vars[fname].set("")

                refresh_stats()

                _state["db_loaded"] = False
                _reload_funcs["editor"]()

            root.after(0, _update_ui_after_fix)

        run_in_thread(task)

    def _reload():
        _load_db_if_needed()
        _filter()

    _reload_funcs["editor"] = _reload

    # Перше завантаження
    _reload()

    # Зберігаємо reload як метод панелі для зворотної сумісності
    panel.reload = _reload

    return panel


# ---------------------------------------------------------------------------
# AppID для Taskbar
# ---------------------------------------------------------------------------
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"my.custom.movielist.app.{APP_VERSION}")
except Exception:
    pass

# ---------------------------------------------------------------------------
# ГОЛОВНЕ ВІКНО
# ---------------------------------------------------------------------------
root = ctk.CTk()

# ✅ Style ініціалізується ПІСЛЯ root = ctk.CTk(), інакше Python автоматично
# створює дефолтний Tk() як implicit root — він і з'являється як зайве біле вікно.
_ttk_style = ttk.Style(root)
_ttk_style.theme_use("clam")
_ttk_style.configure("TCheckbutton",
                      background=C["editor_row"],
                      foreground="white",
                      padding=[8, 0, 0, 0])
_ttk_style.map("TCheckbutton",
               background=[("active", C["editor_row"])],
               indicatorcolor=[
                   ("selected", C["accent"]),
                   ("!selected", C["editor_input"])
               ],
               focuscolor=[("active", C["editor_row"])])

root.title(f"MovieList {APP_VERSION}")
_center_window(root, 1100, 650)
root.minsize(860, 540)
root.configure(fg_color=C["bg"])
root.update()
_apply_dark_titlebar(root)

try:
    root.iconbitmap("logo.ico")
except Exception:
    pass

layout = ctk.CTkFrame(root, fg_color="transparent")
layout.pack(fill="both", expand=True)
layout.columnconfigure(1, weight=1)
layout.rowconfigure(0, weight=1)

sidebar = ctk.CTkFrame(layout, fg_color=C["sidebar_bg"], corner_radius=0, width=220)
sidebar.grid(row=0, column=0, sticky="nsew")
sidebar.pack_propagate(False)

# --- БЛОК ІЗ CANVAS ВКЛАДКОЮ ---
sidebar_header = ctk.CTkFrame(sidebar, fg_color="transparent", height=58)
sidebar_header.pack(fill="x")
sidebar_header.pack_propagate(False)

tab_canvas = tk.Canvas(sidebar_header, bg=C["sidebar_bg"], highlightthickness=0, bd=0)
tab_canvas.pack(side="right")

tab_poly = tab_canvas.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, fill=C["nav_active"], outline="")
tab_text = tab_canvas.create_text(0, 0, text="", fill=C["blue_text"], font=("Arial", 14, "bold"), anchor="e")

ctk.CTkFrame(sidebar, fg_color=C["sidebar_brd"], height=1).pack(fill="x")

nav_f = ctk.CTkFrame(sidebar, fg_color="transparent")
nav_f.pack(fill="x", pady=10)


def _sect(t):
    ctk.CTkLabel(nav_f, text=t, font=("Arial", 9, "bold"), text_color=C["text_dim"], anchor="w").pack(
        fill="x", padx=16, pady=(8, 2))


_make_nav_item(nav_f, "scan", "🔍", "Оновити базу", action_scan)
_make_nav_item(nav_f, "sync", "☁️", "Синхронізувати", action_sync)
_make_nav_item(nav_f, "sheet", "📊", "Відкрити таблицю", action_open_sheet)
_make_nav_item(nav_f, "html", "🎬", "Відкрити вітрину", action_html)

_sect("ІНСТРУМЕНТИ")
_make_nav_item(nav_f, "editor", "✏️", "Редактор",
               lambda: (_show_panel("editor"), _panels["editor"].reload()),
               show_badge=True)
_make_nav_item(nav_f, "logs", "📁", "Папка з логами", action_logs)

copyright_lbl = ctk.CTkLabel(
    sidebar,
    text=f"© {datetime.now().year} {GITHUB_NAME}",
    font=("Arial", 10),
    text_color=C["text_dim"],
    cursor="hand2"
)
copyright_lbl.pack(side="bottom", pady=8)
copyright_lbl.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))

main_area = ctk.CTkFrame(layout, fg_color=C["bg"], corner_radius=0)
main_area.grid(row=0, column=1, sticky="nsew")
main_area.columnconfigure(0, weight=1)

main_area.rowconfigure(0, weight=0)
main_area.rowconfigure(1, weight=1)

pb_wrap = ctk.CTkFrame(main_area, fg_color=C["sidebar_brd"], height=3)
pb_wrap.grid(row=0, column=0, sticky="new")
pb_wrap.grid_propagate(False)
progress_bar = ctk.CTkProgressBar(pb_wrap, height=3, progress_color=C["progress"])
progress_bar.set(0)

content_area = ctk.CTkFrame(main_area, fg_color="transparent")
content_area.grid(row=1, column=0, sticky="nsew")
content_area.columnconfigure(0, weight=1)
content_area.rowconfigure(0, weight=1)

_panels["overview"] = _build_overview_panel(content_area)
_panels["editor"] = _build_editor_panel(content_area)

for p in _panels.values():
    p.grid(row=0, column=0, sticky="nsew")
    p.grid_remove()

sys.stdout, sys.stderr = TextRedirector(), TextRedirector()
root.after(100, _process_log_queue)
_show_panel("overview")
refresh_stats()
root.mainloop()