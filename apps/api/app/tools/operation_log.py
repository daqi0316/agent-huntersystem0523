"""Operation logging tool — 统一记录 Agent 和人工操作到 operation_logs 表。"""

from __future__ import annotations

import logging
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.operation_service import OperationService
from app.models.operation_log import OperationStatus, ErrorCategory

logger = logging.getLogger(__name__)


async def _handle_log_operation(
    action: str = "",
    agent_name: str = "agent",
    status: str = "completed",
    user_id: str = "",
    input_summary: str = "",
    output_summary: str = "",
    error_message: str = "",
    error_category: str = "",
    metadata: dict | None = None,
) -> dict[str, Any]:
    try:
        op_status = OperationStatus(status)
    except ValueError:
        op_status = OperationStatus.COMPLETED

    try:
        err_cat = ErrorCategory(error_category) if error_category else None
    except ValueError:
        err_cat = None

    async with AsyncSessionLocal() as db:
        svc = OperationService(db)
        op = await svc.create(
            user_id=user_id or None,
            agent_name=agent_name,
            action=action,
            input_summary=input_summary or None,
            error_category=err_cat.value if err_cat else None,
            metadata_json=metadata,
        )
        if op_status != OperationStatus.PENDING:
            await svc.transition(
                op.id,
                op_status,
                output_summary=output_summary or None,
                error_message=error_message or None,
                error_category=err_cat.value if err_cat else None,
            )
        return {
            "status": "success",
            "data": {
                "operation_id": op.id,
                "action": op.action,
                "status": op.status.value,
                "created_at": op.created_at.isoformat() if op.created_at else "",
            },
        }


tools = [
    {
        "type": "function",
        "function": {
            "name": "log_operation",
            "description": "记录操作到统一的审计日志。所有 Agent 工具调用和重要人工操作都应调用此工具记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "操作名称，如 create_candidate, cancel_interview, resume_parse"},
                    "agent_name": {"type": "string", "description": "来源：agent / human（默认 agent）"},
                    "status": {"type": "string", "enum": ["pending", "running", "completed", "failed", "cancelled"], "description": "操作状态"},
                    "user_id": {"type": "string", "description": "用户 ID（人工操作时填写）"},
                    "input_summary": {"type": "string", "description": "输入摘要，如 '创建候选人: 张三, email: z@example.com'"},
                    "output_summary": {"type": "string", "description": "输出摘要，如 '候选人 ID: xxx'"},
                    "error_message": {"type": "string", "description": "错误信息（失败时填写）"},
                    "error_category": {"type": "string", "enum": ["system", "user", "business"], "description": "错误分类: system=系统故障, user=用户输入错误, business=业务拒绝"},
                    "metadata": {"type": "object", "description": "额外元数据（JSON 对象）"},
                },
                "required": ["action", "status"],
            },
        },
    },
]

handlers = {
    "log_operation": _handle_log_operation,
}
