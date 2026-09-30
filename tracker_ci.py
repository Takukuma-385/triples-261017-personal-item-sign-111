import json, os, sys, requests
from datetime import datetime
from pathlib import Path
import pytz

TW = pytz.timezone("Asia/Taipei")
STATE_FILE = Path("state.json")

def now_tw(): return datetime.now(TW)
def now_str(): return now_tw().strftime("%Y/%m/%d %H:%M:%S")
def parse_tw(s):
    return TW.localize(datetime.strptime(s, "%Y-%m-%d %H:%M"))

def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

def save_state(s):
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))

def get_active_rule(cfg):
    now = now_tw()
    for rule in cfg.get("schedules", []):
        try:
            if parse_tw(rule["start"]) <= now <= parse_tw(rule["end"]):
                return rule
        except Exception:
            pass
    return None

def fetch_all_variants(url):
    json_url = url.rstrip("/")
    if not json_url.endswith(".json"):
        json_url += ".json"
    try:
        r = requests.get(json_url, timeout=15, headers={"User-Agent": "KMonstar-CI/1.0"})
        r.raise_for_status()
        d = r.json()
        return {v["id"]: v.get("inventory_quantity", 0) for v in d.get("variants", [])}
    except Exception as e:
        print(f"[錯誤] {e}"); return None

def send_dc(url, msg):
    if not url: print(msg); return
    try: requests.post(url, json={"content": msg}, timeout=10).raise_for_status()
    except Exception as e: print(f"[DC錯誤] {e}")

def main():
    cfg     = json.loads(Path("config.json").read_text(encoding="utf-8"))
    state   = load_state()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL") or cfg.get("discord_webhook_url", "")
    rule    = get_active_rule(cfg)

    print(f"[CI] {now_str()}")
    if not rule:
        print("[CI] 不在排程時段，結束"); sys.exit(0)

    url = cfg.get("product_url", "").strip()
    if not url:
        print("[錯誤] config.json 缺少 product_url"); sys.exit(1)

    all_variants = fetch_all_variants(url)
    if all_variants is None:
        print("[錯誤] 無法取得商品資料"); sys.exit(1)

    for v_cfg in cfg.get("variants", []):
        vid  = v_cfg.get("variant_id")
        name = v_cfg.get("custom_name", str(vid))
        key  = str(vid)

        inv_now = all_variants.get(vid)
        if inv_now is None:
            print(f"[警告] variant_id {vid} 在商品中找不到，略過")
            continue

        inv_prev = state.get(key)

        if inv_prev is not None and inv_now != inv_prev:
            diff = inv_prev - inv_now
            sign = f"+{diff}" if diff > 0 else str(diff)
            msg = f"❗️【銷量變動】\n成員：{name}\n時間：{now_str()}\n庫存：{inv_now} ({sign})"
            print(msg); send_dc(webhook, msg)

        msg = f"【自動更新】\n成員：{name}\n時間：{now_str()}\n庫存：{inv_now}"
        print(msg); send_dc(webhook, msg)
        state[key] = inv_now

    save_state(state)

if __name__ == "__main__":
    main()
