"""
扫描所有会话，列出群聊原名，方便填写 group_map.json
用法: python scripts/discover_groups.py
"""
import sys
import time
from pathlib import Path
import pyautogui

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_DIR.parent.parent
for p in [str(PROJECT_DIR), str(WORKSPACE_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from wxauto4 import WeChat
from wxauto4.param import WxParam
from src.config import get_target_groups, get_source_groups, _load_map

WxParam.LANGUAGE = 'cn'


def main():
    wx = WeChat(ads=False, resize=False)

    gmap = _load_map()
    targets = set(get_target_groups())
    sources = set(get_source_groups())
    tests = set(gmap.get('测试', []))

    # 从上往下翻页：每页从下往上遍历，记录最底项做书签
    # 翻页后从下往上扫，遇到上书签=到底
    seen = set()
    all_groups = []
    sb = wx.SessionBox
    sl = sb.session_list
    sb.go_top()
    time.sleep(0.3)

    bookmark = None  # 上一页的最底项
    page = 0

    while True:
        page += 1
        children = sl.GetChildren()
        page_items = 0

        # 从下往上遍历
        for item in reversed(children):
            try:
                item.Click()
                time.sleep(0.2)
                info = wx.ChatInfo()
                name = info.get('chat_name', '')
                ctype = info.get('chat_type', '')

                # 遇到上书签 → 翻到底了
                if bookmark and ctype == 'group' and name == bookmark:
                    page_items = -1
                    break

                if ctype == 'group' and name and name not in seen:
                    seen.add(name)
                    page_items += 1
                    role = '未分类'
                    if name in tests: role = '测试'
                    elif name in targets: role = '发单群'
                    elif name in sources: role = '出单群'
                    all_groups.append((name, role, info.get('group_member_count', '?')))
            except:
                continue

        if page_items == -1:
            break

        # 记录本页最底项作为书签
        try:
            bottom = children[-1]
            bottom.Click()
            time.sleep(0.2)
            info = wx.ChatInfo()
            bookmark = info.get('chat_name', '') or bottom.Name
        except:
            pass

        print(f"  第{page}页 +{page_items}个, 书签={bookmark}")

        sl.WheelDown(wheelTimes=5, waitTime=0.2)
        time.sleep(0.3)

    print(f"共 {len(all_groups)} 个群聊\n")
    for i, (name, role, count) in enumerate(all_groups):
        print(f"[{i+1:2d}] {role:6s} | {name} ({count}人)")

    print(f"\n{'='*40}")
    print(f"群聊总数: {len(all_groups)}")
    print(f"已映射发单群: {len(targets)}")
    print(f"已映射出单群: {len(sources)}")
    print(f"已映射测试: {len(tests)}")
    unclassified = sum(1 for _, role, _ in all_groups if role == '未分类')
    print(f"未分类: {unclassified}")
    if unclassified > 0:
        print(f"\n运行 classify_groups.py 进行交互式分类")


if __name__ == '__main__':
    main()
