"""
交互式群分类器 — 翻页扫描全部群聊 + 按键分类
用法: python scripts/classify_groups.py
"""
import sys
import time
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_DIR.parent.parent
for p in [str(PROJECT_DIR), str(WORKSPACE_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from wxauto4 import WeChat
from wxauto4.param import WxParam

WxParam.LANGUAGE = 'cn'
MAP_FILE = PROJECT_DIR / "data" / "group_map.json"


def load_map():
    if MAP_FILE.exists():
        return json.loads(MAP_FILE.read_text(encoding='utf-8'))
    return {}


def save_map(gmap):
    MAP_FILE.write_text(json.dumps(gmap, ensure_ascii=False, indent=2), encoding='utf-8')


def scan_all_groups(wx):
    """从上往下翻页：每页从下往上遍历，最底项做书签，遇书签=到底"""
    sb = wx.SessionBox
    sl = sb.session_list
    sb.go_top()
    time.sleep(0.3)

    seen = set()
    all_groups = []
    bookmark = None
    page = 0

    while True:
        page += 1
        children = sl.GetChildren()
        page_items = 0

        for item in reversed(children):
            try:
                item.Click()
                time.sleep(0.2)
                info = wx.ChatInfo()
                name = info.get('chat_name', '')
                ctype = info.get('chat_type', '')

                if bookmark and ctype == 'group' and name == bookmark:
                    page_items = -1
                    break

                if ctype == 'group' and name and name not in seen:
                    seen.add(name)
                    page_items += 1
                    all_groups.append((name, info.get('group_member_count', '?')))
            except:
                continue

        if page_items == -1:
            break

        # 记最底项为书签
        try:
            children[-1].Click()
            time.sleep(0.2)
            info = wx.ChatInfo()
            bookmark = info.get('chat_name', '') or children[-1].Name
        except:
            pass

        print(f"  第{page}页 +{page_items}个, 书签={bookmark}")

        sl.WheelDown(wheelTimes=5, waitTime=0.2)
        time.sleep(0.3)

    return all_groups


def main():
    gmap = load_map()
    categories = list(gmap.keys()) or ['发单群', '出单群', '测试']
    classified = set()
    for v in gmap.values():
        classified.update(v)

    print("=" * 50)
    print(" 群聊分类器 — 扫描中...")
    print("=" * 50)

    wx = WeChat(ads=False, resize=False)
    all_groups = scan_all_groups(wx)

    unclassified = [(n, c) for n, c in all_groups if n not in classified]

    print(f"\n共 {len(all_groups)} 个群, {len(unclassified)} 个未分类\n")

    if not unclassified:
        print("全部已分类！")
        return

    print("可选分类: ", end='')
    for i, cat in enumerate(categories):
        print(f"[{i+1}]{cat} ", end='')
    print("[s]跳过 [q]退出\n")

    for name, count in unclassified:
        choice = input(f"  {name} ({count}人) > ").strip().lower()
        if choice == 'q':
            break
        elif choice == 's':
            continue
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(categories):
                    cat = categories[idx]
                    gmap.setdefault(cat, []).append(name)
                    save_map(gmap)
                    print(f"    → 「{cat}」")
            except ValueError:
                pass

    gmap = load_map()
    for cat in categories:
        print(f"  {cat}: {len(gmap.get(cat, []))} 个")
    print("已保存。")


if __name__ == '__main__':
    main()
