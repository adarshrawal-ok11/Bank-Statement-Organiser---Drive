from __future__ import annotations

import contextlib
import queue
import re
import threading
import tkinter as tk
import urllib.parse
import webbrowser
from pathlib import Path
from tkinter import END, Spinbox, StringVar, Text, Tk, messagebox
from tkinter import ttk
from typing import Callable

import Scipt


DEFAULT_OWNER_EMAIL = "adarshrawal@gmail.com"

# ── Design tokens ──────────────────────────────────────────────────────────────
_WIN_BG  = "#b8b2ab"   # window background — darker, cards float above this
_CARD    = "#f0ebe5"   # card / panel surface — light cream, pops above bg
_INPUT   = "#edddd4"   # input field — soft warm peach, matches the theme
_PEACH   = "#e8a898"   # primary accent
_BLUE    = "#8bb8d4"   # secondary accent
_ROSE    = "#d4a0b0"   # tertiary accent
_SAGE    = "#a8c4b0"   # sage green
_TEXT    = "#5c5248"   # warm dark text
_MUTED   = "#9a9090"   # muted label text
_DIVIDER = "#d8d0c8"   # thin divider lines
_TERM_BG = "#2a2420"   # warm dark terminal
_TERM_FG = "#f0ebe5"   # terminal text
_SIDEBAR = 310         # sidebar width


