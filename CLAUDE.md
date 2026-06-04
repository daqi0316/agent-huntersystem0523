# AI 招聘助手 — 行为规范

## 强制规则

1. **始终用中文回复**，不做英文回复
2. **回复内容要压缩**，简洁明了，不啰嗦

## 已实现功能（参考）

- `get_schedule` — 查询指定月份所有面试（含过去+未来），参数：year/month/status_filter/limit
- `get_upcoming_interviews` — 查询未来 n 天面试
- `get_current_time` — 获取当前时间

## 技术栈

- Backend: FastAPI + SQLAlchemy + PostgreSQL
- Frontend: Next.js 14 + tRPC
- 工具目录: `apps/api/app/tools/`
