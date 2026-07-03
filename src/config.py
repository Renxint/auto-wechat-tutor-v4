"""
v4 配置 — 群角色从 data/group_map.json 加载
"""
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
GROUP_MAP_FILE = PROJECT_DIR / "data" / "group_map.json"

# 消息配置
MSG_MIN_LENGTH = 40
MSG_MAX_CHUNK = 1000
SEND_INTERVAL = 0.02

# 中介黑名单
BLACKLIST_SENDERS = ['一对一李老师中介', '一对一辅导周老师中介']

# 文件
FILE_AD = "招代理.txt"
FILE_TUTOR_LIST = "家教单.txt"

# 测试群
TEST_GROUPS = ["测试1", "测试2", "测试3"]

# 转发每批上限
FORWARD_BATCH_MAX = 9

# ── 加载群映射 ──
_group_map = None


def _load_map():
    global _group_map
    if _group_map is None:
        if GROUP_MAP_FILE.exists():
            _group_map = json.loads(GROUP_MAP_FILE.read_text(encoding='utf-8'))
        else:
            _group_map = {"发单群": [], "出单群": []}
    return _group_map


def get_target_groups():
    """发单群列表（从 group_map.json）"""
    return _load_map().get("发单群", [])


def get_source_groups():
    """出单群列表（从 group_map.json）"""
    return _load_map().get("出单群", [])


def save_group_map():
    """保存群映射（发现模式追加后用）"""
    GROUP_MAP_FILE.write_text(json.dumps(_load_map(), ensure_ascii=False, indent=2), encoding='utf-8')
