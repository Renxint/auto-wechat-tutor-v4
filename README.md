# auto_wechat_tutor v4 — 微信 4.x + wxauto4

> 当前状态: **wxauto4 41.1.2 不支持微信 4.1.10.51**（mmui::MainWindow 类名缺失）
> 降级微信或等 wxauto4 更新后即可启用

## v4 vs v3 核心差异

| 特性 | v3 (wxauto 3.9) | v4 (wxauto4) |
|------|-----------------|--------------|
| ChatWith | UIA 匹配，稳定 | `force=True` 强制切换 |
| 群发 | 逐个 ChatWith + SendMsg | `Message.forward(targets)` 一键多选 |
| 消息读取 | GetAllMessage() | GetAllMessage() + OCR |
| 语音 | ❌ | VoiceMessage.to_text() |
| 图片 | ❌ | ImageMessage.download() |
| 会话列表 | GetSessionList() | GetSession() |

## 使用

```bash
pip install wxauto4
python main.py
```
