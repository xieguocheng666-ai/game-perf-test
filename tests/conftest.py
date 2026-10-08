import sys
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# 先加载 B 项目的 .env：server/config.py 里的 load_dotenv() 默认读「当前工作目录」的 .env，
# C 项目从 D:\game-perf-test 跑时 cwd 里没有 .env，DB_PASSWORD 会是空导致连不上 MySQL。
load_dotenv(Path(r"D:\game-api-test\.env"))

sys.path.insert(0, str(Path(r"D:\game-api-test").resolve()))
from server import db  # noqa: E402

BASE = "http://127.0.0.1:8000"
USERNAME = "weaknet_u"
START_GOLD = 1000


@pytest.fixture(autouse=True)
def reset_weaknet_state():
    """每个弱网用例跑前，把 weaknet_u 的货币/背包/保底/幂等键重置到初始态。

    为什么必须清（否则反复跑 suite 会挂）：
    - idempotency_keys：幂等用例用固定 key，第二次跑撞 key，服务端直接返回
      duplicate、不扣款，断言 == gold0-100 必失败。
    - currencies.gold：每次跑都消耗，反复跑耗尽到 insufficient gold，正常购买断言失败。
    - gacha_pity：累积到 90 触发硬保底 SSR，破坏「纯概率」观察。
    - inventory / purchase_records：避免道具与购买记录污染后续断言。
    """
    s = requests.Session()
    s.trust_env = False
    try:
        s.post(f"{BASE}/register", json={"username": USERNAME, "password": "p123"}, timeout=5)
    except requests.Timeout:
        pass
    pid = db.fetch_one("SELECT id FROM players WHERE username=%s", (USERNAME,))["id"]
    for table in ("idempotency_keys", "purchase_records", "gacha_pity", "inventory"):
        db.execute(f"DELETE FROM {table} WHERE player_id=%s", (pid,))
    db.execute("UPDATE currencies SET gold=%s WHERE player_id=%s", (START_GOLD, pid))
    yield
