"""Run ONCE on your own computer to get a YouTube refresh token.

1. In Google Cloud Console: create a project, enable "YouTube Data API v3", create an OAuth client
   of type "Desktop app", download its JSON as client_secret.json next to this script.
2. pip install google-auth-oauthlib
3. python scripts/auth_youtube.py   -> browser opens, pick your channel's Google account.
Copy the three printed values into GitHub Secrets.
"""
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

secret = Path(__file__).with_name("client_secret.json")
flow = InstalledAppFlow.from_client_secrets_file(str(secret), ["https://www.googleapis.com/auth/youtube.upload"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
c = json.loads(secret.read_text())
c = c.get("installed") or c.get("web")
print("\nAdd these as GitHub Secrets:\n")
print("YT_CLIENT_ID     =", c["client_id"])
print("YT_CLIENT_SECRET =", c["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
