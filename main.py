import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3
import threading
import os
import sys
import json
import tempfile
import re
import time
import subprocess
import zipfile
import urllib.request

APP_VERSION = "v3.2-CENT134"

# ============================================================
# SELENIUM IMPORTS
# ============================================================
SELENIUM_OK = False
SELENIUM_ERR = ""
try:
    import selenium
    import selenium.webdriver
    import selenium.webdriver.chrome
    import selenium.webdriver.chrome.webdriver
    import selenium.webdriver.chrome.service
    import selenium.webdriver.chrome.options
    import selenium.webdriver.common.by
    import selenium.webdriver.common.keys
    import selenium.webdriver.support.ui
    import selenium.webdriver.support.expected_conditions
    from selenium.webdriver.chrome.webdriver import WebDriver as ChromeDriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    SELENIUM_OK = True
except Exception as _e:
    SELENIUM_ERR = str(_e)


DB = "fb_accounts.db"
COOKIE_FOLDER = os.path.join(os.path.expanduser("~"), "fb_cookies")
DRIVER_CACHE = os.path.join(os.path.expanduser("~"), ".fb_family_manager")

# Chrome 134 base (Cent Browser 5.2.x এর internal)
CHROME_MAJOR = "134"

# ChromeDriver download URLs (try in order)
DRIVER_URLS = [
    # Chrome for Testing (official)
    f"https://storage.googleapis.com/chrome-for-testing-public/134.0.6998.165/win64/chromedriver-win64.zip",
    f"https://storage.googleapis.com/chrome-for-testing-public/134.0.6998.117/win64/chromedriver-win64.zip",
    f"https://storage.googleapis.com/chrome-for-testing-public/134.0.6998.89/win64/chromedriver-win64.zip",
    # Older URLs
    f"https://chromedriver.storage.googleapis.com/134.0.6998.117/chromedriver_win32.zip",
]

# ============================================================
# DARK THEME
# ============================================================
BG_MAIN = "#0d0d0d"
BG_PANEL = "#1a1a1a"
BG_INPUT = "#252525"
BG_HOVER = "#2d2d2d"
FG_TEXT = "#f0f0f0"
FG_LABEL = "#909090"
GREEN = "#00c853"
BLUE = "#2962ff"
ORANGE = "#ff6d00"
PURPLE = "#aa00ff"
RED = "#d50000"


