# 游戏性能 / 弱网专项 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 CapFrameX 测 Spaceship 三档画质性能，用 Fiddler 模拟弱网测 B 项目游戏接口的数据一致性，产出可溯源的专项报告。

**Architecture:** 两个独立专项。性能 = 黑盒采样现成 demo 的帧率/帧时间/Jank/内存；弱网 = 真实 HTTP 服务 + Fiddler 代理 + requests 脚本，验证弱网重试下的数据一致性（重点：购买是否重复扣款）。

**Tech Stack:** CapFrameX / Fiddler / Python + pytest + requests / uvicorn / MySQL

---

## Task 1: 准备工具与环境

**Files:** 无（纯环境准备）

- [ ] **Step 1: 下载 Unity Spaceship demo**

Steam 商店搜 `Spaceship – Visual Effect Graph Demo`，免费加入库并安装（约 1-2 GB）。装完启动确认能进入 benchmark 模式。

- [ ] **Step 2: 安装 CapFrameX**

已下载便携版（v1.9.1，GitHub 官方 release）并解压到 `D:\CapFrameX\`。双击 `CapFrameX.exe` 启动，确认能看到主界面、能识别本机进程（绿色解压即用，无需安装、无需注册）。

- [ ] **Step 3: 安装 Fiddler**

官网下载 Fiddler Classic（免费版），安装。启动后确认状态栏显示 `Capturing`，默认代理端口 `127.0.0.1:8888`（`Tools → Options → Connections` 查看）。

- [ ] **Step 4: 确认 B 项目后端可跑**

```bash
cd /d/game-api-test && python -c "from server import db; db.init_db(); print('db ok')"
```

Expected: 打印 `db ok`，无报错（MySQL 和 Redis 已在跑，`shop_items` 已 seed 三条商品：id=1 sword price=100、id=2 gems price=999999、id=3 ticket price=10）。

- [ ] **Step 5: 确认能起真实服务**

```bash
cd /d/game-api-test && python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

另开终端 `curl http://127.0.0.1:8000/health`，Expected: `{"status":"ok"}`。测完 Ctrl+C 停掉。

---

## Task 2: 性能测试（Spaceship 三档画质 + CapFrameX）

**Files:** 无（手动操作 + CapFrameX 导出数据）

- [ ] **Step 1: 启动 Spaceship 并进入 benchmark 模式**

打开 Spaceship demo，找到内置 benchmark 模式入口，确认能跑一段固定场景流程（可复现）。

- [ ] **Step 2: 画质设「低」，CapFrameX 选进程并开始采集**

CapFrameX 里选中 Spaceship 进程，开始记录。跑完一轮 benchmark，停止记录。记录指标：平均 FPS、帧时间 P50/P99、1% Low FPS、Jank、内存、CPU/GPU。

- [ ] **Step 3: 画质设「中」，重复一轮**

- [ ] **Step 4: 画质设「高」，重复一轮**

- [ ] **Step 5: 导出 CapFrameX 数据**

CapFrameX 里导出三档画质的数据（CSV 或截图），存到 `D:\game-perf-test\data\` 目录，命名 `spaceship_low.csv` / `spaceship_mid.csv` / `spaceship_high.csv`。

**验收：** 三档画质都有数据，指标含帧时间 P50/P99 和 Jank（不是只报平均 FPS）。

---

## Task 3: 弱网测试脚本（requests + Fiddler 代理）

**Files:**
- Create: `D:\game-perf-test\tests\test_weaknet.py`
- Create: `D:\game-perf-test\tests\conftest.py`

**背景（关键）：** B 项目购买接口 `POST /shop/buy` 有 DB 事务（扣货币 + 加背包 + 记购买），但**没有幂等设计**。弱网下客户端超时重试，服务端会重复执行扣款。本任务写脚本把这个缺陷测出来。

- [ ] **Step 1: 写 conftest.py**

```python
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(r"D:\game-api-test").resolve()))
from server import db  # noqa: E402

BASE = "http://127.0.0.1:8000"
USERNAME = "weaknet_u"
START_GOLD = 1000


