"""
v4 — 与 v3 相同逻辑，文件读取 + 消息合并
"""
from pathlib import Path
from shared.utils.logger import get_logger
from .config import MSG_MAX_CHUNK

logger = get_logger(__name__)


def read(path):
    """读家教单文件 → 按空行分割 → 合并成 ≤MSG_MAX_CHUNK 字的消息块"""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    raw = [line.strip() for line in lines]

    messages = []
    current = ""
    for line in raw:
        if line:
            current += line + "\n"
        elif current:
            messages.append(current[:-1])
            current = ""
    if current:
        messages.append(current[:-1])

    chunks = []
    buf = ""
    for m in messages:
        if len(buf) + len(m) < MSG_MAX_CHUNK:
            buf = buf + "\n\n" + m if buf else m
        else:
            chunks.append(buf)
            buf = m
    if buf:
        chunks.append(buf)

    logger.info(f"读取 {len(messages)} 条, 合并成 {len(chunks)} 条消息")
    return chunks


def adv(path):
    """读广告文案"""
    ad = ""
    with open(path, "r", encoding="utf-8") as f:
        for line in f.readlines():
            ad += line.strip() + "\n"
    return ad
