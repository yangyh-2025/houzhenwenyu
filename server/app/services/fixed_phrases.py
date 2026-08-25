"""固定话术注册表 + 系统提示词导入。"""
from __future__ import annotations

PHRASES = {
    # 2026-08-24 v3：开场=平台介绍+引导，以问句收尾；患者点【明白了】后进入正式问答
    "OPENING": "您好，我是候诊闻语，是帮您在见到医生之前先介绍身体情况的语音助手。"
               "接下来我会像聊天一样问您几个小问题，您听完问题直接对着手机说话就行，"
               "不用打字、不用按键；没听清没关系，我会再说一遍。"
               "我们聊的内容会整理好给医生参考。您听明白了吗？",
    "CLOSING": "问诊完成，请您等候叫号就诊。",
    "REMINDER_SILENT": "如果您准备好了，就请对着手机说话回答吧。",
    "ASK_CONTINUE": "您还在吗？想继续还是结束问诊呢？",
    "FALLBACK_QUESTION": "明白了，请您再跟我讲讲其他方面的情况吧？",
}

PHRASE_KEYS = frozenset(PHRASES.keys())


def get_text(key: str) -> str:
    return PHRASES[key]


from app.services._system_prompt import SYSTEM_PROMPT
