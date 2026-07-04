"""
新朋友监控：检测新会话 → 自动发送引导话术
用法: python scripts/monitor_new_friends.py

流程:
  1. 手机端手动通过好友申请
  2. PC端脚本检测到新个人会话
  3. 自动发话术: 请发单子编号或内容
  4. 记录到 data/new_friends.jsonl
"""
import sys
import json
import re
import time
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_DIR.parent.parent
for p in [str(PROJECT_DIR), str(WORKSPACE_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from wxauto4.param import WxParam
WxParam.LANGUAGE = 'cn'
from wxauto4 import WeChat
import pyautogui, pyperclip

# ── 话术模板 ──
MSG_GUIDE = "你好！请直接发送你想咨询的家教单编号或内容（如 M443-5），我会尽快回复你～"

MSG_IMAGE = "请发一下单子的编号或文字内容，截图可能识别不准确哦～"

MSG_ASK_RESUME = "请发一下你的简历，格式参考：\n- 姓名\n- 学校/学历\n- 家教经验（科目、年级、时长）\n- 可上课时间\n（请不要在简历中留联系方式）"

MSG_RECEIVED = "收到！请等待家长审核，通过后会通知你支付信息费。"

DATA_FILE = PROJECT_DIR / "data" / "new_friends.jsonl"
KNOWN_FILE = PROJECT_DIR / "data" / "known_sessions.txt"
STATE_FILE = PROJECT_DIR / "data" / "conversation_state.json"

SCAN_INTERVAL = 5  # 扫描间隔秒


def load_state():
    """加载对话状态 {chat_name: {stage, last_msg, ...}}"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def load_known():
    if KNOWN_FILE.exists():
        return set(KNOWN_FILE.read_text(encoding='utf-8').splitlines())
    return set()


def save_known(known):
    KNOWN_FILE.write_text('\n'.join(sorted(known)), encoding='utf-8')


def log_friend(info):
    with open(DATA_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(info, ensure_ascii=False) + '\n')


def send_message(msg):
    pyperclip.copy(msg)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.1)
    pyautogui.press('enter')
    time.sleep(0.3)


def get_last_teacher_message(wx, known_content=None):
    """获取联系人最后一条非己发消息"""
    try:
        msgs = wx.GetAllMessage()
        for m in reversed(msgs):
            if hasattr(m, 'attr') and m.attr == 'self':
                continue
            if m.type == 'text' and hasattr(m, 'content'):
                content = str(m.content)
                if content and content != known_content:
                    return content
    except:
        pass
    return None


def scan_sessions(wx):
    sl = wx.SessionBox.session_list
    sessions = {}
    for item in sl.GetChildren():
        try:
            item.Click()
            time.sleep(0.15)
            info = wx.ChatInfo()
            name = info.get('chat_name', '')
            ctype = info.get('chat_type', '')
            if name and name not in sessions:
                sessions[name] = {'type': ctype, 'info': info}
        except:
            continue
    return sessions


def classify_intent(text, msg_type):
    """分类老师意图"""
    if msg_type in ('image', 'picture', 'video'):
        return 'image'
    if len(text) > 100 and any(k in text for k in ['地址', '年级', '科目', '要求', '课酬', '『', '【']):
        return 'order_full'
    if re.search(r'[A-Za-z]+\d+[-−]?\d*', text):
        return 'order_id'
    if any(k in text for k in ['信息费', '多少钱', '出了吗', '还有', '单吗']):
        return 'ask_fee'
    if any(k in text for k in ['代理', '招代理', '回收']):
        return 'ask_agent'
    if any(k in text for k in ['你好', '哈喽', '您好', 'hello', 'hi', '嗨']):
        return 'greet'
    if len(text) > 50:
        return 'order_full'
    return 'unknown'


def handle_new_conversation(wx, name):
    """新朋友对话处理"""
    state = load_state()

    if name not in state:
        send_message(MSG_GUIDE)
        state[name] = {'stage': 'waiting_order'}
        save_state(state)
        print(f"  -> [引导] {MSG_GUIDE[:30]}...")
        log_friend({'time': datetime.now().isoformat(), 'name': name, 'action': 'greeting'})
        return

    st = state[name]
    teacher_msg = get_last_teacher_message(wx)
    if not teacher_msg:
        return

    # 获取最后一条消息类型
    msg_type = 'text'
    try:
        msgs = wx.GetAllMessage()
        for m in reversed(msgs):
            if not hasattr(m, 'attr') or m.attr != 'self':
                msg_type = m.type if hasattr(m, 'type') else 'text'
                break
    except:
        pass

    intent = classify_intent(teacher_msg, msg_type)

    if st['stage'] == 'waiting_order':
        if intent == 'image':
            send_message(MSG_IMAGE)
            st['stage'] = 'waiting_order'
        elif intent in ('order_full', 'order_id', 'ask_fee'):
            st['order_text'] = teacher_msg
            st['stage'] = 'resume_requested'
            send_message(MSG_ASK_RESUME)
            print(f"  -> [要简历]")
        elif intent == 'ask_agent':
            send_message('代理相关问题请加大号微信咨询哦～')
            st['stage'] = 'done'
        else:
            send_message(MSG_GUIDE)

    elif st['stage'] == 'resume_requested':
        st['resume'] = teacher_msg
        st['stage'] = 'done'
        send_message(MSG_RECEIVED)
        print(f"  -> [确认收到]")

    save_state(state)


def main():
    print("=" * 40)
    print(" 新朋友监控 (手动通过 + 多轮话术)")
    print("=" * 40)

    wx = WeChat(ads=False, resize=False)
    known = load_known()

    # 初始化基线
    current = scan_sessions(wx)
    for name in current:
        known.add(name)
    save_known(known)

    print(f"当前 {len(current)} 个会话，监控中...")
    print(f"请在手机上手动通过好友申请")
    print(f"=" * 40)

    # 也检查已知联系人有无新消息
    while True:
        try:
            current = scan_sessions(wx)
            state = load_state()

            # 新会话 → 发第一轮话术
            new_names = set(current.keys()) - known
            for name in new_names:
                info = current[name]
                if info['type'] == 'friend':
                    print(f"\n[{datetime.now():%H:%M:%S}] 新朋友: {name}")
                    wx.ChatWith(name)
                    time.sleep(0.5)
                    handle_new_conversation(wx, name)
                known.add(name)
            save_known(known)

            # 已有会话但 state 未完成 → 继续对话
            for name in state:
                if state[name].get('stage') not in (None, 'done'):
                    if name in current:
                        wx.ChatWith(name)
                        time.sleep(0.5)
                        print(f"\n[{datetime.now():%H:%M:%S}] 跟进: {name}")
                        handle_new_conversation(wx, name)

            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            print("\n已停止")
            break
        except Exception as e:
            print(f"异常: {e}")
            time.sleep(SCAN_INTERVAL)


if __name__ == '__main__':
    main()
