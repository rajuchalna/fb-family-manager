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

DB = "fb_accounts.db"

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

def update_account(acc_id, name, cookie, note):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE accounts SET name=?, cookie=?, note=? WHERE id=?",
              (name, cookie, note, acc_id))
    conn.commit()
    conn.close()

def delete_account(acc_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
    conn.commit()
    conn.close()

def parse_cookie(cookie_str):
    jar = {}
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            jar[k.strip()] = v.strip()
    return jar

def get_c_user(cookie_str):
    jar = parse_cookie(cookie_str)
    return jar.get("c_user", "")

def find_browser():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

def launch_browser_with_cookie(account_name, cookie_str, target_url):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        messagebox.showerror("Missing",
            "Selenium install kora nei.\n\npip install selenium")
        return

    browser_path = find_browser()
    if not browser_path:
        messagebox.showerror("Browser", "Chrome/Edge paoa jaini")
        return

    safe_name = re.sub(r'[^A-Za-z0-9_\-]', '_', account_name)[:20]
    profile_dir = os.path.join(
        os.path.expanduser("~"),
        ".fb_family_manager",
        f"profile_{safe_name}_{int(time.time())}"
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

    try:
        driver = webdriver.Chrome(options=opts)
    except Exception as e:
        messagebox.showerror("Browser launch failed", str(e))
        return

    try:
        driver.get("https://www.facebook.com/")
        time.sleep(1.5)
        for k, v in parse_cookie(cookie_str).items():
            try:
                driver.add_cookie({"name": k, "value": v,
                                   "domain": ".facebook.com", "path": "/"})
            except Exception:
                pass
        driver.get(target_url)
    except Exception as e:
        messagebox.showerror("Navigation error", str(e))

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("FB Family Manager")
        self.root.geometry("1100x680")
        self._build_add_frame()
        self._build_table()
        self._build_bottom()
        self.refresh()

    def _build_add_frame(self):
        top = tk.LabelFrame(self.root, text="Add Account", padx=8, pady=8)
        top.pack(fill="x", padx=10, pady=5)
        tk.Label(top, text="Name:").grid(row=0, column=0, sticky="w")
        self.name_e = tk.Entry(top, width=18)
        self.name_e.grid(row=0, column=1, padx=4)
        tk.Label(top, text="Note:").grid(row=0, column=2, sticky="w")
        self.note_e = tk.Entry(top, width=22)
        self.note_e.grid(row=0, column=3, padx=4)
        tk.Label(top, text="Cookie:").grid(row=1, column=0, sticky="nw", pady=4)
        self.cookie_t = tk.Text(top, width=110, height=4)
        self.cookie_t.grid(row=1, column=1, columnspan=4, pady=4, sticky="we")
        bf = tk.Frame(top)
        bf.grid(row=2, column=0, columnspan=5, pady=4)
        tk.Button(bf, text="Add Account", width=14, bg="#4CAF50",
                  fg="white", command=self.add).pack(side="left", padx=3)
        tk.Button(bf, text="Paste Clipboard", width=14,
                  command=self.paste_clip).pack(side="left", padx=3)
        tk.Button(bf, text="Clear", width=10,
                  command=lambda: self.cookie_t.delete("1.0", "end")
                  ).pack(side="left", padx=3)
        tk.Button(bf, text="Import JSON", width=12,
                  command=self.import_json).pack(side="left", padx=3)
        tk.Button(bf, text="Export JSON", width=12,
                  command=self.export).pack(side="left", padx=3)

    def _build_table(self):
        mid = tk.LabelFrame(self.root, text="Accounts", padx=4, pady=4)
        mid.pack(fill="both", expand=True, padx=10, pady=5)
        cols = ("id", "name", "user_id", "note")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=15)
        for c in cols:
            self.tree.heading(c, text=c.upper())
        self.tree.column("id", width=50, anchor="center")
        self.tree.column("name", width=150)
        self.tree.column("user_id", width=180)
        self.tree.column("note", width=500)
        self.tree.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

    def _build_bottom(self):
        bot = tk.LabelFrame(self.root,
                            text="Actions (double-click row to open FB)",
                            padx=6, pady=6)
        bot.pack(fill="x", padx=10, pady=5)
        tk.Button(bot, text="Open FB", width=14, bg="#4CAF50", fg="white",
                  command=lambda: self.open_url("https://www.facebook.com/")
                  ).pack(side="left", padx=3)
        tk.Button(bot, text="Ads Manager", width=14, bg="#2196F3", fg="white",
                  command=self.open_ads_manager).pack(side="left", padx=3)
        tk.Button(bot, text="Payment", width=14, bg="#FF9800", fg="white",
                  command=self.open_payment).pack(side="left", padx=3)
        tk.Button(bot, text="Boost Post", width=14, bg="#9C27B0", fg="white",
                  command=self.open_boost).pack(side="left", padx=3)
        tk.Button(bot, text="Copy Cookie", width=14,
                  command=self.copy_cookie).pack(side="left", padx=3)
        tk.Button(bot, text="Edit", width=10,
                  command=self.edit).pack(side="left", padx=3)
        tk.Button(bot, text="Delete", width=10, bg="#f44336", fg="white",
                  command=self.delete).pack(side="left", padx=3)
        self.tree.bind("<Double-1>",
                       lambda e: self.open_url("https://www.facebook.com/"))

    def paste_clip(self):
        try:
            data = self.root.clipboard_get()
            self.cookie_t.delete("1.0", "end")
            self.cookie_t.insert("1.0", data)
        except Exception:
            pass

    def add(self):
        name = self.name_e.get().strip()
        ck = self.cookie_t.get("1.0", "end").strip()
        note = self.note_e.get().strip()
        if not name or not ck:
            messagebox.showwarning("Missing", "Name ar Cookie dite hobe")
            return
        add_account(name, ck, note)
        self.name_e.delete(0, "end")
        self.note_e.delete(0, "end")
        self.cookie_t.delete("1.0", "end")
        self.refresh()

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
        if not sel:
            return None
        return self.tree.item(sel[0], "values")

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
        if not r:
            return None, None
        return r[0], r[1]

    def open_url(self, url):
        name, cookie = self.get_cookie_of_selected()
        if not cookie:
            return
        threading.Thread(target=launch_browser_with_cookie,
                         args=(name, cookie, url),
                         daemon=True).start()

    def open_ads_manager(self):
        url = "https://adsmanager.facebook.com/adsmanager/manage/campaigns"
        self.open_url(url)

    def open_payment(self):
        url = "https://adsmanager.facebook.com/adsmanager/billing_hub/payment_settings"
        custom = simpledialog.askstring(
            "Payment URL",
            "Payment page URL din:\n(Cancel = generic page)",
            initialvalue="")
        if custom:
            url = custom.strip()
        self.open_url(url)

    def open_boost(self):
        url = "https://www.facebook.com/adsmanager/creation"
        custom = simpledialog.askstring(
            "Boost URL", "Boost page URL din:", initialvalue="")
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

    def edit(self):
        row = self.selected_row()
        if not row:
            return
        acc_id = row[0]
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT name, cookie, note FROM accounts WHERE id=?",
                  (acc_id,))
        name, cookie, note = c.fetchone()
        conn.close()
        win = tk.Toplevel(self.root)
        win.title(f"Edit #{acc_id}")
        win.geometry("800x400")
        tk.Label(win, text="Name:").pack(anchor="w", padx=10)
        ne = tk.Entry(win, width=80)
        ne.insert(0, name)
        ne.pack(padx=10)
        tk.Label(win, text="Note:").pack(anchor="w", padx=10)
        noe = tk.Entry(win, width=80)
        noe.insert(0, note or "")
        noe.pack(padx=10)
        tk.Label(win, text="Cookie:").pack(anchor="w", padx=10)
        ce = tk.Text(win, height=10, width=100)
        ce.insert("1.0", cookie)
        ce.pack(padx=10)

        def save():
            update_account(acc_id, ne.get().strip(),
                           ce.get("1.0", "end").strip(),
                           noe.get().strip())
            win.destroy()
            self.refresh()
        tk.Button(win, text="Save", bg="#4CAF50", fg="white",
                  width=12, command=save).pack(pady=8)

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
                name = item.get("name", "").strip()
                cookie = item.get("cookie", "").strip()
                note = item.get("note", "")
                if name and cookie:
                    add_account(name, cookie, note)
                    n += 1
            messagebox.showinfo("Imported", f"{n} account imported")
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
