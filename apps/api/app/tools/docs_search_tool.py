"""Docs search tool — 预置招聘相关文档搜索。"""

from __future__ import annotations


DOCS = [
    {"title": "招聘流程最佳实践", "category": "流程", "content": "标准招聘流程包括：需求确认→发布职位→简历筛选→面试→Offer→入职。每个环节需要明确责任人和时间节点。"},
    {"title": "面试评估标准指南", "category": "评估", "content": "建议从技术能力、沟通能力、文化契合度、成长潜力四个维度评估候选人，每项 1-5 分。"},
    {"title": "候选人体验优化手册", "category": "体验", "content": "从投递到入职，保持 48 小时内响应，提供明确 feedback，减少候选人等待时间。"},
    {"title": "AI 初筛配置说明", "category": "技术", "content": "AI 初筛支持自定义筛选维度、权重、阈值。建议初始设置：技能匹配 40%，经验 30%，教育 20%，其他 10%。"},
    {"title": "JD 编写方法论", "category": "内容", "content": "好的 JD 应包含：职位概述、职责描述、任职要求、加分项、团队介绍。避免使用歧视性语言。"},
    {"title": "入职流程清单", "category": "流程", "content": "新员工入职流程：准备工位和设备→发送欢迎邮件→介绍团队成员→讲解公司制度→签署合同→参加入职培训。"},
    {"title": "简历筛选标准", "category": "流程", "content": "简历筛选要点：工作经历时间线、职位匹配度、行业背景、关键技能词、学历要求。"},
    {"title": "薪酬谈判技巧", "category": "体验", "content": "薪酬谈判原则：了解市场行情、突出候选人价值、设定谈判区间、保留让步空间、及时决策。"},
]


async def _handle_search_documents(query: str, limit: int = 3) -> str:
    matched = [d for d in DOCS if query.lower() in d["title"].lower() or query.lower() in d["category"].lower()]
    if not matched:
        matched = DOCS[:limit]
    if limit > 0:
        matched = matched[:limit]
    text = "\n---\n".join(
        f"【{d['title']}】({d['category']})\n{d['content']}" for d in matched
    )
    return text or "未找到匹配结果"


tools = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "搜索预置的招聘相关文档资料库。用于回答招聘流程、面试技巧、制度等问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量（默认 3）",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
        },
    },
]

handlers = {"search_documents": _handle_search_documents}
