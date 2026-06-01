"""Tests for PII Filter — data minimization utilities."""

from app.agents.pii_filter import (
    strip_pii,
    mask_pii,
    strip_pii_from_dict,
    summarize_prompt_for_audit,
    summarize_output_for_audit,
)


# ── strip_pii ──


def test_strip_phone():
    assert strip_pii("联系我 13800138000 谢谢") == "联系我 [已过滤] 谢谢"


def test_strip_email():
    assert "已过滤" in strip_pii("email: test@example.com")


def test_strip_id_card():
    assert strip_pii("身份证 110101199001011234") == "身份证 [已过滤]"


def test_strip_chinese_name():
    result = strip_pii("张三先生和李四女士都合适")
    assert "先生" in result
    assert "女士" in result
    assert "张三" not in result or "[已过滤]" in result


def test_strip_multiple_pii():
    text = "张三先生电话13800138000邮箱test@foo.com"
    cleaned = strip_pii(text)
    assert "[已过滤]" in cleaned
    # All PII should be gone
    assert "13800138000" not in cleaned


def test_strip_no_pii():
    text = "这是一段普通文本，没有敏感信息"
    assert strip_pii(text) == text


def test_strip_empty_string():
    assert strip_pii("") == ""


# ── mask_pii ──


def test_mask_phone():
    assert mask_pii("13800138000") == "138****8000"


def test_mask_email():
    result = mask_pii("user@example.com")
    assert "@" in result
    assert "example" in result
    assert "user" not in result or "***" in result


def test_mask_id_card():
    masked = mask_pii("110101199001011234")
    assert masked.startswith("110101")
    assert masked.endswith("1234")
    assert "********" in masked


def test_mask_chinese_name():
    assert "张**" in mask_pii("张三先生是候选人")
    # also keeps the context word


def test_mask_no_pii():
    text = "普通文本"
    assert mask_pii(text) == text


# ── strip_pii_from_dict ──


def test_strip_pii_from_dict_all():
    data = {
        "name": "张三先生",
        "phone": "13800138000",
        "age": 30,
    }
    cleaned = strip_pii_from_dict(data)
    assert "[已过滤]" in cleaned["name"] or cleaned["name"] != "张三先生"
    assert "13800138000" not in cleaned["phone"]
    assert cleaned["age"] == 30


def test_strip_pii_from_dict_filtered_fields():
    data = {
        "name": "张三先生",
        "phone": "13800138000",
        "note": "正常信息",
    }
    cleaned = strip_pii_from_dict(data, fields=["phone"])
    assert cleaned["name"] == "张三先生"  # not cleaned
    assert cleaned["phone"] != "13800138000"  # cleaned
    assert cleaned["note"] == "正常信息"


def test_strip_pii_from_dict_nested():
    data = {
        "candidate": {"name": "李四女士", "contact": "lisi@test.com"},
    }
    cleaned = strip_pii_from_dict(data)
    nested = cleaned["candidate"]
    assert "[已过滤]" in nested["name"] or nested["name"] != "李四女士"
    assert "[已过滤]" in nested["contact"] or nested["contact"] != "lisi@test.com"


def test_strip_pii_from_dict_list():
    data = {
        "items": [
            {"name": "张三先生"},
            {"name": "李四女士"},
        ]
    }
    cleaned = strip_pii_from_dict(data)
    for item in cleaned["items"]:
        assert "[已过滤]" in item["name"] or item["name"] not in ("张三先生", "李四女士")


# ── summarize_*_for_audit ──


def test_summarize_prompt_cleans_pii():
    prompt = "候选人是 13800138000，请联系他"
    summary = summarize_prompt_for_audit(prompt, max_length=200)
    assert "13800138000" not in summary
    assert "[已过滤]" in summary


def test_summarize_prompt_truncates():
    prompt = "A" * 300
    summary = summarize_prompt_for_audit(prompt, max_length=50)
    assert len(summary) == 53  # 50 + "..."
    assert summary.endswith("...")


def test_summarize_prompt_short():
    prompt = "简短内容"
    assert summarize_prompt_for_audit(prompt) == prompt


def test_summarize_output_from_dict():
    output = {"result": "张三先生 13800138000"}
    summary = summarize_output_for_audit(output)
    assert "13800138000" not in summary


def test_summarize_output_from_str():
    output = "李四女士 110101199001011234"
    summary = summarize_output_for_audit(output)
    assert "110101199001011234" not in summary


def test_summarize_output_truncates():
    output = "B" * 200
    summary = summarize_output_for_audit(output, max_length=20)
    assert len(summary) == 23  # 20 + "..."
    assert summary.endswith("...")
