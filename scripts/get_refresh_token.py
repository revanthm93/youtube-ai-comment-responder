#!/usr/bin/env python3
"""Get YouTube OAuth refresh token."""

import os
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv(Path(__file__).parent.parent / ".env")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube",
]

def main():
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    if not client_id or "your_" in client_id:
        print("ERROR: Set YOUTUBE_CLIENT_ID in .env first")
        return

    if not client_secret or "your_" in client_secret:
        print("ERROR: Set YOUTUBE_CLIENT_SECRET in .env first")
        return

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/"]
        }
    }

    print("\nBrowser will open for authentication...")
    print("Select your Google account and grant permissions.\n")

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=8080)

    print("\n" + "="*50)
    print("SUCCESS! Add this to your .env file:")
    print("="*50)
    print(f"\nYOUTUBE_REFRESH_TOKEN={credentials.refresh_token}\n")

if __name__ == "__main__":
    main()