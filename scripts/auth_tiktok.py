"""Run ONCE to get a TikTok refresh token for your account.

Needs: a TikTok developer app with Login Kit + Content Posting API (Direct Post enabled),
scopes user.info.basic, video.publish, and a Redirect URI you registered (any https page you
control works, e.g. https://YOURNAME.github.io/ ).

    python scripts/auth_tiktok.py CLIENT_KEY CLIENT_SECRET https://YOURNAME.github.io/
Open the printed link, approve, then paste the full URL you land on.
"""
import sys
import secrets
from urllib.parse import urlencode, urlparse, parse_qs
import requests

key, secret, redirect = sys.argv[1:4]
state = secrets.token_urlsafe(8)
print("Open this link and approve:\n")
print("https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
    "client_key": key, "scope": "user.info.basic,video.publish", "response_type": "code",
    "redirect_uri": redirect, "state": state}))
landed = input("\nPaste the full URL you were redirected to: ").strip()
code = parse_qs(urlparse(landed).query)["code"][0]
r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
    "client_key": key, "client_secret": secret, "code": code, "grant_type": "authorization_code",
    "redirect_uri": redirect}, headers={"Content-Type": "application/x-www-form-urlencoded"}).json()
print("\nAdd these as GitHub Secrets:\n")
print("TIKTOK_CLIENT_KEY     =", key)
print("TIKTOK_CLIENT_SECRET  =", secret)
print("TIKTOK_REFRESH_TOKEN  =", r.get("refresh_token", r))