def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            cookie TEXT,
            note TEXT
        )
    """)
    conn.commit()
    conn.close()


def add_account(name, cookie, note=""):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO accounts (name, cookie, note) VALUES (?, ?, ?)",
              (name, cookie, note))
    conn.commit()
    conn.close()


def get_accounts():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, name, cookie, note FROM accounts ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return rows


def delete_account(acc_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
    conn.commit()
    conn.close()


def normalize_cookie(s):
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_cookie(cookie_str):
    jar = {}
    for pair in normalize_cookie(cookie_str).split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            jar[k.strip()] = v.strip()
    return jar


def get_c_user(cookie_str):
    return parse_cookie(cookie_str).get("c_user", "")


# ============================================================
# BROWSER FIND
# ============================================================
def find_cent_browser():
    user = os.path.expanduser("~")
    candidates = [
        os.path.join(user, r"AppData\Local\CentBrowser\Application\chrome.exe"),
        r"C:\Program Files (x86)\CentBrowser\Application\chrome.exe",
        r"C:\Program Files\CentBrowser\Application\chrome.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def find_cached_driver():
    """Look for chromedriver.exe already downloaded."""
    if not os.path.isdir(DRIVER_CACHE):
        return None
    # Search recursively
    for root, dirs, files in os.walk(DRIVER_CACHE):
        if "chromedriver.exe" in files:
            return os.path.join(root, "chromedriver.exe")
    return None


# ============================================================
# CHROMEDRIVER DOWNLOAD
# ============================================================
def download_chromedriver(progress_cb=None):
    """
    Download matching ChromeDriver 134 for Cent Browser 5.2.x.
    Returns path to chromedriver.exe, or None on failure.
    """
    # 1) Check cache first
    cached = find_cached_driver()
    if cached:
        return cached

    os.makedirs(DRIVER_CACHE, exist_ok=True)

    # 2) Try each URL
    for url in DRIVER_URLS:
        try:
            if progress_cb:
                progress_cb(f"Downloading: {url.split('/')[-1]}...")
            zip_path = os.path.join(DRIVER_CACHE, "chromedriver.zip")
            urllib.request.urlretrieve(url, zip_path)

            # Extract
            extract_dir = os.path.join(DRIVER_CACHE, "driver_" + str(int(time.time())))
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)
            try:
                os.remove(zip_path)
            except Exception:
                pass

            # Find chromedriver.exe
            for root, dirs, files in os.walk(extract_dir):
                if "chromedriver.exe" in files:
                    return os.path.join(root, "chromedriver.exe")
        except Exception:
            continue

    # 3) Try webdriver-manager as fallback
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        path = ChromeDriverManager().install()
        return path
    except Exception:
        pass

    return None


# ============================================================
# LAUNCH BROWSER
# ============================================================
def launch_browser(account_name, cookie_str, target_url):
    if not SELENIUM_OK:
        messagebox.showerror("Selenium Error",
            f"Selenium load hoyni:\n{SELENIUM_ERR}")
        return

    browser_path = find_cent_browser()
    if not browser_path:
        messagebox.showerror("Browser",
            "Cent Browser paoa jayni.\nInstall: centbrowser.com")
        return

    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", account_name)[:20]
    profile_dir = os.path.join(
        os.path.expanduser("~"), ".fb_family_manager",
        f"profile_{safe}_{int(time.time())}"
    )
    os.makedirs(profile_dir, exist_ok=True)

    opts = Options()
    opts.binary_location = browser_path
    opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # Ensure driver exists (cached or download)
    driver_path = find_cached_driver()
    if not driver_path:
        driver_path = download_chromedriver()

    driver = None
    if driver_path and os.path.exists(driver_path):
        try:
            service = Service(executable_path=driver_path)
            driver = ChromeDriver(options=opts, service=service)
        except Exception as e1:
            driver = None

    if driver is None:
        # Final fallback: let selenium auto-manage
        try:
            driver = ChromeDriver(options=opts)
        except Exception as e2:
            messagebox.showerror("Browser launch failed",
                f"Error: {e2}\n\n"
                f"Driver: {driver_path or 'not downloaded'}\n"
                f"Cent: {browser_path}\n\n"
                f"Manual fix:\n"
                f"1. Download ChromeDriver 134 from:\n"
                f"https://googlechromelabs.github.io/chrome-for-testing/\n"
                f"2. Extract to:\n{DRIVER_CACHE}")
            return

    try:
        driver.get("https://www.facebook.com/")
        time.sleep(2)
        for k, v in parse_cookie(cookie_str).items():
            try:
                driver.add_cookie({"name": k, "value": v,
                                   "domain": ".facebook.com", "path": "/"})
            except Exception:
                pass
        driver.get(target_url)
    except Exception as e:
        messagebox.showerror("Navigation error", str(e))


# ============================================================
# DARK THEME HELPERS
# ============================================================
def apply_dark_theme(root):
    root.configure(bg=BG_MAIN)
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure("Treeview",
                    background=BG_INPUT, foreground=FG_TEXT,
                    fieldbackground=BG_INPUT, borderwidth=0,
                    rowheight=26)
    style.configure("Treeview.Heading",
                    background=BG_PANEL, foreground=FG_TEXT,
                    borderwidth=0, relief="flat")
    style.map("Treeview",
              background=[("selected", BLUE)],
              foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading",
              background=[("active", BG_HOVER)])


def dark_button(parent, text, color, command, width=14):
    return tk.Button(parent, text=text, bg=color, fg="white",
                     activebackground=color, activeforeground="white",
                     relief="flat", bd=0, width=width,
                     cursor="hand2", command=command,
                     font=("Segoe UI", 9, "bold"))


def dark_label(parent, text):
    return tk.Label(parent, text=text, bg=BG_PANEL,
                    fg=FG_LABEL, font=("Segoe UI", 9))


def dark_entry(parent, width=20):
    return tk.Entry(parent, bg=BG_INPUT, fg=FG_TEXT,
                    insertbackground=FG_TEXT, relief="flat",
                    bd=0, width=width, font=("Segoe UI", 10))


def dark_frame(parent, title=None):
    if title:
        f = tk.LabelFrame(parent, text=title,
                          bg=BG_PANEL, fg=FG_TEXT,
                          bd=1, relief="solid",
                          font=("Segoe UI", 9, "bold"),
                          labelanchor="nw")
    else:
        f = tk.Frame(parent, bg=BG_PANEL)
    return f


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"FB Family Manager  [{APP_VERSION}]")
        self.root.geometry("1180x720")
        self.root.configure(bg=BG_MAIN)
        apply_dark_theme(root)

        self._build_add_frame()
        self._build_table()
        self._build_bottom()
        self.refresh()

        self.root.after(500, self.auto_load_folder)

        if not SELENIUM_OK:
            messagebox.showwarning("Selenium Missing",
                f"Selenium load hoyni:\n{SELENIUM_ERR}")

        # Show driver status
        drv = find_cached_driver()
        status = "OK" if drv else "Not downloaded (will auto on first launch)"
        self.root.title(
            f"FB Family Manager  [{APP_VERSION}]  -  "
            f"Driver: {'Cached' if drv else 'Need download'}")

    def _build_add_frame(self):
        top = dark_frame(self.root, "Add Account")
        top.pack(fill="x", padx=10, pady=8)

        r1 = tk.Frame(top, bg=BG_PANEL)
        r1.pack(fill="x", padx=8, pady=4)

        dark_label(r1, "Name:").pack(side="left", padx=(0, 4))
        self.name_e = dark_entry(r1, width=18)
        self.name_e.pack(side="left", padx=(0, 12))

        dark_label(r1, "Note:").pack(side="left", padx=(0, 4))
        self.note_e = dark_entry(r1, width=25)
        self.note_e.pack(side="left")

        r2 = tk.Frame(top, bg=BG_PANEL)
        r2.pack(fill="x", padx=8, pady=4)

        dark_label(r2, "Cookie:").pack(side="left", anchor="n", padx=(0, 4))
        self.cookie_t = tk.Text(r2, height=2, width=100,
                                bg=BG_INPUT, fg=FG_TEXT,
                                insertbackground=FG_TEXT,
                                relief="flat", bd=0,
                                font=("Consolas", 9))
        self.cookie_t.pack(side="left", fill="x", expand=True)

        r3 = tk.Frame(top, bg=BG_PANEL)
        r3.pack(fill="x", padx=8, pady=6)

        dark_button(r3, "Add Account", GREEN, self.add, 14).pack(side="left", padx=3)
        dark_button(r3, "Paste", BLUE, self.paste_clip, 10).pack(side="left", padx=3)
        dark_button(r3, "Clear", "#424242",
                    lambda: self.cookie_t.delete("1.0", "end"), 8).pack(side="left", padx=3)
        dark_button(r3, "Bulk Import Folder", PURPLE,
                    self.bulk_import_folder, 18).pack(side="left", padx=3)
        dark_button(r3, "Import JSON", "#424242",
                    self.import_json, 12).pack(side="left", padx=3)
        dark_button(r3, "Export JSON", "#424242",
                    self.export, 12).pack(side="left", padx=3)
        dark_button(r3, "Download Driver", "#00897b",
                    self.download_driver_manual, 16).pack(side="left", padx=3)

        tk.Label(top, bg=BG_PANEL, fg=FG_LABEL,
                 text=f"Cookie folder: {COOKIE_FOLDER}   |   "
                      f"Driver cache: {DRIVER_CACHE}",
                 font=("Segoe UI", 8, "italic")).pack(anchor="w", padx=10, pady=(0, 6))

    def _build_table(self):
        mid = dark_frame(self.root, "Accounts")
        mid.pack(fill="both", expand=True, padx=10, pady=6)

        cols = ("id", "name", "user_id", "note")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=14)
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="NAME")
        self.tree.heading("user_id", text="USER_ID")
        self.tree.heading("note", text="NOTE")
        self.tree.column("id", width=50, anchor="center")
        self.tree.column("name", width=180)
        self.tree.column("user_id", width=200)
        self.tree.column("note", width=550)

        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb.pack(side="right", fill="y", pady=6, padx=(0, 6))

    def _build_bottom(self):
        bot = dark_frame(self.root, "Actions")
        bot.pack(fill="x", padx=10, pady=8)

        r1 = tk.Frame(bot, bg=BG_PANEL)
        r1.pack(fill="x", padx=8, pady=4)

        dark_button(r1, "Open FB", GREEN,
                    lambda: self.open_url("https://www.facebook.com/"), 12).pack(side="left", padx=3)
        dark_button(r1, "Ads Manager", BLUE,
                    lambda: self.open_url("https://adsmanager.facebook.com/adsmanager/"), 12).pack(side="left", padx=3)
        dark_button(r1, "Payment", ORANGE, self.open_payment, 12).pack(side="left", padx=3)
        dark_button(r1, "Boost Post", PURPLE,
                    lambda: self.open_url("https://www.facebook.com/adsmanager/creation"), 12).pack(side="left", padx=3)
        dark_button(r1, "Create Page", "#00897b",
                    lambda: self.open_url("https://www.facebook.com/pages/creation/"), 12).pack(side="left", padx=3)
        dark_button(r1, "Professional", "#5e35b1",
                    lambda: self.open_url("https://www.facebook.com/settings/?tab=account"), 12).pack(side="left", padx=3)

        r2 = tk.Frame(bot, bg=BG_PANEL)
        r2.pack(fill="x", padx=8, pady=(0, 6))

        dark_button(r2, "Copy Cookie", "#424242", self.copy_cookie, 12).pack(side="left", padx=3)
        dark_button(r2, "Delete", RED, self.delete, 10).pack(side="left", padx=3)
        dark_button(r2, "Open Cookie Folder", "#424242",
                    self.open_cookie_folder, 18).pack(side="left", padx=3)
        dark_button(r2, "Reload Folder", PURPLE,
                    self.auto_load_folder, 14).pack(side="left", padx=3)
        dark_button(r2, "Open Driver Folder", "#424242",
                    self.open_driver_folder, 18).pack(side="left", padx=3)

        self.tree.bind("<Double-1>",
                       lambda e: self.open_url("https://www.facebook.com/"))

    # -------- DRIVER HELPERS --------
    def download_driver_manual(self):
        def worker():
            self.root.title(f"FB Family Manager  [{APP_VERSION}]  -  Downloading driver...")
            path = download_chromedriver()
            if path:
                messagebox.showinfo("Driver", f"Downloaded:\n{path}")
            else:
                messagebox.showerror("Driver",
                    "Download failed.\n\n"
                    "Manual download:\n"
                    "https://googlechromelabs.github.io/chrome-for-testing/\n\n"
                    "Pick version 134.x, download win64 chromedriver,\n"
                    f"extract chromedriver.exe to:\n{DRIVER_CACHE}")
            self.root.title(
                f"FB Family Manager  [{APP_VERSION}]  -  "
                f"Driver: {'Ready' if path else 'Failed'}")
        threading.Thread(target=worker, daemon=True).start()

    def open_driver_folder(self):
        os.makedirs(DRIVER_CACHE, exist_ok=True)
        try:
            os.startfile(DRIVER_CACHE)
        except Exception:
            messagebox.showinfo("Folder", DRIVER_CACHE)

    # -------- ADD LOGIC --------
    def add(self):
        name = self.name_e.get().strip()
        ck = self.cookie_t.get("1.0", "end").strip()
        note = self.note_e.get().strip()

        if not ck:
            messagebox.showwarning("Missing", "Cookie dite hobe")
            return

        lines = [l.strip() for l in ck.split("\n") if l.strip()]
        if len(lines) > 1:
            n = 0
            for i, line in enumerate(lines, 1):
                if "c_user=" in line:
                    add_account(f"{name or 'Account'}_{i}", line, note)
                    n += 1
            self.cookie_t.delete("1.0", "end")
            self.name_e.delete(0, "end")
            self.note_e.delete(0, "end")
            messagebox.showinfo("Bulk", f"{n} accounts added")
            self.refresh()
            return

        if not name:
            messagebox.showwarning("Missing", "Name dite hobe")
            return

        add_account(name, ck, note)
        self.name_e.delete(0, "end")
        self.note_e.delete(0, "end")
        self.cookie_t.delete("1.0", "end")
        self.refresh()

    def paste_clip(self):
        try:
            self.cookie_t.delete("1.0", "end")
            self.cookie_t.insert("1.0", self.root.clipboard_get())
        except Exception:
            pass

    def open_cookie_folder(self):
        os.makedirs(COOKIE_FOLDER, exist_ok=True)
        try:
            os.startfile(COOKIE_FOLDER)
        except Exception:
            messagebox.showinfo("Folder", COOKIE_FOLDER)

    def auto_load_folder(self):
        os.makedirs(COOKIE_FOLDER, exist_ok=True)
        existing = {r[1] for r in get_accounts()}
        loaded = 0
        for fname in sorted(os.listdir(COOKIE_FOLDER)):
            if not (fname.endswith(".txt") or fname.endswith(".json")):
                continue
            path = os.path.join(COOKIE_FOLDER, fname)
            base = os.path.splitext(fname)[0]
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
            except Exception:
                continue

            if fname.endswith(".json"):
                try:
                    arr = json.loads(content)
                    if isinstance(arr, list):
                        for i, item in enumerate(arr, 1):
                            nm = item.get("name") or f"{base}_{i}"
                            ck = item.get("cookie", "")
                            if ck and "c_user=" in ck and nm not in existing:
                                add_account(nm, ck, "from json")
                                loaded += 1
                        continue
                except Exception:
                    pass

            for line in content.split("\n"):
                line = line.strip()
                if "c_user=" in line and base not in existing:
                    add_account(base, line, "from folder")
                    existing.add(base)
                    loaded += 1
                    break

        self.refresh()
        if loaded:
            messagebox.showinfo("Auto Loaded",
                f"{loaded} accounts loaded from folder")

    def bulk_import_folder(self):
        self.auto_load_folder()

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for r in get_accounts():
            acc_id, name, cookie, note = r
            c_user = get_c_user(cookie)
            self.tree.insert("", "end",
                             values=(acc_id, name, c_user or "?", note))

    def selected_row(self):
        sel = self.tree.selection()
        return self.tree.item(sel[0], "values") if sel else None

    def get_cookie_of_selected(self):
        row = self.selected_row()
        if not row:
            messagebox.showwarning("No selection", "Account select korun")
            return None, None
        acc_id = row[0]
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT name, cookie FROM accounts WHERE id=?", (acc_id,))
        r = c.fetchone()
        conn.close()
        return (r[0], r[1]) if r else (None, None)

    def open_url(self, url):
        name, cookie = self.get_cookie_of_selected()
        if not cookie:
            return
        threading.Thread(target=launch_browser,
                         args=(name, cookie, url),
                         daemon=True).start()

    def open_payment(self):
        url = ("https://adsmanager.facebook.com/adsmanager/"
               "billing_hub/payment_settings")
        custom = simpledialog.askstring("Payment URL",
            "Payment page URL din:", initialvalue="")
        if custom:
            url = custom.strip()
        self.open_url(url)

    def copy_cookie(self):
        name, cookie = self.get_cookie_of_selected()
        if not cookie:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(cookie)
        messagebox.showinfo("Copied", f"{name} cookie copied!")

    def delete(self):
        row = self.selected_row()
        if not row:
            return
        if messagebox.askyesno("Delete", f"Delete '{row[1]}'?"):
            delete_account(row[0])
            self.refresh()

    def import_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            n = 0
            for item in data:
                nm = item.get("name", "").strip()
                ck = item.get("cookie", "").strip()
                if nm and ck:
                    add_account(nm, ck, item.get("note", ""))
                    n += 1
            messagebox.showinfo("Imported", f"{n} accounts added")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = [{"name": r[1], "cookie": r[2], "note": r[3]}
                for r in get_accounts()]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Exported", f"Saved: {path}")


if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    App(root)
    root.mainloop()
