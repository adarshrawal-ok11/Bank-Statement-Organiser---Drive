from __future__ import annotations

import base64
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive",
]

GMAIL_QUERY = "has:attachment newer_than:30d"
LOCAL_ROOT = Path("attachments")
DRIVE_ROOT_FOLDER = "attachments"

BANKS = {
    "HDFC": ["hdfcbank", "hdfc"],
    "ICICI": ["icicibank", "icici"],
    "SBI": ["onlinesbi", "sbi"],
    "AXIS": ["axisbank", "axis"],
    "KOTAK": ["kotak"],
    "YESBANK": ["yesbank"],
    "IDFC": ["idfcfirstbank", "idfc"],
}

STATEMENT_KEYWORDS = [
    "statement",
    "account statement",
    "e-statement",
    "transaction",
    "txn",
]


@dataclass(frozen=True)
class AttachmentToUpload:
    local_path: Path
    drive_folder_id: str
    drive_display_path: str


def authenticate(token_path: str | Path = "token.json") -> tuple[Any, Any]:
    """Authenticate with OAuth2 and return Gmail and Drive service clients."""
    credentials = None
    token_path = Path(token_path)

    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                raise FileNotFoundError(
                    "credentials.json was not found. Download OAuth client credentials "
                    "from Google Cloud Console and place the file beside this script."
                )

            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            print("Opening Google sign-in in your browser. Complete the login to continue...", flush=True)
            credentials = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(credentials.to_json())

    gmail_service = build("gmail", "v1", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)
    return gmail_service, drive_service


def detect_bank(sender: str) -> str | None:
    """Detect a supported bank from the sender email address only."""
    sender_email = parseaddr(sender)[1].lower()

    if not sender_email:
        return None

    for bank, sender_markers in BANKS.items():
        if any(marker in sender_email for marker in sender_markers):
            return bank

    return None


def is_statement_file(filename: str, subject: str) -> bool:
    """Return True when the filename or subject contains a statement keyword."""
    searchable_text = f"{filename} {subject}".lower()
    return any(keyword in searchable_text for keyword in STATEMENT_KEYWORDS)


def get_header(headers: Iterable[dict[str, str]], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def gmail_date_from_internal_date(internal_date: str) -> datetime:
    return datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)


