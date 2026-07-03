"""
提取出单群全部消息：发送人、时间、单子信息、转发内容
输出: data/orders_raw.jsonl（原始消息）, data/orders_parsed.jsonl（解析后的单子）
用法: python scripts/extract_orders.py
"""
import sys
import json
import time
import re
from pathlib import Path
from collections import defaultdict

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_DIR.parent.parent
for p in [str(PROJECT_DIR), str(WORKSPACE_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from wxauto4.param import WxParam
WxParam.LANGUAGE = 'cn'
from wxauto4 import WeChat
from src.config import get_source_groups, _load_map

DATA_DIR = PROJECT_DIR / "data"
RAW_FILE = DATA_DIR / "orders_raw.jsonl"
PARSED_FILE = DATA_DIR / "orders_parsed.jsonl"


def scan_all_groups(wx):
    """书签翻页扫描，返回 {群名: ListItem}"""
    sb = wx.SessionBox
    sl = sb.session_list
    sb.go_top()
    time.sleep(0.3)

    found = {}
    bookmark = None

    while True:
        children = sl.GetChildren()
        hit_new = False

        for item in reversed(children):
            try:
                item.Click()
                time.sleep(0.2)
                info = wx.ChatInfo()
                name = info.get('chat_name', '')
                if bookmark and name == bookmark:
                    hit_new = False
                    break
                if name and name not in found:
                    found[name] = item
                    hit_new = True
            except:
                continue

        if not hit_new:
            break

        try:
            children[-1].Click()
            time.sleep(0.2)
            bookmark = wx.ChatInfo().get('chat_name', '') or children[-1].Name
        except:
            pass

        sl.WheelDown(wheelTimes=5, waitTime=0.2)
        time.sleep(0.3)

    return found


def extract_merge_content(msg):
    """递归读取转发/合并消息的文本内容"""
    parts = []
    try:
        if msg.type == 'merge':
            # 合并消息（聊天记录）→ 展开
            inner = msg.get_content() if hasattr(msg, 'get_content') else []
            if isinstance(inner, list):
                for m in inner:
                    parts.append(f"[{getattr(m, 'sender', '?')}] {getattr(m, 'content', '')}")
            else:
                parts.append(str(inner))
        elif msg.type == 'note':
            if hasattr(msg, 'to_markdown'):
                parts.append(msg.to_markdown())
            elif hasattr(msg, 'get_content'):
                parts.extend(msg.get_content())
        else:
            content = str(getattr(msg, 'content', ''))
            if content:
                parts.append(content)
    except Exception as e:
        parts.append(f"[解析失败: {e}]")
    return '\n'.join(parts)


def parse_order_info(text):
    """从消息文本中提取单子信息"""
    info = {}
    # 单号
    m = re.search(r'([A-Z]+\d+[-－]\d*)\s*[（(]', text)
    if m:
        info['order_id'] = m.group(1)

    # 年级
    m = re.search(r'(?:年级|年级：)\s*[：:]*\s*([^\s，。,]+)', text)
    if m:
        info['grade'] = m.group(1)

    # 科目
    m = re.search(r'(?:科目|科目：)\s*[：:]*\s*([^\s，。,]+)', text)
    if m:
        info['subject'] = m.group(1)

    # 地址
    m = re.search(r'(?:地址|授课地址|『地址』)[：:]*\s*([^\n]{5,40})', text)
    if m:
        info['address'] = m.group(1).strip()

    # 课酬
    m = re.search(r'(?:课酬|费用|薪资|〖课酬〗)[：:]*\s*([^\n]{3,20})', text)
    if m:
        info['fee'] = m.group(1).strip()

    # 要求
    m = re.search(r'(?:『要求』|要求：|要求:)\s*([^\n]{5,100})', text)
    if m:
        info['requirement'] = m.group(1).strip()

    return info


def main():
    print("=" * 50)
    print("出单群消息提取")
    print("=" * 50)

    wx = WeChat(ads=False, resize=False)
    all_sessions = scan_all_groups(wx)

    source_groups = get_source_groups()
    print(f"出单群({len(source_groups)}个): {source_groups}")

    all_messages = []
    all_orders = []
    stats = defaultdict(lambda: {'count': 0, 'senders': defaultdict(int)})

    for group_name in source_groups:
        if group_name not in all_sessions:
            print(f"\n[SKIP] 未找到: {group_name}")
            continue

        print(f"\n{'='*40}")
        print(f"群: {group_name}")

        item = all_sessions[group_name]
        item.Click()
        time.sleep(0.5)

        try:
            wx.LoadMoreMessage()
        except:
            pass
        time.sleep(0.5)

        try:
            msgs = wx.GetAllMessage()
        except Exception as e:
            print(f"  读取失败: {e}")
            continue

        print(f"  消息总数: {len(msgs)}")

        group_orders = 0
        for msg in msgs:
            sender = getattr(msg, 'sender', '?')
            mtype = getattr(msg, 'type', '?')
            content = str(getattr(msg, 'content', ''))
            msg_time = str(getattr(msg, 'time', ''))

            record = {
                'group': group_name,
                'sender': sender,
                'type': mtype,
                'time': msg_time,
                'content': content[:2000],
            }

            # 展开合并消息
            if mtype == 'merge':
                record['merge_content'] = extract_merge_content(msg)

            all_messages.append(record)
            stats[group_name]['count'] += 1
            stats[group_name]['senders'][sender] += 1

            # 解析单子信息
            full_text = content
            if mtype == 'merge':
                full_text = record.get('merge_content', content)

            order_info = parse_order_info(full_text)
            if order_info:
                order_info['group'] = group_name
                order_info['sender'] = sender
                order_info['time'] = msg_time
                all_orders.append(order_info)
                group_orders += 1

        print(f"  解析单子: {group_orders} 条")
        time.sleep(0.3)

    # 保存
    with open(RAW_FILE, 'w', encoding='utf-8') as f:
        for m in all_messages:
            f.write(json.dumps(m, ensure_ascii=False) + '\n')

    with open(PARSED_FILE, 'w', encoding='utf-8') as f:
        for o in all_orders:
            f.write(json.dumps(o, ensure_ascii=False) + '\n')

    # 统计
    print(f"\n{'='*50}")
    print(f"总计: {len(all_messages)} 条消息, {len(all_orders)} 条单子")
    print(f"\n--- 各群统计 ---")
    for g, s in stats.items():
        top3 = sorted(s['senders'].items(), key=lambda x: x[1], reverse=True)[:3]
        print(f"  {g}: {s['count']} 条消息")
        print(f"    活跃发送人: {top3}")

    print(f"\n原始数据: {RAW_FILE}")
    print(f"解析单子: {PARSED_FILE}")


if __name__ == '__main__':
    main()
