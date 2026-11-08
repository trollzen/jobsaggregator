"""One-time Telegram login. Run on your computer:

    python scripts/tg_login.py

Asks for phone number and the code Telegram sends you (and 2FA password if set),
saves the session to tg.session (never commit it), then prints your channels with
their ids so you can copy them into config.yaml.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jobagg.config import load_env  # noqa: E402

load_env()
# Windows console defaults to cp1252 and can't print Cyrillic channel names
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    from telethon.sync import TelegramClient
except ImportError:
    sys.exit('Telethon is not installed: pip install -e ".[telegram]"')

api_id = os.environ.get("TG_API_ID") or input("TG_API_ID: ").strip()
api_hash = os.environ.get("TG_API_HASH") or input("TG_API_HASH: ").strip()

with TelegramClient("tg.session", int(api_id), api_hash) as client:
    me = client.get_me()
    print(f"\nLogged in as {me.first_name} (@{me.username}). Session saved to tg.session\n")
    print("Your channels and groups (copy the ones you need into config.yaml):\n")
    print("telethon:\n  channels:")
    for d in client.get_dialogs():
        if d.is_channel:
            name = (d.entity.username or d.name or str(d.id))[:40]
            print(f'    - {{name: "{name}", id: {d.id}}}')
