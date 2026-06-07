"""A1: Admin 运维端点 — 限流状态查询/重置 (admin JWT 鉴权)。

只服务两类场景:
- 健康检查/压测污染: 调 reset 清空限流状态
- 故障排查: 调 state 看活跃 keys / 限流配置

设计原则:
- 任何 admin 写操作记 audit log (后续 PR 接入 audit_logs 表)
- 不暴露密码/secret，只返限流元数据
- 端点本身不计入限流 (auth 强制 admin role)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.dependencies import require_admin_user_id
from app.core.rate_limit import admin_reset_all, get_state_snapshot
from app.core.response import success

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/rate-limit/state")
async def rate_limit_state(
    admin_user_id: str = Depends(require_admin_user_id),
):
    """查看限流状态: 活跃 buckets/counters 数 + 当前 store 类型 + 限制配置。

    用法:
        curl -H "Authorization: Bearer $ADMIN_TOKEN" \\
             http://localhost:8000/api/v1/admin/rate-limit/state | jq
    """
    snapshot = await get_state_snapshot()
    logger.info("admin inspect rate_limit: user=%s state=%s", admin_user_id, snapshot)
    return success(snapshot)


@router.post("/rate-limit/reset")
async def rate_limit_reset(
    admin_user_id: str = Depends(require_admin_user_id),
):
    """清空限流状态: 删所有 buckets 和 quota counters。

    适用场景:
    - health-check/load test 留下限流污染, 真实用户访问时撞 429
    - 限流误触发需要紧急清空

    注意: 返 snapshot_before_reset 便于排查。

    用法:
        curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
             http://localhost:8000/api/v1/admin/rate-limit/reset | jq
    """
    result = await admin_reset_all()
    logger.info("admin reset rate_limit: user=%s result=%s", admin_user_id, {
        k: v for k, v in result.items() if k != "snapshot_before_reset"
    })
    return success(result)