def list_messages(gmail_service: Any, query: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    page_token = None

    while True:
        response = (
            gmail_service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token)
            .execute()
        )
        messages.extend(response.get("messages", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            return messages


def iter_attachment_parts(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield all MIME parts that look like real attachments."""
    stack = [payload]

    while stack:
        part = stack.pop()
        stack.extend(part.get("parts", []))

        filename = part.get("filename")
        body = part.get("body", {})

        if filename and (body.get("attachmentId") or body.get("data")):
            yield part


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename).strip()
    return cleaned or "attachment"


def unique_local_path(target_dir: Path, filename: str) -> Path:
    safe_filename = sanitize_filename(filename)
    candidate = target_dir / safe_filename

    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1

    while True:
        candidate = target_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def decode_attachment_data(gmail_service: Any, message_id: str, part: dict[str, Any]) -> bytes:
    body = part.get("body", {})

    if body.get("data"):
        encoded_data = body["data"]
    else:
        attachment_id = body["attachmentId"]
        attachment = (
            gmail_service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        encoded_data = attachment["data"]

    return base64.urlsafe_b64decode(encoded_data.encode("utf-8"))


def escape_drive_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def get_or_create_folder(
    drive_service: Any,
    folder_name: str,
    parent_id: str | None = None,
) -> str:
    """Return a Drive folder ID, creating the folder when it is missing."""
    escaped_name = escape_drive_query_value(folder_name)
    query_parts = [
        f"name = '{escaped_name}'",
        "mimeType = 'application/vnd.google-apps.folder'",
        "trashed = false",
    ]

    if parent_id:
        query_parts.append(f"'{parent_id}' in parents")
    else:
        query_parts.append("'root' in parents")

    response = (
        drive_service.files()
        .list(
            q=" and ".join(query_parts),
            spaces="drive",
            fields="files(id, name)",
            pageSize=1,
        )
        .execute()
    )

    folders = response.get("files", [])
    if folders:
        return folders[0]["id"]

    metadata: dict[str, Any] = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }

    if parent_id:
        metadata["parents"] = [parent_id]

    folder = (
        drive_service.files()
        .create(body=metadata, fields="id")
        .execute()
    )
    return folder["id"]


def drive_file_exists(drive_service: Any, filename: str, folder_id: str) -> bool:
    escaped_filename = escape_drive_query_value(filename)
    response = (
        drive_service.files()
        .list(
            q=(
                f"name = '{escaped_filename}' and "
                f"'{folder_id}' in parents and "
                "trashed = false"
            ),
            spaces="drive",
            fields="files(id, name)",
            pageSize=1,
        )
        .execute()
    )
    return bool(response.get("files", []))


def upload_to_drive(
    drive_service: Any,
    local_path: Path,
    folder_id: str,
    drive_display_path: str,
) -> bool:
    """Upload a local file to Drive. Returns False when a duplicate is skipped."""
    if drive_file_exists(drive_service, local_path.name, folder_id):
        print("Skipped: file already exists in Drive")
        return False

    mime_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
    metadata = {"name": local_path.name, "parents": [folder_id]}

    drive_service.files().create(
        body=metadata,
        media_body=media,
        fields="id",
    ).execute()

    print("Uploaded:")
    print(drive_display_path)
    return True


def ensure_drive_hierarchy(
    drive_service: Any,
    bank: str,
    month_folder: str,
    date_folder: str,
) -> tuple[str, str]:
    root_id = get_or_create_folder(drive_service, DRIVE_ROOT_FOLDER)
    bank_id = get_or_create_folder(drive_service, bank, root_id)
    month_id = get_or_create_folder(drive_service, month_folder, bank_id)
    date_id = get_or_create_folder(drive_service, date_folder, month_id)
    display_path = f"{DRIVE_ROOT_FOLDER}/{bank}/{month_folder}/{date_folder}"
    return date_id, display_path


def download_attachments(
    gmail_service: Any,
    drive_service: Any,
    message: dict[str, str],
) -> list[AttachmentToUpload]:
    """Process one Gmail message, download valid bank statements, and prepare uploads."""
    message_id = message["id"]
    full_message = (
        gmail_service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    payload = full_message.get("payload", {})
    headers = payload.get("headers", [])
    sender = get_header(headers, "From")
    subject = get_header(headers, "Subject")
    received_at = gmail_date_from_internal_date(full_message["internalDate"])
    date_folder = received_at.strftime("%Y-%m-%d")
    month_folder = received_at.strftime("%Y-%m")

    print()
    print(f"From: {parseaddr(sender)[1] or sender}")
    print(f"Subject: {subject}")

    bank = detect_bank(sender)
    if not bank:
        print("Skipped: sender not recognized bank")
        return []

    print(f"Detected Bank: {bank}")

    downloaded: list[AttachmentToUpload] = []
    local_dir = LOCAL_ROOT / bank / month_folder / date_folder
    drive_folder_id: str | None = None
    drive_folder_path: str | None = None

    for part in iter_attachment_parts(payload):
        original_filename = part.get("filename", "")

        if not is_statement_file(original_filename, subject):
            print("Skipped: non-statement attachment")
            continue

        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = unique_local_path(local_dir, original_filename)
        local_path.write_bytes(decode_attachment_data(gmail_service, message_id, part))

        local_display_path = local_path.as_posix()
        print("Downloaded:")
        print(local_display_path)

        if drive_folder_id is None or drive_folder_path is None:
            drive_folder_id, drive_folder_path = ensure_drive_hierarchy(
                drive_service,
                bank,
                month_folder,
                date_folder,
            )

        downloaded.append(
            AttachmentToUpload(
                local_path=local_path,
                drive_folder_id=drive_folder_id,
                drive_display_path=f"{drive_folder_path}/{local_path.name}",
            )
        )

    return downloaded


def main() -> None:
    try:
        gmail_service, drive_service = authenticate()
        messages = list_messages(gmail_service, GMAIL_QUERY)

        print(f"Found {len(messages)} emails")

        for message in messages:
            attachments = download_attachments(gmail_service, drive_service, message)

            for attachment in attachments:
                upload_to_drive(
                    drive_service,
                    attachment.local_path,
                    attachment.drive_folder_id,
                    attachment.drive_display_path,
                )

    except HttpError as error:
        print(f"Google API error: {error}")
    except FileNotFoundError as error:
        print(error)


if __name__ == "__main__":
    main()
