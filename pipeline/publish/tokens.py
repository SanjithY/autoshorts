"""Encrypted token store so rotating refresh tokens (TikTok, Instagram) survive between scheduled runs.

The file state/tokens.enc is committed back to the repo by the workflow; it is encrypted with the
TOKEN_KEY secret, so it is safe even in a public repo. Initial values come from GitHub Secrets.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

PATH = Path(__file__).resolve().parents[2] / "state" / "tokens.enc"


def _f():
    key = os.environ.get("TOKEN_KEY")
    if key:
        return Fernet(key.encode())
    # no TOKEN_KEY secret: derive one from a secret that already exists (one less thing to set up)
    seed = os.environ.get("YT_CLIENT_SECRET") or os.environ.get("TIKTOK_CLIENT_SECRET")
    if not seed:
        return None
    import base64, hashlib
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("autoshorts:" + seed).encode()).digest()))


def load() -> dict:
    f = _f()
    if f and PATH.exists():
        try:
            return json.loads(f.decrypt(PATH.read_bytes()))
        except Exception as ex:
            print(f"[tokens] could not decrypt store ({ex}); falling back to secrets")
    return {}


def save(data: dict):
    f = _f()
    if not f:
        print("[tokens] TOKEN_KEY not set; rotated tokens will not persist")
        return
    PATH.parent.mkdir(exist_ok=True)
    PATH.write_bytes(f.encrypt(json.dumps(data).encode()))


def get(name: str):
    return load().get(name) or os.environ.get(name)


def put(name: str, value: str):
    d = load()
    d[name] = value
    save(d)
