# Bank Statement Organizer

A Python desktop GUI that scans a Gmail inbox for recent bank statement attachments, stores matching files locally, and syncs them into Google Drive under an `attachments` folder.

## Features

- Gmail OAuth login
- Google Drive sync
- Bank detection from sender email
- Statement attachment filtering
- Date-based folder structure
- Duplicate-safe local downloads
- Duplicate-safe Drive uploads
- GUI for test access request, login check, scan range, and results

## Supported Banks

- HDFC
- ICICI
- SBI
- AXIS
- KOTAK
- YESBANK
- IDFC

## Project Files

```text
.
|-- gui_app.py
|-- Scipt.py
|-- requirements.txt
|-- README.md
`-- .gitignore
```

## Important: Credentials

This project needs a Google OAuth file named:

```text
credentials.json
```

For security, `credentials.json` is not committed to GitHub.

If you are testing this as an assignment reviewer, there are two options:

1. The developer shares `credentials.json` with you privately.
2. You create your own Google Cloud OAuth credentials.

Most reviewers do not need to do the Google Cloud setup if the developer has privately shared a valid `credentials.json` and added the reviewer's Gmail as a test user.

## Quick Start For Testers

Use this path if `credentials.json` was shared with you privately.

1. Place `credentials.json` in the project root, beside `gui_app.py`.

2. Install Python dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Run the GUI:

   ```powershell
   .\.venv\Scripts\python.exe gui_app.py
   ```

4. Enter the Gmail account to scan.

5. Click `Check Login`.

6. Complete Google sign-in in the browser.

7. Select the number of days to scan.

8. Click `Run Scan`.

9. After completion, check Google Drive for:

   ```text
   attachments/
   ```

## OAuth Test User Note

If the app is still in Google OAuth Testing mode, the Gmail account being scanned must be added as a test user by the developer.

If Google shows:

```text
Error 403: access_denied
```

ask the developer to add your Gmail address in:

```text
Google Cloud Console > APIs & Services > OAuth consent screen > Test users
```

The GUI has a `Request Test Access` button that opens a pre-filled Gmail draft for this.

## Full Google Cloud Setup For Developers

Use this only if you need to create your own `credentials.json`.

1. Open Google Cloud Console:

   https://console.cloud.google.com/

2. Create or select a project.

3. Enable APIs:

   ```text
   APIs & Services > Library > Gmail API > Enable
   APIs & Services > Library > Google Drive API > Enable
   ```

4. Configure OAuth consent:

   ```text
   APIs & Services > OAuth consent screen
   ```

   For assignment/testing use, keep the app in Testing mode and add test users.

5. Create OAuth credentials:

   ```text
   APIs & Services > Credentials > Create Credentials > OAuth client ID
   ```

6. Choose:

   ```text
   Application type: Desktop app
   ```

7. Download the JSON file.

8. Rename it to:

   ```text
   credentials.json
   ```

9. Place it in the project root, beside `gui_app.py`.

## How The GUI Uses Email

The GUI scans the Gmail account entered in:

```text
Gmail to scan
```

For each Gmail account, the app creates a separate token file:

```text
tokens/<gmail-address>.json
```

If the typed Gmail does not match the Google account used during sign-in, the app stops and shows a login mismatch.

## Output Structure

Local files are saved as:

```text
attachments/
`-- BANK/
    `-- YYYY-MM/
        `-- YYYY-MM-DD/
            `-- statement.pdf
```

Google Drive uses the same structure:

```text
attachments/
`-- ICICI/
    `-- 2026-05/
        `-- 2026-05-02/
            `-- Statement_2026MTH04_197561342.pdf
```

## CLI Option

The core automation can also be run directly:

```powershell
.\.venv\Scripts\python.exe Scipt.py
```

The GUI is recommended because it supports email-specific tokens and shows results more clearly.

## Do Not Upload These Files

These files are private or generated locally and should not be committed to GitHub:

```text
credentials.json
credentials.json.json
token.json
tokens/
attachments/
.venv/
__pycache__/
```

Only upload:

```text
gui_app.py
Scipt.py
requirements.txt
README.md
.gitignore
```
