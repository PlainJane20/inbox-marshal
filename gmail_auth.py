"""
Google OAuth for Gmail — standard installed-app flow. Runs a local
throwaway web server for the browser redirect, same pattern every
Google API quickstart uses. token.json (the refresh token) is written
locally and gitignored — never touches the repo, never touches this chat.
"""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# gmail.modify covers read + label changes + archive (removing INBOX label).
# gmail.send is required only for the mailto-based unsubscribe path — HTTP
# one-click unsubscribe needs no Gmail scope at all, it's a plain request to
# an external URL. Both are requested up front so a re-auth isn't needed
# later just because a sender happens to use the mailto mechanism.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def get_gmail_service(credentials_path: str, token_path: str):
    creds = None
    token_file = Path(token_path)

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(credentials_path).exists():
                raise FileNotFoundError(
                    f"{credentials_path} not found — download your OAuth client "
                    f"JSON from Google Cloud Console and place it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)
