"""固定话术注册表 + 系统提示词导入。"""
from __future__ import annotations

PHRASES = {
    # 2026-08-24 v4：精简修正版开场（问句结尾）；FIRST_QUESTION 固定首问（瞬时返回）
    "OPENING": "您好，我是候诊闻语，是帮您在见医生前把身体情况提前整理好的语音助手。我问，您答，直接对着手机说话就行，不用打字；没听清没关系，我会再说一遍。您听明白了吗？",
    "FIRST_QUESTION": "请问您主要是哪里不舒服呀？是怎么开始的，到现在大概多久了？",
    "CLOSING": "问诊完成，请您等候叫号就诊。",
    "REMINDER_SILENT": "如果您准备好了，就请对着手机说话回答吧。",
    "ASK_CONTINUE": "您还在吗？想继续还是结束问诊呢？",
    "FALLBACK_QUESTION": "明白了，请您再跟我讲讲其他方面的情况吧？",
}

PHRASE_KEYS = frozenset(PHRASES.keys())


def get_text(key: str) -> str:
    return PHRASES[key]


from app.services._system_prompt import SYSTEM_PROMPT
