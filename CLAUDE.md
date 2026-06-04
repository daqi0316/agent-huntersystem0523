# AI 招聘助手 — 行为规范

## 强制规则

1. **始终用中文回复**，不做英文回复
2. **回复内容要压缩**，简洁明了，不啰嗦
3. **每次代码改动后必须跑系统健康检查**——见 `docs/system-health-check.md`
   - 不跑 = 改完不算
   - 仅 tsc + mock e2e 通过 ≠ 系统可用（2026-06-04 教训：后端 8000 没起导致 "Failed to fetch"）

## 已实现功能（参考）

- `get_schedule` — 查询指定月份所有面试（含过去+未来），参数：year/month/status_filter/limit
- `get_upcoming_interviews` — 查询未来 n 天面试
- `get_current_time` — 获取当前时间

## 技术栈

- Backend: FastAPI + SQLAlchemy + PostgreSQL
- Frontend: Next.js 14 + tRPC
- 工具目录: `apps/api/app/tools/`

## 全栈验证 SOP（必读）

`docs/system-health-check.md` 列出 6 步检查：
1. 基础设施（postgres/redis/qdrant/minio）
2. 后端进程（uvicorn 8000）
3. 后端可登录（POST /auth/login）
4. 后端可验证（GET /auth/me 带 token）
5. 前端可达（curl /login /agent）
6. 端到端真实登录（Playwright 真实后端）

**e2e 测试不能替代**——`verify-contextbar.ts` 用 `page.addInitScript` mock token，验不了真实后端可达性。
