import logging
import os.path
import pickle

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from .utils import get_temp_path

logger = logging.getLogger(__name__)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.readonly",
]


GOOGLE_CLIENT_SECRET_FILE = get_temp_path("google-credentials.json")
GOOGLE_TOKEN_FILE = get_temp_path("google-token.pickle")


def get_account_credentials(email: str) -> Credentials:
    creds = None
    _token_file = get_temp_path(f"{email}-google-token.pickle")

    # Check if token.pickle exists
    if os.path.exists(_token_file):
        with open(_token_file, "rb") as token:
            creds = pickle.load(token)

    # If no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow

            creds = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_CLIENT_SECRET_FILE, SCOPES
            ).run_local_server(port=0, timeout_seconds=30, open_browser=True)
            # Verify creds match the account
            user_info = get_user_info(creds)
            if user_info["email"] != email:
                raise ValueError(
                    f"Credential email {user_info['email']} does not match provided"
                    " email {email}"
                )

        # Save credentials
        logger.info("Saving credentials to %s", _token_file)
        with open(_token_file, "wb") as token:
            pickle.dump(creds, token)

    return creds


def get_user_info(creds: Credentials):
    service = build("oauth2", "v2", credentials=creds)
    userinfo = service.userinfo().get().execute()

    return userinfo


def verify_credentials(email: str):
    creds = get_account_credentials(email)
    if not creds:
        raise ValueError(f"No credentials found for {email}")

    logger.info(f"✅ Credentials found for {email}")
