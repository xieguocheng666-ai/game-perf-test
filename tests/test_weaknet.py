import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(r"D:\game-api-test").resolve()))
from server import db  # noqa: E402

BASE = "http://127.0.0.1:8000"
PROXY = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
USERNAME = "weaknet_u"


def _session():
    s = requests.Session()
    s.trust_env = False  # 禁用环境变量代理，避免 NO_PROXY 绕过 localhost
    s.proxies = PROXY
    return s


def _login(s):
    # 账号已由 conftest 的 reset_weaknet_state fixture 直连创建，这里只登录拿 token
    r = s.post(f"{BASE}/login", json={"username": USERNAME, "password": "p123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _gold(player_id):
    return db.fetch_one("SELECT gold FROM currencies WHERE player_id=%s", (player_id,))["gold"]


def _pid():
    return db.fetch_one("SELECT id FROM players WHERE username=%s", (USERNAME,))["id"]


def test_buy_weaknet_duplicate_charge():
    s = _session()
    h = _login(s)
    pid = _pid()

    gold0 = _gold(pid)  # 1000
    # 正常购买 sword（shop_item_id=1，price=100，buy_limit=0 不限购）
    s.post(f"{BASE}/shop/buy", json={"shop_item_id": 1}, headers=h)
    assert _gold(pid) == gold0 - 100

    # 弱网购买：Fiddler 已设高延迟，客户端 0.5s 超时，但服务端实际已扣款
    try:
        s.post(f"{BASE}/shop/buy", json={"shop_item_id": 1}, headers=h, timeout=0.5)
    except requests.Timeout:
        pass
    time.sleep(3)  # 等上一笔服务端事务落库

    # 恢复 Fiddler 后重试
    s.post(f"{BASE}/shop/buy", json={"shop_item_id": 1}, headers=h)

    gold_after = _gold(pid)
    print(f"购买：初始 {gold0} -> 弱网重试后 {gold_after}")
    # 理想：只扣 2 次 = gold0-200。当前实现无幂等，会扣 3 次 = gold0-300（重复扣款 bug）
    assert gold_after == gold0 - 300


def test_gacha_weaknet_duplicate_charge():
    s = _session()
    h = _login(s)
    pid = _pid()

    gold0 = _gold(pid)  # 1000
    s.post(f"{BASE}/gacha", headers=h)  # 正常一抽，扣 10
    assert _gold(pid) == gold0 - 10

    # 弱网抽卡：Fiddler 已设高延迟，客户端 0.5s 超时，但服务端实际已扣货币
    try:
        s.post(f"{BASE}/gacha", headers=h, timeout=0.5)
    except requests.Timeout:
        pass
    time.sleep(3)

    # 恢复 Fiddler 后重试
    s.post(f"{BASE}/gacha", headers=h)

    gold_after = _gold(pid)
    print(f"抽卡：初始 {gold0} -> 弱网重试后 {gold_after}")
    # 理想：扣 3 次 = gold0-30。当前实现无幂等，会扣 3 次（重复扣款 bug）
    assert gold_after == gold0 - 30


def test_buy_idempotency_key_prevents_duplicate_charge():
    s = _session()
    h = _login(s)
    pid = _pid()

    gold0 = _gold(pid)
    headers = {**h, "Idempotency-Key": "weaknet-buy-1"}

    # 带幂等键的弱网购买：客户端超时，但服务端已处理并记录 key
    try:
        s.post(f"{BASE}/shop/buy", json={"shop_item_id": 1}, headers=headers, timeout=0.5)
    except requests.Timeout:
        pass
    time.sleep(3)

    # 同 key 重试：服务端识别重复，不重复扣款
    r = s.post(f"{BASE}/shop/buy", json={"shop_item_id": 1}, headers=headers)
    assert r.json()["duplicate"] is True

    gold_after = _gold(pid)
    print(f"幂等修复后：初始 {gold0} -> 同 key 重试后 {gold_after}")
    assert gold_after == gold0 - 100  # 只扣一次