@pytest.fixture(autouse=True)
def reset_weaknet_state():
    """每个弱网用例跑前，把 weaknet_u 的货币/背包/保底/幂等键重置到初始态。

    为什么必须清（否则反复跑 suite 会挂）：
    - idempotency_keys：幂等用例用固定 key，不清的话第二次跑撞 key，服务端直接返回
      duplicate、不扣款，断言 == gold0-100 必失败。
    - currencies.gold：每次跑都消耗，反复跑会耗尽到 insufficient gold，正常购买断言失败。
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
```

作用：让测试脚本能 `from server import db` 复用 B 项目的 DB 查询（验证扣款用）；`reset_weaknet_state` 是 `autouse=True` 的隔离 fixture，每个用例跑前自动重置账号数据，保证用例可反复跑、互不污染。

- [ ] **Step 2: 写 test_weaknet.py 框架**

```python
import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(r"D:\game-api-test").resolve()))
from server import db  # noqa: E402

BASE = "http://127.0.0.1:8000"
PROXY = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}


def _session():
    s = requests.Session()
    s.trust_env = False  # 禁用环境变量代理，避免 NO_PROXY 绕过 localhost
    s.proxies = PROXY
    return s


def _login(s):
    # 账号已由 conftest 的 reset_weaknet_state fixture 直连创建，这里只登录拿 token
    r = s.post(f"{BASE}/login", json={"username": "weaknet_u", "password": "p123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _gold(player_id):
    return db.fetch_one("SELECT gold FROM currencies WHERE player_id=%s", (player_id,))["gold"]
```

- [ ] **Step 3: 写「购买弱网重复扣款」用例**

```python
def test_buy_weaknet_duplicate_charge():
    s = _session()
    h = _login(s)
    pid = db.fetch_one("SELECT id FROM players WHERE username='weaknet_u'", ())["id"]

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
    print(f"初始 {gold0} -> 弱网重试后 {gold_after}")
    # 理想：只扣 2 次 = gold0-200。当前实现无幂等，会扣 3 次 = gold0-300（重复扣款 bug）
    assert gold_after == gold0 - 300
```

- [ ] **Step 4: 写「抽卡弱网重复扣款」用例**

```python
def test_gacha_weaknet_duplicate_charge():
    s = _session()
    h = _login(s)
    pid = db.fetch_one("SELECT id FROM players WHERE username='weaknet_u'", ())["id"]

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
```

> 说明：抽卡接口已补全「扣货币」（每抽 10 金币，见 B 项目 Plan 3 加固），所以抽卡弱网的观察点和购买一致——「弱网重试是否重复扣货币」，是第二个重复扣款硬核用例（不再是只测保底推进的补充用例）。

- [ ] **Step 5: 跑一遍确认脚本能连上服务（Fiddler 正常、未模拟弱网时）**

```bash
cd /d/game-api-test && python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 &
cd /d/game-perf-test && python -m pytest tests/test_weaknet.py -v
```

Expected: 此时 Fiddler 未设弱网，`test_buy_weaknet_duplicate_charge` 里第二次购买不会超时，断言可能失败（因为没制造超时）。这一步只确认「脚本能跑、能连 DB、代理生效」，具体断言在 Task 4 配好弱网后再看。

- [ ] **Step 6: 写「幂等修复后复验」用例（前置：B 项目 `/shop/buy` 已加 Idempotency-Key）**

```python
def test_buy_idempotency_key_prevents_duplicate_charge():
    s = _session()
    h = _login(s)
    pid = db.fetch_one("SELECT id FROM players WHERE username='weaknet_u'", ())["id"]

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
```

> 前置：B 项目 `/shop/buy` 已加 Idempotency-Key（见 `D:\game-api-test\docs\superpowers\plans\2026-10-08-game-api-hardening.md`）。此用例证明修复后弱网重试不重复扣款，与 Step 3 的「bug 复现」形成「发现 → 根因 → 修复 → 复验」闭环。

---

## Task 4: 弱网测试执行（五档弱网 + 数据一致性）

**Files:** 无（手动配 Fiddler + 跑 Task 3 脚本）

前置：B 项目服务已起（`uvicorn server.main:app --port 8000`），Fiddler 已开。

> 隔离已处理：conftest 的 `reset_weaknet_state` fixture 会在每个用例跑前重置 `weaknet_u` 的 gold（→1000）并清空四张业务表，所以用例可单独跑、可反复跑、顺序无关，不需要手动清库。

- [ ] **Step 1: 配 Fiddler 弱网参数（延迟档）**

`Rules → Customize Rules`（Ctrl+R），在 `OnBeforeRequest` 里 `m_SimulateModem` 块加：

```javascript
if (m_SimulateModem) {
    oSession["request-trickle-delay"] = "300";
    oSession["response-trickle-delay"] = "2000";  // 响应每 KB 延迟 2000ms，让客户端 0.5s 超时
}
```

`Rules → Performance → Simulate Modem Speeds` 勾选开启。

- [ ] **Step 2: 跑购买用例，记录「重复扣款」**

```bash
cd /d/game-perf-test && python -m pytest tests/test_weaknet.py::test_buy_weaknet_duplicate_charge -v -s
```

Expected: 打印 `初始 1000 -> 弱网重试后 700`，断言 `== 700`（gold0-300）通过，证明「超时重试导致重复扣款」。

- [ ] **Step 3: 跑抽卡用例，记录抽卡重复扣款**

```bash
cd /d/game-perf-test && python -m pytest tests/test_weaknet.py::test_gacha_weaknet_duplicate_charge -v -s
```

- [ ] **Step 4: 换「限速档」重复**

改 `m_SimulateModem` 为限速（`request-trickle-bandwidth` / `response-trickle-bandwidth` 设小值如 57344），记录接口在低带宽下的响应时间变化。

- [ ] **Step 5: 换「丢包档」重复**

Fiddler 原生不支持丢包，在 `OnBeforeRequest` 加：

```javascript
if (Math.random() < 0.05) { oSession.Abort(); }  // 5% 随机丢包
```

跑脚本记录请求失败率。

- [ ] **Step 6: 换「基线档」记录对照**

关掉 Simulate Modem Speeds，跑脚本记录正常网络下的响应时间和数据一致性，作为基线。

- [ ] **Step 7: 幂等修复后复验（前置：B 项目 /shop/buy 已加 Idempotency-Key）**

```bash
cd /d/game-perf-test && python -m pytest tests/test_weaknet.py::test_buy_idempotency_key_prevents_duplicate_charge -v -s
```

Expected: 打印 `幂等修复后：初始 1000 -> 同 key 重试后 900`，断言 `== 900` 通过，证明带幂等键重试不重复扣款。

- [ ] **Step 8: 测试完恢复 Fiddler**

取消 `Simulate Modem Speeds`（Ctrl+M），删除丢包脚本，避免影响后续正常上网。

**验收：** 五档（基线/延迟/限速/丢包/超时重试）都有记录；购买重复扣款有明确断言结论。

---

## Task 5: 产出专项报告

**Files:**
- Create: `D:\game-perf-test\README.md`（专项报告）

- [ ] **Step 1: 写性能部分**

用 Task 2 的三档画质数据，写：画质三档对比数据表（帧率 / 帧时间 P50/P99 / 1% Low / Jank / 内存）、帧时间分析、结论（画质对性能的边际代价）。

- [ ] **Step 2: 写弱网部分**

用 Task 4 的五档记录，写：弱网场景对比表、购买 + 抽卡重复扣款缺陷的复现与根因（POST 无幂等设计）、Idempotency-Key 修复与复验结论。

- [ ] **Step 3: 写「怎么测」的方法论段落**

针对面试，写清：① 帧率为何不能只看平均 FPS（要看帧时间 P99 / Jank）；② 弱网怎么模拟（Fiddler trickle-delay / bandwidth / Abort 丢包）；③ 弱网下购买重复扣款怎么测、根因是什么、怎么解决（幂等键 / 防重提交）。

- [ ] **Step 4: 自检**

报告里每处数据都来自真实采集/实测，无编造数字；性能指标含帧时间 P50/P99 和 Jank，不只平均 FPS。

**验收：** 报告完整，能支撑面试讲清「帧率怎么测」「弱网怎么测」「购买重复扣款怎么测」。

---

## 完成标准（全部 Task 验收通过）

- [ ] CapFrameX 三档画质数据已导出，含帧时间 P50/P99 和 Jank
- [ ] 弱网测试脚本能连真实服务 + Fiddler 代理，购买重复扣款有断言结论
- [ ] 五档弱网场景都有记录
- [ ] 专项报告完整，无编造数据
- [ ] 面试能讲清：帧率不能只看平均 FPS、弱网怎么模拟、购买重复扣款怎么测