# ── Rounded button widget ──────────────────────────────────────────────────────
class RoundBtn(tk.Canvas):
    """Canvas-backed button with smooth rounded corners."""

    def __init__(
        self,
        parent,
        text: str,
        fill: str,
        fg: str,
        command,
        parent_bg: str = _CARD,
        font=("Segoe UI", 10, "bold"),
        height: int = 42,
        radius: int = 14,
        **kw,
    ) -> None:
        super().__init__(
            parent, height=height, bg=parent_bg,
            highlightthickness=0, cursor="hand2", bd=0, **kw,
        )
        self._fill     = fill
        self._fg       = fg
        self._text     = text
        self._cmd      = command
        self._font     = font
        self._r        = radius
        self._hovered  = False

        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>",  lambda e: self._cmd())
        self.bind("<Enter>",     lambda e: self._hover(True))
        self.bind("<Leave>",     lambda e: self._hover(False))
        self.after(15, self._draw)

    def _shade(self, color: str, factor: float) -> str:
        r = min(255, int(int(color[1:3], 16) * factor))
        g = min(255, int(int(color[3:5], 16) * factor))
        b = min(255, int(int(color[5:7], 16) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _rrect(self, x1: int, y1: int, x2: int, y2: int, r: int, color: str) -> None:
        pts = [
            x1 + r, y1,     x2 - r, y1,
            x2,     y1,     x2,     y1 + r,
            x2,     y2 - r, x2,     y2,
            x2 - r, y2,     x1 + r, y2,
            x1,     y2,     x1,     y2 - r,
            x1,     y1 + r, x1,     y1,
        ]
        self.create_polygon(pts, smooth=True, fill=color, outline="")

    def _draw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            self.after(15, self._draw)
            return
        color = self._shade(self._fill, 0.88) if self._hovered else self._fill
        self._rrect(2, 2, w - 2, h - 2, self._r, color)
        self.create_text(w // 2, h // 2, text=self._text, fill=self._fg, font=self._font)

    def _hover(self, state: bool) -> None:
        self._hovered = state
        self._draw()


# ── Queue writer ───────────────────────────────────────────────────────────────
class QueueWriter:
    def __init__(self, output_queue: queue.Queue[str]) -> None:
        self.output_queue = output_queue

    def write(self, text: str) -> None:
        if text:
            self.output_queue.put(text)

    def flush(self) -> None:
        pass


# ── Main GUI ───────────────────────────────────────────────────────────────────
class BankStatementGui:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Bank Statement Organizer")
        self.root.geometry("1080x720")
        self.root.minsize(920, 620)

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self.owner_email = StringVar(value=DEFAULT_OWNER_EMAIL)
        self.request_email = StringVar()
        self.days = StringVar(value="30")
        self.status = StringVar(value="Ready")
        self.scan_account = StringVar(value="Scan account: not signed in yet")
        self.summary = StringVar(value="Uploaded: 0 | Downloaded: 0 | Found emails: 0")
        self.final_result = StringVar(value="Final result will appear here after a scan.")

        self.build_ui()
        self.root.after(100, self.drain_log_queue)

    # ── UI helpers ──────────────────────────────────────────────────────────────

    def _dot(self, parent: tk.Frame, color: str, size: int = 12) -> None:
        c = tk.Canvas(parent, bg=_CARD, width=size, height=size, highlightthickness=0)
        c.pack(side=tk.LEFT, padx=(0, 8))
        c.create_oval(1, 1, size - 1, size - 1, fill=color, outline="")

    def _section(self, parent: tk.Frame, label: str, dot: str) -> None:
        row = tk.Frame(parent, bg=_CARD)
        row.pack(anchor="w", pady=(0, 12))
        self._dot(row, dot)
        tk.Label(row, text=label, font=("Segoe UI", 12, "bold"), fg=_TEXT, bg=_CARD).pack(side=tk.LEFT)

    def _lbl(self, parent: tk.Frame, text: str) -> None:
        tk.Label(parent, text=text, font=("Segoe UI", 7, "bold"), fg=_MUTED, bg=_CARD).pack(anchor="w")

    def _entry(self, parent: tk.Frame, var: StringVar) -> None:
        tk.Entry(
            parent, textvariable=var,
            relief="flat", bd=0,
            bg=_INPUT, fg=_TEXT, insertbackground=_TEXT,
            font=("Segoe UI", 10),
            highlightbackground=_DIVIDER, highlightthickness=1,
        ).pack(fill=tk.X, ipady=9, pady=(4, 14))

    def _divider(self, parent: tk.Frame) -> None:
        tk.Frame(parent, bg=_DIVIDER, height=1).pack(fill=tk.X, pady=(0, 18))

    # ── build_ui ────────────────────────────────────────────────────────────────

    def build_ui(self) -> None:
        self.root.configure(bg=_WIN_BG)

        style = ttk.Style()
        style.configure(".", background=_WIN_BG, font=("Segoe UI", 10))
        style.configure("Win.TFrame", background=_WIN_BG)
        style.configure(
            "TScrollbar",
            troughcolor=_CARD, background=_DIVIDER,
            borderwidth=0, arrowsize=0, relief="flat",
        )
        style.map("TScrollbar", background=[("active", _MUTED), ("!active", _DIVIDER)])

        # ── Header canvas — decorative pastel circles ────────────────────────────
        HDR_BG = "#e4dfd9"
        hdr = tk.Canvas(self.root, bg=HDR_BG, height=90, highlightthickness=0, bd=0)
        hdr.pack(fill=tk.X, side="top")

        def _draw_hdr(event=None):
            w = hdr.winfo_width() or 1080
            hdr.delete("all")
            hdr.create_rectangle(0, 0, w, 90, fill=HDR_BG, outline="")
            hdr.create_oval(w - 55,  -25, w + 15, 45,   fill=_PEACH, outline="")
            hdr.create_oval(w - 118,  18, w - 48, 88,   fill=_BLUE,  outline="")
            hdr.create_oval(w - 190,  -8, w - 130, 52,  fill=_ROSE,  outline="")
            hdr.create_oval(w - 158,  52, w - 138, 72,  fill=HDR_BG, outline="")
            hdr.create_oval(22, 28, 40, 46, fill=_PEACH, outline="")
            hdr.create_text(52, 34, text="Bank Statement Organizer",
                            font=("Segoe UI", 18, "bold"), fill=_TEXT, anchor="w")
            hdr.create_text(52, 58, text="Google Drive Sync",
                            font=("Segoe UI", 10), fill=_MUTED, anchor="w")

        hdr.bind("<Configure>", _draw_hdr)
        self.root.after(20, _draw_hdr)

        # ── Body ────────────────────────────────────────────────────────────────
        body = ttk.Frame(self.root, padding=(16, 14, 16, 14), style="Win.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=0, minsize=_SIDEBAR)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ── Sidebar card — floats above _WIN_BG ──────────────────────────────────
        sb = tk.Frame(body, bg=_CARD)
        sb.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        si = tk.Frame(sb, bg=_CARD, padx=18, pady=18)
        si.pack(fill=tk.BOTH, expand=True)

        self._section(si, "Access", _PEACH)
        self._lbl(si, "REQUEST RECIPIENT")
        self._entry(si, self.owner_email)
        self._lbl(si, "GMAIL TO SCAN")
        self._entry(si, self.request_email)

        RoundBtn(
            si, "✉  Request Test Access", _DIVIDER, _TEXT,
            self.request_test_access, parent_bg=_CARD,
            font=("Segoe UI", 9), height=36, radius=12,
        ).pack(fill=tk.X, pady=(0, 18))

        self._divider(si)
        self._section(si, "Scan Range", _BLUE)

        rng = tk.Frame(si, bg=_CARD)
        rng.pack(fill=tk.X, pady=(0, 16))
        Spinbox(
            rng, from_=1, to=365, textvariable=self.days, width=6,
            relief="flat", bd=0,
            bg=_INPUT, fg=_TEXT, font=("Segoe UI", 12, "bold"),
            highlightbackground=_DIVIDER, highlightthickness=1,
            buttonbackground=_INPUT,
        ).pack(side=tk.LEFT, ipady=8, ipadx=4)
        tk.Label(rng, text=" days", font=("Segoe UI", 10), fg=_MUTED, bg=_CARD).pack(side=tk.LEFT)

        RoundBtn(
            si, "▶   Run Scan", _PEACH, "#ffffff",
            self.run_scan, parent_bg=_CARD, height=46, radius=16,
        ).pack(fill=tk.X, pady=(0, 10))

        RoundBtn(
            si, "↻   Check Login", _SAGE, "#ffffff",
            self.check_login, parent_bg=_CARD, height=40, radius=14,
        ).pack(fill=tk.X)

        tk.Frame(si, bg=_DIVIDER, height=1).pack(fill=tk.X, pady=(18, 10))
        tk.Label(
            si, textvariable=self.scan_account,
            font=("Segoe UI", 8, "italic"), fg=_MUTED, bg=_CARD,
            wraplength=262, justify="left",
        ).pack(anchor="w")

        # ── Right panel ──────────────────────────────────────────────────────────
        rp = tk.Frame(body, bg=_WIN_BG)
        rp.grid(row=0, column=1, sticky="nsew")
        rp.rowconfigure(2, weight=1)
        rp.columnconfigure(0, weight=1)

        # Status bar
        sbar = tk.Frame(rp, bg=_WIN_BG)
        sbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        pill = tk.Frame(sbar, bg=_PEACH)
        pill.pack(side=tk.LEFT)
        tk.Label(
            pill, textvariable=self.status,
            font=("Segoe UI", 10, "bold"), fg="#ffffff", bg=_PEACH,
        ).pack(padx=18, ipady=5)

        tk.Label(
            sbar, textvariable=self.summary,
            font=("Segoe UI", 9), fg=_CARD, bg=_WIN_BG,
        ).pack(side=tk.RIGHT)

        # Result card — floats above darker background
        res = tk.Frame(rp, bg=_CARD)
        res.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        ri = tk.Frame(res, bg=_CARD, padx=16, pady=14)
        ri.pack(fill=tk.BOTH, expand=True)

        rh = tk.Frame(ri, bg=_CARD)
        rh.pack(anchor="w", pady=(0, 6))
        self._dot(rh, _ROSE)
        tk.Label(rh, text="Result", font=("Segoe UI", 10, "bold"), fg=_TEXT, bg=_CARD).pack(side=tk.LEFT)
        tk.Label(
            ri, textvariable=self.final_result,
            font=("Segoe UI", 10), fg=_TEXT, bg=_CARD,
            wraplength=580, justify="left",
        ).pack(anchor="w")

        # Log card — floats above darker background
        log = tk.Frame(rp, bg=_CARD)
        log.grid(row=2, column=0, sticky="nsew", pady=(0, 12))

        lo = tk.Frame(log, bg=_CARD)
        lo.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        lo.rowconfigure(2, weight=1)
        lo.columnconfigure(0, weight=1)

        lh = tk.Frame(lo, bg=_CARD, padx=14, pady=10)
        lh.grid(row=0, column=0, columnspan=2, sticky="ew")
        lhr = tk.Frame(lh, bg=_CARD)
        lhr.pack(anchor="w")
        self._dot(lhr, _BLUE)
        tk.Label(lhr, text="Activity Log", font=("Segoe UI", 11, "bold"), fg=_TEXT, bg=_CARD).pack(side=tk.LEFT)

        tk.Frame(lo, bg=_DIVIDER, height=1).grid(row=1, column=0, columnspan=2, sticky="ew")

        self.log_text = Text(
            lo,
            wrap="word",
            height=18,
            bg=_TERM_BG,
            fg=_TERM_FG,
            insertbackground=_TERM_FG,
            relief="flat",
            padx=16,
            pady=14,
            font=("Cascadia Mono", 10),
            selectbackground="#6a4f40",
            selectforeground=_TERM_FG,
        )
        self.log_text.grid(row=2, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(lo, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        # Footer buttons
        ftr = tk.Frame(rp, bg=_WIN_BG)
        ftr.grid(row=3, column=0, sticky="ew")

        RoundBtn(
            ftr, "✕  Clear Log", _DIVIDER, _TEXT,
            self.clear_log, parent_bg=_WIN_BG,
            font=("Segoe UI", 9), height=34, radius=10,
        ).pack(side=tk.LEFT, ipadx=6)

        RoundBtn(
            ftr, "Open Drive  →", _BLUE, "#ffffff",
            lambda: webbrowser.open("https://drive.google.com/drive/my-drive"),
            parent_bg=_WIN_BG,
            font=("Segoe UI", 9), height=34, radius=10,
        ).pack(side=tk.RIGHT, ipadx=6)

    def request_test_access(self) -> None:
        owner = self.owner_email.get().strip()
        user_email = self.selected_email()

        if not owner:
            messagebox.showerror("Missing owner email", "Enter the email address that should receive test access requests.")
            return

        if not user_email or "@" not in user_email:
            messagebox.showerror("Missing user Gmail", "Enter the Gmail address that needs OAuth test access.")
            return

        subject = "Request test access for Bank Statement Organizer"
        body = (
            "Please add this Gmail address as a test user in Google Cloud Console:\n\n"
            f"{user_email}\n\n"
            "Project path:\n"
            "Google Cloud Console > APIs & Services > OAuth consent screen > Test users\n"
        )
        compose_url = (
            "https://mail.google.com/mail/?view=cm&fs=1"
            f"&to={urllib.parse.quote(owner)}"
            f"&su={urllib.parse.quote(subject)}"
            f"&body={urllib.parse.quote(body)}"
        )
        webbrowser.open(compose_url)
        self.log(f"Opened Gmail compose requesting test access for {user_email}\n")

    def check_login(self) -> None:
        if self.is_busy():
            return
        if not self.selected_email():
            messagebox.showerror("Missing Gmail", "Enter the Gmail address you want to scan.")
            return
        self.start_worker("Checking Google login...", self._check_login_worker)

    def run_scan(self) -> None:
        if self.is_busy():
            return
        try:
            selected_days = int(self.days.get())
        except ValueError:
            messagebox.showerror("Invalid days", "Enter a number of days between 1 and 365.")
            return
        if selected_days < 1 or selected_days > 365:
            messagebox.showerror("Invalid days", "Enter a number of days between 1 and 365.")
            return
        if not self.selected_email():
            messagebox.showerror("Missing Gmail", "Enter the Gmail address you want to scan.")
            return
        self.start_worker(f"Running scan for last {selected_days} days...", lambda: self._run_scan_worker(selected_days))
        self.final_result.set("Scan running...")

    def start_worker(self, status: str, target: Callable[[], None]) -> None:
        self.status.set(status)
        self.worker_thread = threading.Thread(target=target, daemon=True)
        self.worker_thread.start()

    def is_busy(self) -> bool:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Busy", "A task is already running. Wait for it to finish first.")
            return True
        return False

    def _check_login_worker(self) -> None:
        with contextlib.redirect_stdout(QueueWriter(self.output_queue)):
            try:
                expected_email = self.selected_email()
                gmail_service, _ = Scipt.authenticate(token_path=self.token_path_for_email(expected_email))
                profile = gmail_service.users().getProfile(userId="me").execute()
                email = profile.get("emailAddress", "unknown").lower()
                if email != expected_email.lower():
                    print(f"Login mismatch. GUI email is {expected_email}, but Google authorized {email}.")
                    print("Use the correct Google account during sign-in, or remove that email's token from the tokens folder.")
                    self.output_queue.put(f"__ACCOUNT__Scan account mismatch: {email}")
                    self.output_queue.put("__STATUS__Login mismatch")
                    return
                self.output_queue.put(f"__ACCOUNT__Scan account: {email}")
                print("Login check passed. Google OAuth is ready.")
                self.output_queue.put("__STATUS__Ready")
            except Exception as error:
                print(f"Login check failed: {error}")
                self.output_queue.put("__STATUS__Login check failed")

    def _run_scan_worker(self, selected_days: int) -> None:
        found_count = downloaded_count = uploaded_count = 0
        with contextlib.redirect_stdout(QueueWriter(self.output_queue)):
            try:
                expected_email = self.selected_email()
                gmail_service, drive_service = Scipt.authenticate(token_path=self.token_path_for_email(expected_email))
                profile = gmail_service.users().getProfile(userId="me").execute()
                email = profile.get("emailAddress", "unknown").lower()
                if email != expected_email.lower():
                    print(f"Scan stopped. GUI email is {expected_email}, but Google authorized {email}.")
                    print("Sign in with the Gmail entered in the GUI before running the scan.")
                    self.output_queue.put(f"__ACCOUNT__Scan account mismatch: {email}")
                    self.output_queue.put("__STATUS__Login mismatch")
                    return
                self.output_queue.put(f"__ACCOUNT__Scan account: {email}")
                query = f"has:attachment newer_than:{selected_days}d"
                messages = Scipt.list_messages(gmail_service, query)
                found_count = len(messages)
                print(f"Found {found_count} emails")
                for message in messages:
                    attachments = Scipt.download_attachments(gmail_service, drive_service, message)
                    downloaded_count += len(attachments)
                    for attachment in attachments:
                        uploaded = Scipt.upload_to_drive(
                            drive_service, attachment.local_path,
                            attachment.drive_folder_id, attachment.drive_display_path,
                        )
                        if uploaded:
                            uploaded_count += 1
                    self.output_queue.put(
                        f"__SUMMARY__Uploaded: {uploaded_count} | "
                        f"Downloaded: {downloaded_count} | Found emails: {found_count}"
                    )
                print("Scan complete.")
                self.output_queue.put("__STATUS__Ready")
                self.output_queue.put(
                    f"__SUMMARY__Uploaded: {uploaded_count} | "
                    f"Downloaded: {downloaded_count} | Found emails: {found_count}"
                )
                self.output_queue.put(
                    f"__FINAL__Done. Found {found_count} emails, downloaded {downloaded_count} files, "
                    f"uploaded {uploaded_count} files. Check your Google Drive for the attachments folder."
                )
            except Exception as error:
                print(f"Scan failed: {error}")
                self.output_queue.put("__STATUS__Scan failed")
                self.output_queue.put("__FINAL__Scan failed. Check the results log for details.")

    def drain_log_queue(self) -> None:
        while True:
            try:
                message = self.output_queue.get_nowait()
            except queue.Empty:
                break
            if message.startswith("__STATUS__"):
                self.status.set(message.replace("__STATUS__", "", 1))
            elif message.startswith("__SUMMARY__"):
                self.summary.set(message.replace("__SUMMARY__", "", 1))
            elif message.startswith("__ACCOUNT__"):
                self.scan_account.set(message.replace("__ACCOUNT__", "", 1))
            elif message.startswith("__FINAL__"):
                self.final_result.set(message.replace("__FINAL__", "", 1))
            else:
                self.log(message)
        self.root.after(100, self.drain_log_queue)

    def log(self, message: str) -> None:
        self.log_text.insert(END, message)
        self.log_text.see(END)

    def clear_log(self) -> None:
        self.log_text.delete("1.0", END)

    def selected_email(self) -> str:
        return self.request_email.get().strip()

    def token_path_for_email(self, email: str) -> Path:
        safe_email = re.sub(r"[^A-Za-z0-9_.-]+", "_", email.lower()).strip("._-")
        return Path("tokens") / f"{safe_email}.json"


def main() -> None:
    root = Tk()
    ttk.Style().theme_use("clam")
    BankStatementGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
