import json
import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import logging
import threading
from PIL import Image, ImageDraw
try:
    from plyer import notification
except ImportError:
    notification = None
try:
    import pystray
except ImportError:
    pystray = None
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
import platform
import subprocess

class FileSorterApp:
    """
    Умный сортировщик файлов с поддержкой авто-сортировки, логирования, трея и расширяемых опций.
    """
    ACTIONS = ["Переместить", "Копировать", "Переименовать", "Удалить"]
    ACTION_MAP = {
        "Переместить": "move",
        "Копировать": "copy",
        "Переименовать": "rename",
        "Удалить": "delete"
    }
    KNOWN_EXTENSIONS = {
        ".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".mp3", ".wav",
        ".ogg", ".flac", ".mp4", ".avi", ".mkv", ".mov", ".zip", ".rar",
        ".7z", ".tar", ".gz", ".exe", ".msi", ".bat", ".py", ".js", ".html",
        ".css", ".json", ".xml", ".csv", ".tsv", ".md", ".rtf", ".svg"
        # ...add more as needed
    }
    def __init__(self, root):
        self.root = root
        self.root.title("Умный сортировщик файлов")
        self.root.geometry("500x500")
        self.root.resizable(True, True)
        self.config_file = "config.json"
        self.config = self.load_config()
        self.setup_logging()
        self.tray_icon = None
        self.setup_tray_icon()
        self.observer = None
        self.auto_sort_enabled = False
        self.exclusion_patterns = [".*"]  # Пример: скрытые файлы
        self.test_run = False
        self.setup_ui()

    def setup_logging(self):
        logging.basicConfig(
            filename='file_sorter.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            encoding='utf-8'
        )

    def load_config(self):
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            default_config = {
                "target_dirs": {
                    "Images": {"exts": [".jpg", ".png", ".gif"], "action": "Переместить"},
                    "Documents": {"exts": [".pdf", ".docx", ".txt"], "action": "Переместить"},
                    "Music": {"exts": [".mp3", ".wav"], "action": "Переместить"}
                },
                "source_dir": ""
            }
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            return default_config

    def save_config(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    def setup_ui(self):
        style = ttk.Style()
        style.configure("TButton", padding=6, font=('Arial', 10))
        main_frame = ttk.Frame(self.root)
        main_frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=10)
        ttk.Button(main_frame, text="Настройки сортировки", command=self.open_settings).pack(pady=5, fill=tk.X)
        ttk.Button(main_frame, text="Выполнить сортировку", command=self.sort_files).pack(pady=5, fill=tk.X)
        ttk.Button(main_frame, text="Выбрать файлы для сортировки", command=self.select_files_for_sorting).pack(pady=5, fill=tk.X)
        self.auto_sort_btn = ttk.Button(main_frame, text="Включить авто-сортировку", command=self.toggle_auto_sort)
        self.auto_sort_btn.pack(pady=5, fill=tk.X)
        ttk.Button(main_frame, text="Просмотреть лог", command=self.show_log_viewer).pack(pady=5, fill=tk.X)
        ttk.Button(main_frame, text="Вернуть файлы из подпапки", command=self.return_from_subfolder).pack(pady=5, fill=tk.X)
        ttk.Button(main_frame, text="Удалить подпапку", command=self.delete_subfolder).pack(pady=5, fill=tk.X)
        # Test run checkbox
        self.test_run_var = tk.BooleanVar(value=self.test_run)
        test_run_cb = ttk.Checkbutton(main_frame, text="Тестовый режим (без изменений)", variable=self.test_run_var, command=self.toggle_test_run)
        test_run_cb.pack(pady=5, anchor=tk.W)
        # Status bar
        self.status_var = tk.StringVar(value="Готово.")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def setup_tray_icon(self):
        if pystray is None:
            return
        def create_image():
            image = Image.new('RGB', (64, 64), color=(0, 128, 255))
            d = ImageDraw.Draw(image)
            d.rectangle([16, 16, 48, 48], fill=(255, 255, 255))
            return image
        image = create_image()
        menu = pystray.Menu(pystray.MenuItem('Выход', self.quit_app))
        self.tray_icon = pystray.Icon("filesorter", image, "FileSorterApp", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def quit_app(self, icon, item):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()

    def show_notification(self, title, message):
        try:
            if notification:
                notification.notify(title=title, message=message, app_name="FileSorterApp")
            elif self.tray_icon:
                self.tray_icon.notify(message, title)
            elif platform.system() == "Darwin":
                # macOS native notification
                try:
                    subprocess.run([
                        "osascript", "-e",
                        f'display notification "{message}" with title "{title}"'
                    ], check=True)
                except Exception as e:
                    logging.error(f"Ошибка показа уведомления через osascript: {e}")
                    print(f"[{title}] {message} (уведомление не поддерживается)")
            else:
                print(f"[{title}] {message}")
        except Exception as e:
            logging.error(f"Ошибка показа уведомления: {e}")
            print(f"[{title}] {message} (уведомление не поддерживается)")

    def perform_action(self, src, dst, action, file_name, folder, auto=False):
        """Выполнить действие над файлом и логировать результат."""
        try:
            if action == "Переместить":
                if not self.test_run:
                    shutil.move(src, dst)
                logging.info(f"Файл '{file_name}' перемещён в '{folder}'{' (авто)' if auto else ''}")
            elif action == "Копировать":
                if not self.test_run:
                    shutil.copy2(src, dst)
                logging.info(f"Файл '{file_name}' скопирован в '{folder}'{' (авто)' if auto else ''}")
            elif action == "Переименовать":
                base, extn = os.path.splitext(file_name)
                new_name = base + "_renamed" + extn
                dst = os.path.join(os.path.dirname(dst), new_name)
                if not self.test_run:
                    shutil.move(src, dst)
                logging.info(f"Файл '{file_name}' переименован и перемещён в '{folder}' как '{new_name}'{' (авто)' if auto else ''}")
            elif action == "Удалить":
                if not self.test_run:
                    os.remove(src)
                logging.info(f"Файл '{file_name}' удалён{' (авто)' if auto else ''}")
            return True
        except Exception as e:
            logging.error(f"Ошибка при обработке файла '{file_name}': {str(e)}")
            self.show_notification("Ошибка", f"{file_name}: {str(e)}")
            return False

    def is_excluded(self, file_name):
        """Проверить, исключён ли файл по паттернам."""
        for pattern in self.exclusion_patterns:
            if pattern == ".*" and file_name.startswith('.'):
                return True
            # Можно добавить другие паттерны
        return False

    def sort_files(self):
        """Сортировка всех файлов в исходной папке согласно настройкам."""
        source_dir = self.config.get("source_dir", "")
        if not source_dir or not os.path.exists(source_dir):
            messagebox.showerror("Ошибка", "Папка для сортировки не указана или не существует!")
            logging.error("Папка для сортировки не указана или не существует!")
            self.show_notification("Ошибка", "Папка для сортировки не указана или не существует!")
            return
        try:
            affected_files = 0
            ext_to_info = {}
            for folder, info in self.config["target_dirs"].items():
                exts = info["exts"] if isinstance(info, dict) else info
                action = info["action"] if isinstance(info, dict) else "Переместить"
                for ext in exts:
                    ext = ext.strip().lower()
                    if not ext.startswith("."):
                        ext = "." + ext
                    ext_to_info[ext] = (folder, action)
            with os.scandir(source_dir) as entries:
                for entry in entries:
                    if entry.is_file():
                        file_name = entry.name
                        if self.is_excluded(file_name):
                            continue
                        ext = os.path.splitext(file_name)[1].lower()
                        info = ext_to_info.get(ext)
                        if info:
                            folder, action = info
                            src = entry.path
                            if action != "Удалить":
                                target_dir = os.path.join(source_dir, folder)
                                os.makedirs(target_dir, exist_ok=True)
                                dst = os.path.join(target_dir, file_name)
                            else:
                                target_dir = None
                                dst = None
                            if self.perform_action(src, dst, action, file_name, folder):
                                affected_files += 1
            msg = f"(Тест) Обработано {affected_files} файлов!" if self.test_run else f"Обработано {affected_files} файлов!"
            messagebox.showinfo("Готово", msg)
            logging.info(msg)
            self.show_notification("Готово", msg)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Произошла ошибка: {str(e)}")
            logging.error(f"Произошла ошибка: {str(e)}")
            self.show_notification("Ошибка", f"Произошла ошибка: {str(e)}")

    def open_settings(self):
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Настройки сортировки")
        self.settings_window.geometry("750x550")
        self.settings_window.grab_set()  # Disable main window

        # Source folder panel
        source_panel = ttk.Frame(self.settings_window)
        source_panel.pack(pady=10, fill=tk.X, padx=10)
        ttk.Label(source_panel, text="Папка для сортировки:").pack(anchor=tk.W)
        self.source_var = tk.StringVar(value=self.config["source_dir"])
        source_entry = ttk.Entry(source_panel, textvariable=self.source_var, width=50)
        source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(source_panel, text="Обзор", command=self.browse_source).pack(side=tk.RIGHT, padx=5)

        # Formats panel
        formats_panel = ttk.Frame(self.settings_window)
        formats_panel.pack(pady=10, fill=tk.BOTH, expand=True, padx=10)
        ttk.Label(formats_panel, text="Настройка форматов файлов:").pack(anchor=tk.W)
        self.tree = ttk.Treeview(formats_panel, columns=("folder", "extensions", "action"), show="headings", selectmode="browse")
        self.tree.heading("folder", text="Папка")
        self.tree.heading("extensions", text="Расширения (через запятую)")
        self.tree.heading("action", text="Действие")
        self.tree.column("folder", width=150)
        self.tree.column("extensions", width=350)
        self.tree.column("action", width=150)
        self.tree.pack(fill=tk.BOTH, expand=True)
        for folder, info in self.config["target_dirs"].items():
            exts = info["exts"] if isinstance(info, dict) else info
            action = info["action"] if isinstance(info, dict) else "Переместить"
            self.tree.insert("", tk.END, values=(folder, ", ".join(exts), action))
        self.tree.bind("<Double-1>", self.edit_format)

        # Control panel
        control_panel = ttk.Frame(formats_panel)
        control_panel.pack(pady=5)
        ttk.Button(control_panel, text="Добавить", command=self.add_format).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_panel, text="Удалить", command=self.remove_format).pack(side=tk.LEFT, padx=5)

        # Save/Cancel buttons
        button_panel = ttk.Frame(self.settings_window)
        button_panel.pack(pady=10)
        ttk.Button(button_panel, text="Сохранить", command=lambda: self.save_settings(self.settings_window)).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_panel, text="Отмена", command=self.settings_window.destroy).pack(side=tk.LEFT)

    def browse_source(self):
        folder = filedialog.askdirectory()
        if folder:
            self.source_var.set(folder)

    def add_format(self):
        self.open_format_window("Добавить новый формат", self.save_new_format)

    def edit_format(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        folder, exts, action = self.tree.item(item_id)['values']
        self.open_format_window(
            "Редактировать формат",
            lambda: self.save_edited_format(item_id),
            folder, exts, action
        )

    def open_format_window(self, title, save_command, folder_val="", exts_val="", action_val="Переместить"):
        self.edit_window = tk.Toplevel(self.settings_window)
        self.edit_window.title(title)
        self.edit_window.geometry("400x250")
        self.edit_window.grab_set()
        ttk.Label(self.edit_window, text="Имя папки:").pack(pady=5)
        self.folder_var = tk.StringVar(value=folder_val)
        folder_entry = ttk.Entry(self.edit_window, textvariable=self.folder_var)
        folder_entry.pack(fill=tk.X, padx=10)
        folder_entry.focus_set()
        ttk.Label(self.edit_window, text="Расширения (через запятую):").pack(pady=5)
        self.exts_var = tk.StringVar(value=exts_val)
        ttk.Entry(self.edit_window, textvariable=self.exts_var).pack(fill=tk.X, padx=10)
        ttk.Label(self.edit_window, text="Действие:").pack(pady=5)
        self.action_var = tk.StringVar(value=action_val)
        action_combo = ttk.Combobox(self.edit_window, textvariable=self.action_var, values=self.ACTIONS, state="readonly")
        action_combo.pack(fill=tk.X, padx=10)
        ttk.Button(self.edit_window, text="Сохранить", command=save_command).pack(pady=10)

    def save_new_format(self):
        folder = self.folder_var.get().strip()
        exts = self.exts_var.get().strip()
        action = self.action_var.get().strip()
        if not folder or not exts or not action:
            messagebox.showerror("Ошибка", "Заполните все поля!")
            return
        if any(folder == self.tree.item(child)['values'][0] for child in self.tree.get_children()):
            messagebox.showerror("Ошибка", "Папка с таким именем уже существует!")
            return
        if not self._validate_extensions(exts):
            return
        self.tree.insert("", tk.END, values=(folder, exts, action))
        self.edit_window.destroy()

    def save_edited_format(self, item_id):
        folder = self.folder_var.get().strip()
        exts = self.exts_var.get().strip()
        action = self.action_var.get().strip()
        if not folder or not exts or not action:
            messagebox.showerror("Ошибка", "Заполните все поля!")
            return
        for child in self.tree.get_children():
            if child != item_id and folder == self.tree.item(child)['values'][0]:
                messagebox.showerror("Ошибка", "Папка с таким именем уже существует!")
                return
        if not self._validate_extensions(exts):
            return
        self.tree.item(item_id, values=(folder, exts, action))
        self.edit_window.destroy()

    def _validate_extensions(self, exts):
        """Validate a comma-separated string of extensions. Returns True if valid, else False and shows error."""
        for ext in exts.split(","):
            ext = ext.strip().lower()
            if not ext:
                continue
            if not ext.startswith("."):
                ext = "." + ext
            if not all(c.isalnum() or c == '_' for c in ext[1:]) or not ext[0] == '.':
                messagebox.showerror(
                    "Ошибка",
                    f"Некорректное расширение файла: {ext}. Расширения должны начинаться с точки и содержать только буквы, цифры или подчёркивания."
                )
                logging.error(f"Некорректное расширение файла: {ext}")
                return False
            if ext not in self.KNOWN_EXTENSIONS:
                messagebox.showerror(
                    "Ошибка",
                    f"Расширение {ext} не является стандартным. Проверьте правильность написания."
                )
                logging.error(f"Неизвестное расширение файла: {ext}")
                return False
        return True

    def remove_format(self):
        selected = self.tree.selection()
        if selected:
            self.tree.delete(selected)

    def save_settings(self, window):
        try:
            self.config["source_dir"] = self.source_var.get()
            self.config["target_dirs"] = {}
            for child in self.tree.get_children():
                folder, exts, action = self.tree.item(child)['values']
                ext_list = []
                for ext in exts.split(","):
                    ext = ext.strip().lower()
                    if not ext:
                        continue
                    if not ext.startswith("."):
                        ext = "." + ext
                    if not all(c.isalnum() or c == '_' for c in ext[1:]) or not ext[0] == '.':
                        messagebox.showerror(
                            "Ошибка",
                            f"Некорректное расширение файла: {ext}. Расширения должны начинаться с точки и содержать только буквы, цифры или подчёркивания."
                        )
                        logging.error(f"Некорректное расширение файла: {ext}")
                        return
                    if ext not in self.KNOWN_EXTENSIONS:
                        messagebox.showerror(
                            "Ошибка",
                            f"Расширение {ext} не является стандартным. Проверьте правильность написания."
                        )
                        logging.error(f"Неизвестное расширение файла: {ext}")
                        return
                    ext_list.append(ext)
                self.config["target_dirs"][folder] = {"exts": ext_list, "action": action}
            self.save_config()
            messagebox.showinfo("Сохранено", "Настройки успешно сохранены!")
            logging.info("Настройки успешно сохранены!")
            window.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка сохранения: {str(e)}")
            logging.error(f"Ошибка сохранения: {str(e)}")

    def toggle_auto_sort(self):
        if not self.auto_sort_enabled:
            self.start_auto_sort()
        else:
            self.stop_auto_sort()

    def start_auto_sort(self):
        source_dir = self.config.get("source_dir", "")
        if not source_dir or not os.path.exists(source_dir):
            messagebox.showerror("Ошибка", "Папка для сортировки не указана или не существует!")
            return
        if self.observer:
            self.stop_auto_sort()
        event_handler = self.AutoSortHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, source_dir, recursive=False)
        self.observer.start()
        self.auto_sort_enabled = True
        self.auto_sort_btn.config(text="Отключить авто-сортировку")
        self.show_notification("Авто-сортировка", "Автоматическая сортировка включена.")
        # Process existing files immediately
        self.sort_files()

    def stop_auto_sort(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        self.auto_sort_enabled = False
        self.auto_sort_btn.config(text="Включить авто-сортировку")
        self.show_notification("Авто-сортировка", "Автоматическая сортировка отключена.")

    class AutoSortHandler(FileSystemEventHandler):
        def __init__(self, app):
            self.app = app
        def on_created(self, event):
            if not event.is_directory:
                # Wait a bit for file to be fully written
                time.sleep(0.5)
                self.app.sort_single_file(event.src_path)

    def sort_single_file(self, file_path):
        """Сортировка одного файла (для авто-сортировки)."""
        try:
            source_dir = self.config.get("source_dir", "")
            if not file_path.startswith(source_dir):
                return
            file_name = os.path.basename(file_path)
            if self.is_excluded(file_name):
                return
            ext_to_info = {}
            for folder, info in self.config["target_dirs"].items():
                exts = info["exts"] if isinstance(info, dict) else info
                action = info["action"] if isinstance(info, dict) else "Переместить"
                for ext in exts:
                    ext = ext.strip().lower()
                    if not ext.startswith("."):
                        ext = "." + ext
                    ext_to_info[ext] = (folder, action)
            ext = os.path.splitext(file_name)[1].lower()
            info = ext_to_info.get(ext)
            if info:
                folder, action = info
                if action != "Удалить":
                    target_dir = os.path.join(source_dir, folder)
                    os.makedirs(target_dir, exist_ok=True)
                    dst = os.path.join(target_dir, file_name)
                else:
                    target_dir = None
                    dst = None
                self.perform_action(file_path, dst, action, file_name, folder, auto=True)
                self.show_notification("Авто-сортировка", f"Файл '{file_name}' обработан: {action}")
        except Exception as e:
            logging.error(f"Ошибка авто-сортировки файла '{file_path}': {str(e)}")
            self.show_notification("Ошибка авто-сортировки", f"{os.path.basename(file_path)}: {str(e)}")

    def set_status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def toggle_test_run(self):
        self.test_run = self.test_run_var.get()
        self.set_status("Тестовый режим включён." if self.test_run else "Тестовый режим выключен.")

    def show_log_viewer(self):
        log_win = tk.Toplevel(self.root)
        log_win.title("Просмотр лога")
        log_win.geometry("700x400")
        text = tk.Text(log_win, wrap=tk.NONE, font=("Consolas", 10))
        text.pack(expand=True, fill=tk.BOTH)
        try:
            with open('file_sorter.log', 'r', encoding='utf-8') as f:
                lines = f.readlines()[-100:]
                text.insert(tk.END, ''.join(lines))
        except Exception as e:
            text.insert(tk.END, f"Ошибка чтения лога: {e}")
        text.config(state=tk.DISABLED)
        ttk.Button(log_win, text="Закрыть", command=log_win.destroy).pack(pady=5)

    def select_files_for_sorting(self):
        files = filedialog.askopenfilenames(title="Выберите файлы для сортировки")
        if files:
            self.set_status(f"Сортировка {len(files)} выбранных файлов...")
            self.sort_selected_files(files)
            self.set_status("Готово.")

    def sort_selected_files(self, files):
        try:
            affected_files = 0
            ext_to_info = {}
            for folder, info in self.config["target_dirs"].items():
                exts = info["exts"] if isinstance(info, dict) else info
                action = info["action"] if isinstance(info, dict) else "Переместить"
                for ext in exts:
                    ext = ext.strip().lower()
                    if not ext.startswith("."):
                        ext = "." + ext
                    ext_to_info[ext] = (folder, action)
            for file_path in files:
                file_name = os.path.basename(file_path)
                if self.is_excluded(file_name):
                    continue
                ext = os.path.splitext(file_name)[1].lower()
                info = ext_to_info.get(ext)
                if info:
                    folder, action = info
                    source_dir = self.config.get("source_dir", "")
                    if action != "Удалить":
                        target_dir = os.path.join(source_dir, folder)
                        os.makedirs(target_dir, exist_ok=True)
                        dst = os.path.join(target_dir, file_name)
                    else:
                        target_dir = None
                        dst = None
                    if self.perform_action(file_path, dst, action, file_name, folder):
                        affected_files += 1
            msg = f"(Тест) Обработано {affected_files} файлов!" if self.test_run else f"Обработано {affected_files} файлов!"
            messagebox.showinfo("Готово", msg)
            logging.info(msg)
            self.show_notification("Готово", msg)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Произошла ошибка: {str(e)}")
            logging.error(f"Произошла ошибка: {str(e)}")
            self.show_notification("Ошибка", f"Произошла ошибка: {str(e)}")

    def return_from_subfolder(self):
        source_dir = self.config.get("source_dir", "")
        if not source_dir or not os.path.exists(source_dir):
            messagebox.showerror("Ошибка", "Папка для сортировки не указана или не существует!")
            return
        # List subfolders
        subfolders = [f for f in os.listdir(source_dir) if os.path.isdir(os.path.join(source_dir, f))]
        if not subfolders:
            messagebox.showinfo("Нет подпапок", "В исходной папке нет подпапок.")
            return
        # Dialog to pick subfolder
        pick_win = tk.Toplevel(self.root)
        pick_win.title("Выберите подпапку для возврата файлов")
        pick_win.geometry("350x200")
        tk.Label(pick_win, text="Выберите подпапку:").pack(pady=10)
        subfolder_var = tk.StringVar(value=subfolders[0])
        combo = ttk.Combobox(pick_win, values=subfolders, textvariable=subfolder_var, state="readonly")
        combo.pack(pady=10)
        def do_return():
            subfolder = subfolder_var.get()
            subfolder_path = os.path.join(source_dir, subfolder)
            files = [f for f in os.listdir(subfolder_path) if os.path.isfile(os.path.join(subfolder_path, f))]
            if not files:
                messagebox.showinfo("Пусто", "В выбранной подпапке нет файлов.")
                pick_win.destroy()
                return
            moved = 0
            for f in files:
                src = os.path.join(subfolder_path, f)
                dst = os.path.join(source_dir, f)
                try:
                    if not self.test_run:
                        shutil.move(src, dst)
                    moved += 1
                    logging.info(f"Файл '{f}' возвращён из '{subfolder}' в исходную папку.")
                except Exception as e:
                    logging.error(f"Ошибка возврата файла '{f}': {str(e)}")
            # Delete subfolder if empty
            if not os.listdir(subfolder_path):
                try:
                    if not self.test_run:
                        os.rmdir(subfolder_path)
                    logging.info(f"Папка '{subfolder}' удалена после возврата файлов.")
                except Exception as e:
                    logging.error(f"Ошибка удаления папки '{subfolder}': {str(e)}")
            msg = f"Возвращено {moved} файлов из '{subfolder}'."
            messagebox.showinfo("Готово", msg)
            self.show_notification("Готово", msg)
            self.set_status(msg)
            pick_win.destroy()
        ttk.Button(pick_win, text="Вернуть файлы", command=do_return).pack(pady=10)
        ttk.Button(pick_win, text="Отмена", command=pick_win.destroy).pack()

    def delete_subfolder(self):
        source_dir = self.config.get("source_dir", "")
        if not source_dir or not os.path.exists(source_dir):
            messagebox.showerror("Ошибка", "Папка для сортировки не указана или не существует!")
            return
        # List subfolders
        subfolders = [f for f in os.listdir(source_dir) if os.path.isdir(os.path.join(source_dir, f))]
        if not subfolders:
            messagebox.showinfo("Нет подпапок", "В исходной папке нет подпапок.")
            return
        # Dialog to pick subfolder
        pick_win = tk.Toplevel(self.root)
        pick_win.title("Выберите подпапку для удаления")
        pick_win.geometry("350x200")
        tk.Label(pick_win, text="Выберите подпапку:").pack(pady=10)
        subfolder_var = tk.StringVar(value=subfolders[0])
        combo = ttk.Combobox(pick_win, values=subfolders, textvariable=subfolder_var, state="readonly")
        combo.pack(pady=10)
        def do_delete():
            subfolder = subfolder_var.get()
            subfolder_path = os.path.join(source_dir, subfolder)
            if not os.path.exists(subfolder_path):
                messagebox.showerror("Ошибка", "Папка не найдена.")
                pick_win.destroy()
                return
            if messagebox.askyesno("Подтверждение", f"Удалить подпапку '{subfolder}' и все её содержимое?"):
                try:
                    if not self.test_run:
                        shutil.rmtree(subfolder_path)
                    logging.info(f"Папка '{subfolder}' и все её содержимое удалены.")
                    msg = f"Папка '{subfolder}' удалена."
                    messagebox.showinfo("Готово", msg)
                    self.show_notification("Готово", msg)
                    self.set_status(msg)
                except Exception as e:
                    logging.error(f"Ошибка удаления папки '{subfolder}': {str(e)}")
                    messagebox.showerror("Ошибка", f"Ошибка удаления: {str(e)}")
            pick_win.destroy()
        ttk.Button(pick_win, text="Удалить подпапку", command=do_delete).pack(pady=10)
        ttk.Button(pick_win, text="Отмена", command=pick_win.destroy).pack()

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = FileSorterApp(root)
        root.mainloop()
    except Exception as e:
        import traceback
        try:
            messagebox.showerror("Ошибка запуска", f"Произошла ошибка:\n{e}\n\n{traceback.format_exc()}")
        except Exception:
            print("Ошибка запуска:", e)
            print(traceback.format_exc())
