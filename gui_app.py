from __future__ import annotations

import contextlib
import queue
import re
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Spinbox, StringVar, Text, Tk, messagebox
from tkinter import ttk
from typing import Callable

import Scipt


DEFAULT_OWNER_EMAIL = "adarshrawal@gmail.com"


class QueueWriter:
    def __init__(self, output_queue: queue.Queue[str]) -> None:
        self.output_queue = output_queue

    def write(self, text: str) -> None:
        if text:
            self.output_queue.put(text)

    def flush(self) -> None:
        pass


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

    def build_ui(self) -> None:
        self.root.configure(bg="#f5f5f7")
        style = ttk.Style()
        style.configure(".", font=("Segoe UI", 10))
        style.configure("App.TFrame", background="#f5f5f7")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Header.TFrame", background="#f5f5f7")
        style.configure("Title.TLabel", background="#f5f5f7", foreground="#1d1d1f", font=("Segoe UI", 24, "bold"))
        style.configure("Eyebrow.TLabel", background="#f5f5f7", foreground="#6e6e73", font=("Segoe UI", 10, "bold"))
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#1d1d1f", font=("Segoe UI", 13, "bold"))
        style.configure("CardLabel.TLabel", background="#ffffff", foreground="#424245", font=("Segoe UI", 9, "bold"))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#6e6e73", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#f5f5f7", foreground="#0071e3", font=("Segoe UI", 10, "bold"))
        style.configure("Summary.TLabel", background="#f5f5f7", foreground="#424245", font=("Segoe UI", 10))
        style.configure("Final.TLabel", background="#ffffff", foreground="#1d1d1f", font=("Segoe UI", 11, "bold"))
        style.configure("TEntry", padding=(8, 7))
        style.configure("TButton", padding=(14, 8), borderwidth=0)
        style.configure("Accent.TButton", padding=(16, 9), foreground="#ffffff", background="#0071e3")
        style.map(
            "Accent.TButton",
            background=[("active", "#147ce5"), ("pressed", "#0068d1"), ("disabled", "#b8c7d9")],
            foreground=[("disabled", "#ffffff")],
        )
        style.configure("Secondary.TButton", padding=(14, 8), foreground="#0071e3", background="#ffffff")

        outer = ttk.Frame(self.root, padding=24, style="App.TFrame")
        outer.pack(fill=BOTH, expand=True)

        header = ttk.Frame(outer, style="Header.TFrame")
        header.pack(fill=X, pady=(0, 18))
        ttk.Label(header, text="DRIVE SYNC", style="Eyebrow.TLabel").pack(anchor="w")

        title = ttk.Label(
            header,
            text="Bank Statement Organizer",
            style="Title.TLabel",
        )
        title.pack(anchor="w", pady=(2, 0))

        content = ttk.Frame(outer, style="App.TFrame")
        content.pack(fill=BOTH, expand=True)
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        left = ttk.Frame(content, padding=18, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.configure(width=330)
        left.grid_propagate(False)

        right = ttk.Frame(content, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(left, text="Access", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 16))

        ttk.Label(left, text="REQUEST RECIPIENT", style="CardLabel.TLabel").pack(anchor="w")
        ttk.Entry(left, textvariable=self.owner_email).pack(fill=X, pady=(6, 14))

        ttk.Label(left, text="GMAIL TO SCAN", style="CardLabel.TLabel").pack(anchor="w")
        ttk.Entry(left, textvariable=self.request_email).pack(fill=X, pady=(6, 12))
        ttk.Button(
            left,
            text="Request Test Access",
            command=self.request_test_access,
            style="Secondary.TButton",
        ).pack(fill=X, pady=(0, 24))

        ttk.Label(left, text="Scan Range", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
        range_row = ttk.Frame(left, style="Card.TFrame")
        range_row.pack(fill=X, pady=(0, 18))
        Spinbox(
            range_row,
            from_=1,
            to=365,
            textvariable=self.days,
            width=8,
            relief="flat",
            bg="#f5f5f7",
            font=("Segoe UI", 11),
        ).pack(side=LEFT)
        ttk.Label(range_row, text="days", style="Muted.TLabel").pack(side=LEFT, padx=(8, 0))

        ttk.Button(left, text="Run Scan", command=self.run_scan, style="Accent.TButton").pack(fill=X, pady=(0, 10))
        ttk.Button(left, text="Check Login", command=self.check_login, style="Secondary.TButton").pack(fill=X)

        ttk.Label(left, textvariable=self.scan_account, style="Muted.TLabel", wraplength=285).pack(anchor="w", pady=(22, 0))

        top_bar = ttk.Frame(right, style="App.TFrame")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(top_bar, textvariable=self.status, style="Status.TLabel").pack(side=LEFT)
        ttk.Label(top_bar, textvariable=self.summary, style="Summary.TLabel").pack(side=RIGHT)

        result_bar = ttk.Frame(right, padding=16, style="Card.TFrame")
        result_bar.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(result_bar, text="Final Result", style="CardLabel.TLabel").pack(anchor="w")
        ttk.Label(result_bar, textvariable=self.final_result, style="Final.TLabel", wraplength=620).pack(anchor="w", pady=(5, 0))

        log_frame = ttk.Frame(right, padding=12, style="Card.TFrame")
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)
        ttk.Label(log_frame, text="Activity", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.log_text = Text(
            log_frame,
            wrap="word",
            height=22,
            bg="#111111",
            fg="#f5f5f7",
            insertbackground="#f5f5f7",
            relief="flat",
            padx=14,
            pady=12,
            font=("Cascadia Mono", 10),
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")

        footer = ttk.Frame(right, style="App.TFrame")
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(footer, text="Clear Log", command=self.clear_log, style="Secondary.TButton").pack(side=LEFT)
        ttk.Button(
            footer,
            text="Open Drive",
            command=lambda: webbrowser.open("https://drive.google.com/drive/my-drive"),
            style="Secondary.TButton",
        ).pack(side=RIGHT)

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
                    print(
                        f"Login mismatch. GUI email is {expected_email}, "
                        f"but Google authorized {email}."
                    )
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
        found_count = 0
        downloaded_count = 0
        uploaded_count = 0

        with contextlib.redirect_stdout(QueueWriter(self.output_queue)):
            try:
                expected_email = self.selected_email()
                gmail_service, drive_service = Scipt.authenticate(token_path=self.token_path_for_email(expected_email))
                profile = gmail_service.users().getProfile(userId="me").execute()
                email = profile.get("emailAddress", "unknown").lower()

                if email != expected_email.lower():
                    print(
                        f"Scan stopped. GUI email is {expected_email}, "
                        f"but Google authorized {email}."
                    )
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
                            drive_service,
                            attachment.local_path,
                            attachment.drive_folder_id,
                            attachment.drive_display_path,
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
