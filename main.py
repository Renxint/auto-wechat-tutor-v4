"""
v4 入口 — wxauto4 + 微信 4.1.1.19
混合方案: GetSession(click) + ChatInfo 识别群名 + 键盘发送

用法:
  python main.py              # 文件模式 → 35 群
  python main.py --test       # 测试模式 → 测试1/2/3
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from wxauto4 import WeChat
from wxauto4.param import WxParam
from shared.utils.logger import get_logger

from src.config import FILE_AD, FILE_TUTOR_LIST, _load_map
from src.reader import read, adv
from src.sender_v4 import send

WxParam.LANGUAGE = 'cn'
logger = get_logger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    test_mode = '--test' in sys.argv

    logger.info("=" * 40)
    logger.info(" v4 家教单转发 (wxauto4 混合方案)")
    logger.info(f" 模式: {'测试' if test_mode else '正式'}")
    logger.info("=" * 40)

    try:
        wx = WeChat(ads=False, resize=False)
        logger.info(f"微信已连接: {wx.nickname}")
    except Exception as e:
        logger.error(f"微信初始化失败: {e}")
        return

    groups = _load_map().get("测试", ["测试1"]) if test_mode else None

    tutor_path = DATA_DIR / FILE_TUTOR_LIST
    if not tutor_path.exists():
        logger.error(f"家教单不存在: {tutor_path}")
        return

    messages = read(str(tutor_path))
    if DATA_DIR.joinpath(FILE_AD).exists():
        messages.append(adv(str(DATA_DIR / FILE_AD)))

    logger.info(f"共 {len(messages)} 条 → {len(groups) if groups else 35} 个群")
    send(messages, groups=groups, wx=wx)
    logger.info("完成")


if __name__ == '__main__':
    main()
