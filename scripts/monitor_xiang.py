"""
向老师（狮子岭）私聊监控 — 实时抓取最新单子
用法: python scripts/monitor_xiang.py

- 每30秒检查一次
- UIA 直接读 msgbox 控件（绕过 GetAllMessage 缓存bug）
- 仅保留当天单子，过期自动清理
- 向老师的单 = 5成
"""
import sys
import json
import re
import time
from pathlib import Path
from datetime import datetime, date

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_DIR.parent.parent
for p in [str(PROJECT_DIR), str(WORKSPACE_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from wxauto4.param import WxParam
WxParam.LANGUAGE = 'cn'
from wxauto4 import WeChat
from wxauto4.uia import uiautomation as uia
import win32gui, win32con, pyautogui

XIANG_NAME = '狮子岭的天空2026+小号+招代理收徒'
ORDERS_FILE = PROJECT_DIR / 'data' / 'xiang_orders.json'      # 解析后（检索用）
RAW_FILE = PROJECT_DIR / 'data' / 'xiang_orders_raw.txt'       # 原文（转发用）
SCAN_INTERVAL = 30  # 秒

# 单子关键词
ORDER_KEYWORDS = ['地址', '年级', '科目', '时间', '要求', '课酬', '〖', '『']


def read_messages_ui(wx):
    """通过 UIA msgbox 直接读当前可见消息（绕过 GetAllMessage）"""
    children = wx.ChatBox.msgbox.GetChildren()
    msgs = []
    for c in children:
        name = (c.Name or '')
        cls = (c.ClassName or '')
        msgs.append({
            'class': cls,
            'name': name,
        })
    return msgs


def parse_orders(msgs):
    """从消息中提取单子，一条消息可能含多单"""
    orders = []
    for m in msgs:
        if 'ChatTextItemView' not in m['class']:
            continue
        text = m['name']
        if len(text) < 30 or not any(k in text for k in ORDER_KEYWORDS):
            continue

        # 按单号分割（每个单子以 字母+数字 编号开头）
        parts = re.split(r'\n(?=[A-Z]+\d+)', text)
        for part in parts:
            part = part.strip()
            if not part or len(part) < 30:
                continue
            oid_match = re.search(r'([A-Z]+\d+[-‐‑‒–—―]?\d*)', part)
            order_id = oid_match.group(1) if oid_match else None
            orders.append({
                'order_id': order_id,
                'content': part,
                'source': '向老师(狮子岭)',
                'commission': '5成',
                'fetched_at': datetime.now().isoformat(),
            })
    return orders


def load_orders():
    if ORDERS_FILE.exists():
        return json.loads(ORDERS_FILE.read_text(encoding='utf-8'))
    return []


def save_orders(orders):
    today = date.today().isoformat()
    fresh = [o for o in orders if o['fetched_at'][:10] >= today]
    # 解析数据（检索用）
    ORDERS_FILE.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding='utf-8')
    # 原始文本（转发用，每单空一行分隔）
    raw_parts = [o['content'].strip() for o in fresh if o.get('content')]
    RAW_FILE.write_text('\n\n'.join(raw_parts), encoding='utf-8')
    return fresh


def main():
    print("=" * 40)
    print(f" 向老师私聊监控: {XIANG_NAME}")
    print(f" 扫描间隔: {SCAN_INTERVAL}s")
    print("=" * 40)

    wx = WeChat(ads=False, resize=False)
    wx.ChatWith(XIANG_NAME)
    time.sleep(0.5)

    orders = load_orders()
    seen_ids = {o.get('order_id') for o in orders if o.get('order_id')}
    last_msg_count = 0

    print(f"已有 {len(orders)} 条今日单子, 开始监控...")

    while True:
        try:
            # 读当前消息
            msgs = read_messages_ui(wx)
            new_count = len(msgs)

            if new_count != last_msg_count:
                last_msg_count = new_count

                # 解析新单子
                new_orders = parse_orders(msgs)
                added = 0
                for o in new_orders:
                    oid = o.get('order_id')
                    if oid and oid not in seen_ids:
                        orders.append(o)
                        seen_ids.add(oid)
                        added += 1
                        print(f"[{datetime.now():%H:%M}] 新单: {oid}")

                if added:
                    orders = save_orders(orders)
                    print(f"  累计 {len(orders)} 条 (向老师5成)")
                elif new_orders:
                    pass  # 已见过的单子

            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            print(f"\n停止, 今日共 {len(orders)} 条")
            break
        except Exception as e:
            print(f"异常: {e}")
            time.sleep(SCAN_INTERVAL)


if __name__ == '__main__':
    main()
