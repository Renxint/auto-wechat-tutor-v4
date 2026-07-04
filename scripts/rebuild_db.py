"""
从 家教单.txt 重建结构化数据库
解析字段：单号/城市/年级/科目/课酬/要求/地址/来源/分成
"""
import sys, re, sqlite3, json
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_DIR.parent.parent
for p in [str(PROJECT_DIR), str(WORKSPACE_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

DATA_DIR = PROJECT_DIR / 'data'
TXT_FILE = DATA_DIR / '家教单.txt'
DB_PATH = DATA_DIR / 'orders_v2.db'
GROUP_MAP = DATA_DIR / 'group_map.json'

# ── 解析函数 ──

def parse_orders_from_txt(path):
    """从 txt 按空行拆分单子"""
    text = path.read_text(encoding='utf-8')
    blocks = re.split(r'\n\s*\n', text.strip())
    return [b.strip() for b in blocks if len(b.strip()) > 30]


def extract_fields(content):
    """从单子内容提取结构化字段"""
    fields = {}

    # 单号
    m = re.search(r'([A-Z]+\d+[-‐]?\d*)', content)
    if m:
        fields['order_id'] = m.group(1)
    m = re.search(r'编号[：:]\s*(.{5,25})', content)
    if m and 'order_id' not in fields:
        fields['order_id'] = m.group(1).strip()[:25]

    # 城市
    for city in ['海口', '三亚', '老城', '儋州', '澄迈', '屯昌', '琼海', '文昌', '万宁']:
        if city in content:
            fields['city'] = city
            break

    # 年级
    m = re.search(r'(?:『年级』|年级[：:＝]\s*|【年级[^】]*】[：:]?\s*|几年级[：:：]\s*)(.{3,15})', content)
    if m:
        fields['grade'] = m.group(1).strip()
    else:
        m = re.search(r'([小学初高中大]\w{1,3}(?:年级|升|二|三|四|五|六|一|二|三)|[小初高]一?\s*[男女])', content)
        if m:
            fields['grade'] = m.group(1)

    # 科目
    m = re.search(r'(?:『科目[^』]*』|科目[：:＝]\s*|【科目[^】]*】[：:]?\s*|补习科目[：:：]\s*)(.{3,20})', content)
    if m:
        fields['subject'] = m.group(1).strip()

    # 课酬/价格
    m = re.search(r'(?:〖课酬〗|课酬|老师报酬|薪酬|价格|费用|课时费)[：:＝]?\s*([^\n]{3,20})', content)
    if m:
        fields['fee'] = m.group(1).strip()

    # 地址
    m = re.search(r'(?:『地址』|地址[：:＝]\s*|【地址[^】]*】[：:]?\s*|授课位置[：:]\s*)(.{5,40})', content)
    if m:
        fields['address'] = m.group(1).strip()

    # 要求
    m = re.search(r'(?:『要求』|要求[：:＝]\s*|【老师要求】[：:]?\s*|对老师的要求[：:]\s*)(.{5,80})', content)
    if m:
        fields['requirement'] = m.group(1).strip()

    # 时间
    m = re.search(r'(?:『时间』|时间[：:＝]\s*|上课时间[：:]\s*|每周次数[：:]\s*)(.{5,60})', content)
    if m:
        fields['schedule'] = m.group(1).strip()

    # 判断暑假单
    fields['is_summer'] = bool(re.search(r'暑假|假期', content))

    # 判断帮字单（分成低）
    fields['is_bang'] = ('帮字单' in content) or ('帮字' in content)

    return fields


def determine_source(content, gmap):
    """根据内容判断来源"""
    if any(k in content for k in ['向老师', '狮子岭', 'NL', 'MG', 'M07']):
        return '向老师(狮子岭)', '5成'
    if '楚老师' in content or '郑老师' in content or '海口家庭单' in content:
        return '郑老师', '2-3成'
    if 'hk' in content[:10].lower():
        return '奥利给', '2-3成'
    if any(k in content[:30] for k in ['海口暑假', '老城暑假', '海口上门']):
        return '李老师', '2-3成'
    return '未知', '未知'


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
            content TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_order_id ON orders(order_id);
        CREATE INDEX IF NOT EXISTS idx_city ON orders(city);
        CREATE INDEX IF NOT EXISTS idx_grade ON orders(grade);
        CREATE INDEX IF NOT EXISTS idx_subject ON orders(subject);
        CREATE INDEX IF NOT EXISTS idx_source ON orders(source);
    ''')
    return db


def main():
    print("=" * 50)
    print(" 重建结构化订单数据库")
    print("=" * 50)

    gmap = json.loads(GROUP_MAP.read_text(encoding='utf-8')) if GROUP_MAP.exists() else {}
    blacklist = gmap.get('黑名单', [])

    blocks = parse_orders_from_txt(TXT_FILE)
    print(f"从 txt 解析: {len(blocks)} 条")

    db = init_db()
    now = datetime.now().isoformat()
    inserted = 0
    skipped = 0

    for content in blocks:
        # 黑名单过滤
        if any(b in content for b in blacklist):
            skipped += 1
            continue

        fields = extract_fields(content)
        source, commission = determine_source(content, gmap)

        if fields.get('is_bang'):
            commission = '低（帮字单）'

        db.execute('''INSERT INTO orders(order_id, city, grade, subject, fee, address,
                      requirement, schedule, is_summer, is_bang, source, commission,
                      content, created_at, updated_at)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                   [fields.get('order_id'),
                    fields.get('city'),
                    fields.get('grade'),
                    fields.get('subject'),
                    fields.get('fee'),
                    fields.get('address'),
                    fields.get('requirement'),
                    fields.get('schedule'),
                    int(fields.get('is_summer', False)),
                    int(fields.get('is_bang', False)),
                    source, commission,
                    content, now, now])
        inserted += 1

    db.commit()

    # 统计
    total = db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    by_source = db.execute(
        'SELECT source, COUNT(*), commission FROM orders GROUP BY source ORDER BY COUNT(*) DESC'
    ).fetchall()
    by_city = db.execute(
        'SELECT city, COUNT(*) FROM orders WHERE city IS NOT NULL GROUP BY city ORDER BY COUNT(*) DESC'
    ).fetchall()
    summer = db.execute('SELECT COUNT(*) FROM orders WHERE is_summer=1').fetchone()[0]

    print(f"\n入库: {inserted} 条 | 黑名单过滤: {skipped} 条")
    print(f"\n=== 按来源 ===")
    for s, c, comm in by_source:
        print(f"  {s}: {c} 单 ({comm})")
    print(f"\n=== 按城市 ===")
    for city, c in by_city:
        print(f"  {city}: {c} 单")
    print(f"\n暑假单: {summer} 条")
    print(f"数据库: {DB_PATH}")

    db.close()


if __name__ == '__main__':
    main()
