"""
v4 群发引擎 — wxauto4 GetSession + click + 键盘发送
ChatWith/SendMsg 在微信 4.1.1 有 bug，用混合方案替代
"""
import time
import random
import pyautogui
import pyperclip
from wxauto4 import WeChat
from wxauto4.param import WxParam
from shared.utils.logger import get_logger
from .config import get_target_groups

WxParam.LANGUAGE = 'cn'
logger = get_logger(__name__)


def _find_target_sessions(wx, target_groups):
    """翻页扫描：最底项书签判底，从下往上遍历"""
    targets = set(target_groups)
    found = {}
    sb = wx.SessionBox
    sl = sb.session_list
    sb.go_top()
    time.sleep(0.3)

    bookmark = None

    while True:
        children = sl.GetChildren()
        hit = False

        for item in reversed(children):
            try:
                item.Click()
                time.sleep(0.2)
                info = wx.ChatInfo()
                name = info.get('chat_name', '')

                if bookmark and name == bookmark:
                    hit = False  # 到底
                    break

                if name in targets and name not in found:
                    found[name] = item
                    hit = True
                    if len(found) >= len(targets):
                        return found
            except:
                continue

        if not hit:
            break

        # 记最底项为书签
        try:
            children[-1].Click()
            time.sleep(0.2)
            info = wx.ChatInfo()
            bookmark = info.get('chat_name', '') or children[-1].Name
        except:
            pass

        sl.WheelDown(wheelTimes=5, waitTime=0.2)
        time.sleep(0.3)

    return found


def send(messages, groups=None, wx=None):
    """
    群发：遍历会话 → click 开群 → 键盘粘贴发送
    """
    if groups is None:
        groups = get_target_groups()

    if wx is None:
        wx = WeChat(ads=False, resize=False)

    # 先建索引
    total = len(wx.SessionBox.session_list.GetChildren())
    logger.info(f"扫描 {total} 个会话，匹配 {len(groups)} 个目标...")
    found = _find_target_sessions(wx, groups)
    logger.info(f"匹配到 {len(found)} 个目标群")

    for group in groups:
        if group not in found:
            logger.warning(f"未找到: {group}")
            continue

        start = time.time()
        s = found[group]
        s.Click()
        time.sleep(random.uniform(0.5, 1.0))

        for msg in messages:
            pyperclip.copy(msg)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(random.uniform(0.1, 0.3))
            pyautogui.press('enter')
            # 每条消息间隔 1~3 秒，模拟人类打字
            time.sleep(random.uniform(1.0, 3.0))

        logger.info(f"<{group}> {len(messages)} 条, {time.time() - start:.1f}s")

        # 群间休息 3~8 秒
        if group != groups[-1]:
            delay = random.uniform(3.0, 8.0)
            logger.info(f"休息 {delay:.0f}s...")
            time.sleep(delay)

    logger.info("全部发送完成")
