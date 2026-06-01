"""PII Filter — 数据最小化工具。

功能:
- 从文本/JSON 中移除或脱敏个人身份信息
- 支持: 姓名、手机号、邮箱、身份证号、银行卡号、地址
- 提供 strip_pii() 一键清理 + mask_pii() 可逆脱敏
"""

from __future__ import annotations

import re
from typing import Any

# ── PII 正则模式 ──

PII_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    # id_card must come before phone — phone pattern (1[3-9]\d{9}) can match
    # substrings of full ID card numbers (e.g. 110101199001011234 → 19900101123).
    ("id_card", "身份证号", re.compile(r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]")),
    ("bank_card", "银行卡号", re.compile(r"\b(?:62|60|58|56|55|54|53|52|51|50|49|48|47|46|45|44|43|42|41|40)\d{14,17}\b")),
    ("phone", "手机号", re.compile(r"1[3-9]\d{9}")),
    ("email", "邮箱", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("chinese_name", "中文姓名", re.compile(r"(?<![a-zA-Z])[\u4e00-\u9fa5]{2,3}(?=先生|女士|同志|同学|老师|经理|总监|总裁|工程师|用户|候选人|candidate)")),
]

# 需要额外上下文才能安全匹配的名词，仅 strip 不 mask
PII_CONTEXTUAL = [
    ("address", "地址", re.compile(r"(?:省|市|区|县|镇|乡|路|街|巷|号|栋|单元|室)")),
]


def strip_pii(text: str, replacement: str = "[已过滤]") -> str:
    """彻底移除文本中的 PII（不可逆）。"""
    for name, label, pattern in PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def mask_pii(text: str) -> str:
    """脱敏 PII（保留格式，隐藏敏感部分）。

    - 手机号: 138****1234
    - 邮箱: user@***.com
    - 身份证: 110101********1234
    - 中文姓名: 张**
    """
    for name, label, pattern in PII_PATTERNS:
        if name == "phone":
            text = pattern.sub(lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:], text)
        elif name == "email":
            def _mask_email(m: re.Match) -> str:
                parts = m.group(0).split("@")
                if len(parts) == 2:
                    local, domain = parts
                    domain_parts = domain.split(".")
                    masked_local = local[0] + "***" if len(local) > 1 else "***"
                    return f"{masked_local}@{domain_parts[0]}.{'.'.join(domain_parts[1:])}"
                return "[已过滤]"
            text = pattern.sub(_mask_email, text)
        elif name == "id_card":
            text = pattern.sub(lambda m: m.group(0)[:6] + "********" + m.group(0)[-4:], text)
        elif name == "chinese_name":
            text = pattern.sub(lambda m: m.group(0)[0] + "**", text)
        else:
            text = pattern.sub("[已过滤]", text)
    return text


def strip_pii_from_dict(data: dict, fields: list[str] | None = None) -> dict:
    """递归清理 dict 中所有字符串值的 PII。

    可指定 fields 限定范围，默认处理全部字符串。
    """
    result: dict = {}
    for key, value in data.items():
        if fields and key not in fields:
            result[key] = value
            continue
        if isinstance(value, str):
            result[key] = strip_pii(value)
        elif isinstance(value, dict):
            result[key] = strip_pii_from_dict(value, fields)
        elif isinstance(value, list):
            result[key] = [
                strip_pii_from_dict(item, fields) if isinstance(item, dict)
                else strip_pii(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def summarize_prompt_for_audit(prompt: str, max_length: int = 200) -> str:
    """对 prompt 做审计摘要：清理 PII + 截断。"""
    cleaned = strip_pii(prompt)
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "..."
    return cleaned


def summarize_output_for_audit(output: dict | str, max_length: int = 150) -> str:
    """对 agent 输出做审计摘要。"""
    if isinstance(output, dict):
        text = str(output)
    else:
        text = output
    cleaned = strip_pii(text)
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "..."
    return cleaned
