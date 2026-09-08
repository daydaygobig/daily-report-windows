"""向飞书群机器人发送一条测试卡片，验证推送链路（含 IP 白名单）是否畅通。"""

import base64
import json
import sqlite3
import sys
import urllib.error
import urllib.request

from cryptography.fernet import Fernet

ROOT = __file__.rsplit("\\tools", 1)[0] if "\\tools" in __file__ else "."

key = None
with open(f"{ROOT}/.env", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("TS_SECRETS_KEY="):
            key = line.strip().split("=", 1)[1]
if not key:
    sys.exit(".env 中未找到 TS_SECRETS_KEY")

fernet = Fernet(base64.urlsafe_b64encode(key.encode("utf-8").ljust(32, b"0")[:32]))
conn = sqlite3.connect(f"{ROOT}/data/app.db")
url_cipher = conn.execute("SELECT url_cipher FROM webhooks WHERE id=1").fetchone()[0]
url = fernet.decrypt(url_cipher.encode()).decode()

payload = {
    "msg_type": "interactive",
    "card": {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "推送链路测试"},
        },
        "body": {
            "direction": "vertical",
            "elements": [
                {
                    "tag": "markdown",
                    "content": "这是一条日报系统的推送链路测试消息，收到即代表飞书机器人 IP 白名单已生效，可忽略。",
                }
            ],
        },
    },
}

request = urllib.request.Request(
    url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(request, timeout=30) as resp:
        print("HTTP", resp.status, "BODY", resp.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    print("HTTP", exc.code, exc.read().decode("utf-8")[:300])
except Exception as exc:  # noqa: BLE001
    print("ERROR", type(exc).__name__, exc)
