"""
从出单群提取最新单子 → 输出 txt（v3 旧脚本直接可用）
用法: python scripts/dump_orders_txt.py

流程:
  1. 扫描所有出单群
  2. 读取消息 → 过滤非单子
  3. 去重（同单号保留最新）
  4. 输出 data/家教单.txt（每单空一行，与旧格式兼容）
"""
import sys
import json
import re
import time
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

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

from src.config import get_source_groups, _load_map

DATA_DIR = PROJECT_DIR / 'data'
OUTPUT_TXT = DATA_DIR / '家教单.txt'
XIANG_JSON = DATA_DIR / 'xiang_orders.json'

# 非单子过滤词
SKIP_KEYWORDS = ['邀请你', '加入了群聊', '撤回', '以上是打招呼']


def read_messages_ui(wx):
    """通过 UIA msgbox 读取当前可见消息"""
    children = wx.ChatBox.msgbox.GetChildren()
    msgs = []
    for c in children:
        msgs.append((c.ClassName or '', c.Name or ''))
    return msgs


def is_order(text):
    """判断是否家教单"""
    if len(text) < 30:
        return False
    if any(k in text for k in SKIP_KEYWORDS):
        return False
    return any(k in text for k in ['地址', '年级', '科目', '『地址』', '【家庭地址】',
                                     '课酬', '〖课酬', '老师报酬', '价格', '薪资', '费用'])


def extract_orders_from_group(wx):
    """从当前已打开的群提取所有单子"""
    orders = []

    # 激活窗口 + 滚轮加载历史
    hwnd = None
    def cb(h, p):
        if win32gui.IsWindowVisible(h) and '微信' in win32gui.GetWindowText(h) \
                and 'Qt' in win32gui.GetClassName(h):
            p.append(h)
        return True
    handles = []
    win32gui.EnumWindows(cb, handles)
    if handles:
        win32gui.SetForegroundWindow(handles[0])
        time.sleep(0.3)
        rect = win32gui.GetWindowRect(handles[0])
        # 点击消息区域
        pyautogui.click(rect[0] + 400, rect[1] + 250)
        time.sleep(0.2)
        # 滚到顶
        for _ in range(30):
            pyautogui.scroll(300)
            time.sleep(0.02)
        time.sleep(0.5)

    msgs = read_messages_ui(wx)
    for cls, text in msgs:
        if 'ChatTextItemView' not in cls:
            continue
        if is_order(text):
            # 拆分含多单的消息
            parts = re.split(r'\n(?=[A-Z]+\d+)', text)
            for part in parts:
                part = part.strip()
                if is_order(part):
                    orders.append(part)

    return orders


def main():
    print("=" * 40)
    print(" 出单群 → txt 提取")
    print("=" * 40)

    wx = WeChat(ads=False, resize=False)

    source_groups = get_source_groups()
    print(f"出单群: {len(source_groups)} 个")

    all_orders = OrderedDict()  # 单号 → 内容，保留最新

    # 1. 先读向老师私聊单子（最高优先级）
    if XIANG_JSON.exists():
        xiang_orders = json.loads(XIANG_JSON.read_text(encoding='utf-8'))
        for o in xiang_orders:
            oid = o.get('order_id')
            content = o.get('content', '')
            if oid and is_order(content):
                all_orders[oid] = content
        print(f"向老师私聊: {len(all_orders)} 单")

    # 2. 扫描出单群
    for group_name in source_groups:
        # 从群列表找到并打开
        found = False
        for item in wx.SessionBox.session_list.GetChildren():
            item.Click()
            time.sleep(0.2)
            info = wx.ChatInfo()
            if info.get('chat_name', '') == group_name:
                found = True
                break

        if not found:
            print(f"[SKIP] 未找到: {group_name}")
            continue

        print(f"\n群: {group_name}")
        orders = extract_orders_from_group(wx)
        print(f"  有效单子: {len(orders)}")

        for content in orders:
            oid_match = re.search(r'([A-Z]+\d+[-‐]?\d*)', content)
            oid = oid_match.group(1) if oid_match else content[:20]
            # 去重：保留最新的（后出现的覆盖先出现的）
            if oid not in all_orders or len(content) > len(all_orders[oid]):
                all_orders[oid] = content

        time.sleep(0.3)

    # 3. 写入 txt
    unique_orders = list(all_orders.values())
    text = '\n\n'.join(o.strip() for o in unique_orders)
    OUTPUT_TXT.write_text(text, encoding='utf-8')
    print(f"\n{'='*40}")
    print(f"输出: {OUTPUT_TXT}")
    print(f"共 {len(unique_orders)} 单")

    # 统计来源
    xi = sum(1 for o in unique_orders if '向老师' in o[:5] or 'NL' in o[:10] or 'M07' in o[:10])
    print(f"其中向老师单: {xi} 条")


if __name__ == '__main__':
    main()
