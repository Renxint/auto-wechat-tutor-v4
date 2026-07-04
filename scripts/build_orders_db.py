"""
从出单群 UIA 读消息 → 解析 → 结构化入库 → 去重 → 标记已出 → 导出txt

一个脚本完成全部链路，来源/分成在读消息时直接标注（不从txt反推）

用法: python scripts/build_orders_db.py
"""
import sys, re, time, json, sqlite3
from pathlib import Path
from datetime import datetime, date
from collections import OrderedDict

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_DIR.parent.parent
for p in [str(PROJECT_DIR), str(WORKSPACE_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from wxauto4.param import WxParam
WxParam.LANGUAGE = 'cn'
from wxauto4 import WeChat
import win32gui, win32con, pyautogui

from src.config import get_source_groups, _load_map

DATA_DIR = PROJECT_DIR / 'data'
DB_PATH = DATA_DIR / 'orders_v2.db'
OUTPUT_TXT = DATA_DIR / '家教单.txt'
XIANG_JSON = DATA_DIR / 'xiang_orders.json'

SKIP_KEYWORDS = ['邀请你加入', '加入了群聊', '撤回', '以上是打招呼']

# ── 数据库 ──

def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.executescript('''
        DROP TABLE IF EXISTS orders;
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            city TEXT,
            grade TEXT,
            subject TEXT,
            fee TEXT,
            address TEXT,
            requirement TEXT,
            schedule TEXT,
            is_summer INTEGER DEFAULT 0,
            is_bang INTEGER DEFAULT 0,
            source TEXT,
            commission TEXT,
            agent_name TEXT,
            group_name TEXT,
            content TEXT,
            content_hash TEXT UNIQUE,
            first_seen TEXT,
            last_seen TEXT,
            active INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_oid ON orders(order_id);
        CREATE INDEX IF NOT EXISTS idx_source ON orders(source);
        CREATE INDEX IF NOT EXISTS idx_active ON orders(active);
        CREATE INDEX IF NOT EXISTS idx_city ON orders(city);
    ''')
    return db


# ── 消息读取 ──

def read_group_messages(wx):
    """UIA msgbox 读取消息，翻页加载"""
    handles = []
    def cb(h, p):
        if win32gui.IsWindowVisible(h) and '微信' in win32gui.GetWindowText(h) \
                and 'Qt' in win32gui.GetClassName(h):
            p.append(h)
        return True
    win32gui.EnumWindows(cb, handles)
    if not handles:
        return []

    win32gui.SetForegroundWindow(handles[0])
    time.sleep(0.2)
    r = win32gui.GetWindowRect(handles[0])
    pyautogui.click(r[0] + 400, r[1] + 200)
    time.sleep(0.1)

    seen = set()
    texts = []
    for _ in range(20):
        for c in wx.ChatBox.msgbox.GetChildren():
            if 'ChatTextItemView' in str(c.ClassName):
                name = c.Name
                h = hash(name[:80])
                if h not in seen:
                    seen.add(h)
                    texts.append(name)
        pyautogui.scroll(300)
        time.sleep(0.02)
    return texts


# ── 单子解析 ──

def is_order(text):
    if len(text) < 20:
        return False
    if any(k in text for k in SKIP_KEYWORDS):
        return False
    return bool(re.search(r'[A-Za-z]+\d+', text)) or \
           any(k in text for k in ['地址', '年级', '科目', '课酬', '薪酬', '费用', '价格', '薪资',
                                    '〖', '『', '授课位置', '老师要求', '课时费'])


def split_orders(text):
    """按双换行拆分单子块"""
    text = re.sub(r'\n={2,}\n', '\n\n', text)
    blocks = re.split(r'\n\s*\n', text)
    return [b.strip() for b in blocks if is_order(b.strip())]


def extract_compact_fields(content):
    """解析单行紧凑格式:
       S系列: 🍃S217512【初三物理化学龙华区海濂一横路】新初3男...
       bos系列: 【暑假单】bos64433：桂林洋...，男孩，初升高...
    """
    f = {}
    m = re.search(r'([A-Za-z]+\d+)', content)
    if m: f['order_id'] = m.group(1)

    # 城市
    for city in ['海口', '三亚', '老城', '儋州', '澄迈', '屯昌', '琼海', '桂林洋']:
        if city in content: f['city'] = city; break

    # 判断是 S 系列(bracket=科目+地点) 还是 bos 系列(bracket=标签)
    is_bos = 'bos' in content.lower() or 'os' in content[:5].lower()

    if not is_bos:
        # S系列: 【科目+地点】正文
        m = re.search(r'【(.+?)】', content)
        if m:
            bracket = m.group(1)
            for subj in ['物理', '化学', '数学', '英语', '语文', '生物', '地理', '全科', '政治', '历史']:
                if subj in bracket:
                    f['subject'] = (f.get('subject','') + subj + ' ').strip()
            if not f.get('subject'): f['subject'] = bracket[:15]
            for area in ['龙华', '秀英', '美兰', '琼山', '吉阳', '天涯', '海棠']:
                if area in bracket: f['city'] = f.get('city') or '海口'; break

        m = re.search(r'】(.+?)(?:，|。)', content)
        grade_text = m.group(1) if m else ''
        if grade_text:
            m2 = re.search(r'(?:([初高小]\w{0,2})|(\d\s*年级)|(幼小衔接)|(新?[初高小]\d))', grade_text)
            if m2: f['grade'] = m2.group(0).strip()

    else:
        # bos/os系列: ID后跟：地址，年级+科目...
        # 去掉前面的【标签】
        clean = re.sub(r'【[^】]+】', '', content)
        # 分号后面是正文
        parts = clean.split('：', 1) if '：' in clean else clean.split(':', 1)
        body = parts[1] if len(parts) > 1 else clean
        # 提取年级
        m = re.search(r'(?:([初高小]\w{0,2}(?:升[初高小]\w{0,2})?)|(\d\s*年级)|(幼小衔接)|(新?[初高小]\d))', body)
        if m: f['grade'] = m.group(0).strip()
        # 提取科目
        for subj in ['物理', '化学', '数学', '英语', '语文', '生物', '地理', '全科', '政治', '历史']:
            if subj in body:
                f['subject'] = (f.get('subject','') + subj + ' ').strip()
        if not f.get('subject'):
            m = re.search(r'[升初高小]+(.+?)[，,]', body)
            if m: f['subject'] = m.group(1)[:10]

    # 课酬: 多种格式
    for pat in [r'(\d+[-‐]?\d*/[h时次小])', r'(\d+[-‐]?\d*元?/[h时次小])',
                r'(?:，|,)\s*(\d+[-‐]?\d*/[次h])', r'(\d+[/h时])']:
        m = re.search(pat, content)
        if m and '暑假' not in m.group(1): f['fee'] = m.group(1); break

    f['is_summer'] = bool(re.search(r'暑假|假期', content))
    f['is_bang'] = False
    return f


def extract_fields(content):
    """提取结构化字段（先试标准格式，不行再用紧凑格式）"""
    f = {}

    m = re.search(r'([A-Z]+\d+[-‐]?\d*)', content)
    if m: f['order_id'] = m.group(1)
    else:
        m = re.search(r'([a-z]{2}\d+)', content)
        if m: f['order_id'] = m.group(1)

    # 判格式: 标准格式有『或【标签】
    is_compact = not any(k in content for k in ['『地址』', '『年级』', '【家庭地址】', '地址：', '地址:'])

    if is_compact:
        f.update(extract_compact_fields(content))
    else:
        for city in ['海口', '三亚', '老城', '儋州', '澄迈', '屯昌', '琼海']:
            if city in content:
                f['city'] = city; break

        m = re.search(r'(?:『年级』|年级[：:＝]|【年级[^】]*】[：:]?|几年级[：:：])\s*(.{3,15})', content)
        if m: f['grade'] = m.group(1).strip()

        m = re.search(r'(?:『科目[^』]*』|科目[：:＝]|【科目[^】]*】[：:]?|补习科目[：:：])\s*(.{3,20})', content)
        if m: f['subject'] = m.group(1).strip()

        m = re.search(r'(?:〖课酬〗|课酬|老师报酬|薪酬|价格|费用|课时费)[：:＝]?\s*([^\n]{3,20})', content)
        if m: f['fee'] = m.group(1).strip()

        m = re.search(r'(?:『地址』|地址[：:＝]|【地址[^】]*】[：:]?|授课位置[：:])\s*(.{5,40})', content)
        if m: f['address'] = m.group(1).strip()

        m = re.search(r'(?:『要求』|要求[：:＝]|【老师要求】[：:]?|对老师的要求[：:])\s*(.{5,80})', content)
        if m: f['requirement'] = m.group(1).strip()

        m = re.search(r'(?:『时间』|时间[：:＝]|上课时间[：:]|每周次数[：:])\s*(.{5,60})', content)
        if m: f['schedule'] = m.group(1).strip()

    f['is_summer'] = bool(re.search(r'暑假|假期', content))
    f['is_bang'] = ('帮字单' in content)
    return f


def determine_source(content, group_name, agent_name=''):
    """根据群名/发送人判断来源和分成"""
    # 向老师
    if any(k in (agent_name or '') for k in ['狮子岭', '向老师']):
        return '向老师(狮子岭)', '5成'
    if any(k in content for k in ['NL', 'MG', 'M07']) and re.search(r'[A-Z]+\d+[（(]', content):
        if '沟通群' in (group_name or ''):
            return '向老师(狮子岭)', '5成'
    # 郑老师
    if any(k in (agent_name or '') for k in ['郑老师', '楚老师']):
        return '郑老师', '2-3成'
    if '楚老师' in content or re.search(r'(?:海口|楚老师).{0,5}家庭单\d+', content):
        return '郑老师', '2-3成'
    # 奥利给
    if re.match(r'[a-z]{2}\d+', content.strip()):
        return '奥利给', '2-3成'
    # 李老师
    if any(k in content[:30] for k in ['海口暑假', '老城暑假', '海口上门']):
        return '李老师', '2-3成'
    # 其他
    if '合作出单' in (group_name or ''):
        return '奥利给', '2-3成'
    if '海大' in (group_name or ''):
        return '奥利给', '2-3成'
    if '海岛' in (group_name or ''):
        return '奥利给', '2-3成'
    if '郑老师' in (group_name or ''):
        return '郑老师', '2-3成'
    if '沟通群' in (group_name or ''):
        return '向老师(狮子岭)', '5成'
    return '未知', '未知'


# ── 入库 + 导出 ──

def import_xiang(db):
    if not XIANG_JSON.exists(): return 0
    now = datetime.now().isoformat()
    xiang_data = json.loads(XIANG_JSON.read_text(encoding='utf-8'))
    count = 0
    for o in xiang_data:
        content = o.get('content', '')
        for part in split_orders(content) or [content]:
            if is_order(part):
                fields = extract_fields(part)
                h = str(hash(part))
                db.execute('''INSERT OR IGNORE INTO orders(order_id, city, grade, subject, fee, address,
                              requirement, schedule, is_summer, is_bang, source, commission,
                              agent_name, group_name, content, content_hash, first_seen, last_seen, active)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)''',
                           [fields.get('order_id'), fields.get('city'), fields.get('grade'),
                            fields.get('subject'), fields.get('fee'), fields.get('address'),
                            fields.get('requirement'), fields.get('schedule'),
                            int(fields.get('is_summer', 0)), int(fields.get('is_bang', 0)),
                            '向老师(狮子岭)', '5成', '向老师(狮子岭)', '私聊', part, h, now, now])
                count += 1
    db.commit()
    return count


def import_group(db, wx, group_name):
    """读群 + 解析 + 入库"""
    for item in wx.SessionBox.session_list.GetChildren():
        item.Click(); time.sleep(0.2)
        if wx.ChatInfo().get('chat_name', '') == group_name:
            break
    else:
        return 0

    texts = read_group_messages(wx)
    now = datetime.now().isoformat()
    count = 0

    # 李老师群：全量替换
    is_li = ('李老师' in group_name or '鹏' in group_name)

    if is_li:
        all_parts = []
        for t in texts:
            if is_order(t):
                all_parts.extend(split_orders(t))
        seen = OrderedDict()
        for p in all_parts:
            oid = extract_fields(p).get('order_id') or p[:40]
            seen[oid] = p
        parts = list(seen.values())
        if parts:
            li_ids = set()
            for p in parts:
                fields = extract_fields(p)
                source, comm = determine_source(p, group_name, '李老师')
                oid = fields.get('order_id') or f'li_{abs(hash(p[:30]))}'
                li_ids.add(oid)
                h = str(hash(p))
                db.execute('''INSERT OR REPLACE INTO orders(order_id, city, grade, subject, fee, address,
                              requirement, schedule, is_summer, is_bang, source, commission,
                              agent_name, group_name, content, content_hash, first_seen, last_seen, active)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)''',
                           [oid, fields.get('city'), fields.get('grade'), fields.get('subject'),
                            fields.get('fee'), fields.get('address'), fields.get('requirement'),
                            fields.get('schedule'), int(fields.get('is_summer', 0)), int(fields.get('is_bang', 0)),
                            source, comm, '李老师', group_name, p, h, now, now])
                count += 1
            # 旧单标记已出
            if li_ids:
                ph = ','.join('?' * len(li_ids))
                db.execute(f'''UPDATE orders SET active=0, last_seen=? WHERE agent_name='李老师'
                               AND order_id NOT IN ({ph}) AND source='李老师' ''', [now] + list(li_ids))
            db.commit()
    else:
        for t in texts:
            if not is_order(t): continue
            for p in split_orders(t):
                fields = extract_fields(p)
                source, comm = determine_source(p, group_name)
                oid = fields.get('order_id') or f'{group_name[:4]}_{abs(hash(p[:30]))}'
                h = str(hash(p))
                db.execute('''INSERT OR REPLACE INTO orders(order_id, city, grade, subject, fee, address,
                              requirement, schedule, is_summer, is_bang, source, commission,
                              agent_name, group_name, content, content_hash, first_seen, last_seen, active)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)''',
                           [oid, fields.get('city'), fields.get('grade'), fields.get('subject'),
                            fields.get('fee'), fields.get('address'), fields.get('requirement'),
                            fields.get('schedule'), int(fields.get('is_summer', 0)), int(fields.get('is_bang', 0)),
                            source, comm, '', group_name, p, h, now, now])
                count += 1
        db.commit()

    # 2天未更新 → 可能已出
    db.execute('UPDATE orders SET active=0 WHERE last_seen < ?', [str(date.today())])
    db.commit()
    return count


def export_txt(db):
    """导出有效单子，过滤黑名单"""
    gmap = _load_map()
    blacklist = gmap.get('黑名单', [])
    rows = db.execute(
        'SELECT DISTINCT content FROM orders WHERE active=1 ORDER BY source DESC, last_seen DESC'
    ).fetchall()
    out = []
    skipped = 0
    for (content,) in rows:
        if any(b in content for b in blacklist):
            skipped += 1; continue
        out.append(content.strip())
    OUTPUT_TXT.write_text('\n\n'.join(out), encoding='utf-8')
    return len(out), skipped


# ── 主流程 ──

def main():
    print("=" * 50)
    print(" 订单数据库构建 (v2)")
    print("=" * 50)

    wx = WeChat(ads=False, resize=False)
    db = init_db()

    gmap = _load_map()
    blacklist = gmap.get('黑名单', [])

    # 1. 向老师私聊
    xc = import_xiang(db)
    print(f"向老师私聊: {xc} 单")

    # 2. 出单群
    groups = [g for g in get_source_groups() if g != 'D01+江苏+海南家教2025+楠老师']
    total = xc
    for g in groups:
        n = import_group(db, wx, g)
        total += n
        print(f"[{g[:15]}]: {n} 单")
        time.sleep(0.3)

    # 3. 导出
    exported, bl_skipped = export_txt(db)
    print(f"\n入库: {total} | 有效: {exported} | 黑名单过滤: {bl_skipped}")
    print(f"输出: {OUTPUT_TXT} ({exported} 单)")

    # 4. 导出 Excel
    try:
        import openpyxl
    except:
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'openpyxl', '-q'])
        import openpyxl

    xlsx_path = DATA_DIR / 'orders_v2.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '订单'
    headers = ['单号', '城市', '年级', '科目', '课酬', '地址', '要求', '时间安排',
               '暑假单', '帮字单', '来源', '分成', '代理', '来源群', '最近出现', '原文']
    ws.append(headers)

    rows = db.execute('''
        SELECT order_id, city, grade, subject, fee, address, requirement, schedule,
               CASE WHEN is_summer THEN '是' ELSE '' END,
               CASE WHEN is_bang THEN '是' ELSE '' END,
               source, commission, agent_name, group_name, last_seen, content
        FROM orders WHERE active=1
        ORDER BY source DESC, last_seen DESC
    ''').fetchall()

    def clean(val):
        """清除 Excel 不支持的字符"""
        if not isinstance(val, str): return val
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f​﻿\U00010000-\U0010ffff]', '', val)

    for r in rows:
        ws.append([clean(v) for v in r])

    for col, w in enumerate([14,6,12,12,14,28,32,28,6,6,18,6,16,22,20,60], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = w

    try:
        wb.save(str(xlsx_path))
    except PermissionError:
        alt = str(xlsx_path).replace('.xlsx', f'_{datetime.now().strftime("%H%M%S")}.xlsx')
        wb.save(alt)
        print(f"  (原文件被占用，保存到 {alt})")
    print(f"Excel: {xlsx_path} ({len(rows)} 行)")

    # 5. 统计
    print(f"\n=== 按来源 ===")
    for row in db.execute('SELECT source, commission, COUNT(*) FROM orders WHERE active=1 GROUP BY source ORDER BY COUNT(*) DESC'):
        print(f"  {row[0]}: {row[2]} 单 ({row[1]})")

    print(f"\n=== 按城市 ===")
    for row in db.execute('SELECT city, COUNT(*) FROM orders WHERE active=1 AND city IS NOT NULL GROUP BY city ORDER BY COUNT(*) DESC'):
        print(f"  {row[0]}: {row[1]} 单")

    db.close()


if __name__ == '__main__':
    main()
