"""医疗建议安全过滤器（PRD F3-R8 合规红线服务端兜底）。

五族黑名单：用药建议/诊断结论/处方剂量/治疗建议/检查建议。
命中即 WARN（不含正文）；问题轮整条替换，摘要轮删行。
"""
from __future__ import annotations

import logging
import re
from typing import List, Pattern

logger = logging.getLogger(__name__)

# 每条正则 = 一族建议话术的匹配模式
# 五族基础 + 2026-08-24 第三轮加固（诊断推断/方剂药名/剂型/用法/剂量）
PATTERNS: List[Pattern] = [
    re.compile(p) for p in [
        # --- 用药建议家族 ---
        r"(建议|推荐)[^。？！.?!]{0,12}(服用|使用|吃|打|注射)",
        r"(可以|需要)(吃|服|用)下?[这那]?(些|个)?药",
        r"坚持吃药|忘记吃药|按医嘱服药",
        r"(吃|服|喝|用|含)[\d一二两三四五六七八九十]+\s*(粒|片|丸|颗|克|毫升|袋|支|包)",
        r"(建议|不妨|试试|最好|要不)[^。？！.?!]{0,6}(现在|先|再|临时)?[^。？！.?！]{0,4}(吃|喝|服|用)[^。？！.?!]{0,12}(药|丸|片|汤|胶囊|颗粒)",
        # --- 诊断结论家族 ---
        r"(确诊|诊断)为|考虑诊断|诊断结果|诊断[：: ]|确诊出",
        r"考虑.{0,6}(诊断|是).{0,8}(证|病|炎|综合征)",
        r"(你|您)(这就是|就是|这是|如今是|是|得的|患的|得的是)(.{0,8})(病|证|综合征|炎|癌|结核)",
        r"辨证(为|是)|体质(属于|是|偏)|(您|你)(可能是|大概|像是|应该是)[^。？！.?!]{0,8}(虚弱|脾虚|气虚|血虚|阳虚|阴虚|湿热|寒湿|痰湿|亏虚|不足)",
        r"(检查|化验|片子|报告|结果)(显示|提示|结果)(为|是|:)?[^。？！.?!]{0,10}(病|炎|综合征|异常|渗出|肿大)",
        # --- 处方方剂家族 ---
        r"处方|方剂|方子|开方|剂型",
        r"剂量|用量|一日三次|(饭前|饭后)(服|喝)|空腹服|温水送服|开水冲服",
        r"水煎服|按疗程|连用|连服|疗程",
        r"[一-龥]{2,6}(汤|散|丸|丹|颗粒|膏方|口服液|糖浆|胶囊)",  # 剂型名
        r"(脾胃|肝|肾|心|肺|气血)(虚弱|亏虚|不和|不调|不足|有寒|有热)",
        r"六味地黄|归脾|桂枝汤|逍遥丸|藿香正气|保和丸|补中益气|四君子|八珍|二陈|小柴胡|血府逐瘀|羚羊角",
        # --- 治疗建议家族 ---
        r"治疗(原则|建议|方案|手段)|治法|方用|针灸(治疗|调理)|(艾灸|推拿|拔罐|刮痧|理疗)(治疗|调理|建议)",
        r"(泡脚|足浴|热敷|药浴|食疗|偏方)(治|调理|可以|帮助|推荐)",
        # --- 检查建议家族 ---
        r"(建议|推荐)[^。？！.?!]{0,10}(做|查|检查|化验|拍)",
        r"先去做个?(B超|CT|核磁|胃镜|肠镜|血常规|化验|彩超)",
        r"(去|先|赶紧|最好|建议)[^。？！.?!]{0,6}(拍|做|查|照)(个|张|次)?(片子|X光|B超|CT|检查|化验|造影|核磁)",
        r"(住院|输液|打点滴|动手术|手术)(治疗|建议|吧|可以)",
        r"(你就|你(应该|需要|最好))[^。？！.?!]{0,10}(挂号|就诊|复诊|转诊|看医生|去看)",
        r"挂号[^。？！.?!]{0,8}(科|门诊|医生|专家|看看)",
    ]
]


def hit(text: str):
    """返回 (命中正则, 族索引)；未命中 (None, None)。"""
    for i, pat in enumerate(PATTERNS):
        m = pat.search(text or "")
        if m:
            return pat, i
    return None, None


_CONSECUTIVE = {"family": None, "count": 0}


def filter_question_reply(text: str, fallback: str) -> str:
    """问题轮过滤：命中建议类内容则整条替换为中性追问。

    2026-08-24 死锁自愈：同一族连续命中 >=3 次视为正常问句误拦（如
    "现在在吃哪些药"），放行原文并 CRITICAL 告警——防过滤本身造成
    固定话术循环，人工记录标点。
    """
    pat, fam = hit(text)
    if pat is not None:
        if _CONSECUTIVE["family"] == fam:
            _CONSECUTIVE["count"] += 1
        else:
            _CONSECUTIVE["family"] = fam
            _CONSECUTIVE["count"] = 1
        if _CONSECUTIVE["count"] >= 3:
            logger.critical("safety 连续命中同族>=3 family=%d 放行原文", fam)
            _CONSECUTIVE["count"] = 0
            return text
        logger.warning("safety 拦截问题输出 family=%d", fam)
        return fallback
    _CONSECUTIVE["family"] = None
    _CONSECUTIVE["count"] = 0
    return text


def filter_summary(text: str) -> str:
    """摘要过滤：删除命中行；【辨证参考】 块为医生专用辨证参考，原样保留。"""
    src = text or ""
    tcm = ""
    i = src.find("【辨证参考】")
    if i >= 0:
        j = src.find("【", i + 1)
        tcm = src[i:j if j > 0 else len(src)]
        src = src[:i] + src[j:] if j > 0 else src[:i]
    out_lines = []
    removed = 0
    for line in src.splitlines():
        pat, _fam = hit(line)
        if pat is not None:
            removed += 1
            continue
        out_lines.append(line)
    if removed:
        logger.warning("safety 删除摘要行 count=%d", removed)
    out = chr(10).join(out_lines)
    if tcm:
        out = (out + chr(10) + tcm).strip()
    return out
