# Phase Z: Infrastructure + Coverage Push (2026-06-02)

> 优先级：基础设施完整性 > 覆盖率 > 功能增强
> 目标：让系统达到 production-ready 状态

---

## Z.1 — Rate Limiting（已实现框架，缺启用）

**现状**：`apps/api/app/core/rate_limit.py` 已存在，但未被实际启用。

**任务**：
1. 读取 `rate_limit.py` 了解当前实现
2. 在 `agent.py` 的 `/chat` 端点实际启用 rate limiting
3. 添加 Redis dependency check（无 Redis 时 graceful degradation）
4. 测试 rate limit 确实生效

**文件**：
- `apps/api/app/core/rate_limit.py` — 现有框架
- `apps/api/app/api/agent.py` — 启用端点
- `apps/api/app/main.py` — middleware 级别（可选）

**Est**: ~1h

---

## Z.2 — LLM Retry with Backoff

**现状**：LLM 调用失败时直接抛异常，无重试。

**任务**：
1. 在 `agent_service.py` 的 `_call_llm()` 或 equivalent 处加 retry decorator
2. 使用 `tenacity` 或手动实现指数退避（3 次重试，base 1s，max 10s）
3. 区分 retriable errors（timeout、429、503）和 non-retriable（401、403、422）
4. 测试：mock LLM 返回 503 → 验证重试 3 次

**文件**：
- `apps/api/app/services/agent_service.py`
- 或 `apps/api/app/llm/` clients

**Est**: ~1h

---

## Z.3 — `operations.py` 覆盖率 30% → 60%+

**现状**：大量端点未测试。

**任务**：
1. 读取 `operations.py` 了解端点
2. 写 `tests/test_operations.py` 覆盖：
   - `GET /operations/stats` — 验证响应结构
   - `POST /operations/log` — 验证写入
   - `GET /operations/recent` — 验证分页
   - error path: unauthenticated → 401
3. Mock Redis/DB dependencies

**文件**：
- `apps/api/app/api/operations.py`
- `apps/api/tests/test_operations.py`（新建）

**Est**: ~1.5h

---

## Z.4 — Python Deprecation Warnings（24 个 → 0）

**现状**：测试输出 551 warnings。

**常见模式**：
- `datetime.utcnow()` → `datetime.now(datetime.UTC)`（Python 3.12+）
- `asyncio.iscoroutinefunction` → `inspect.iscoroutinefunction`
- `RuntimeWarning: coroutine was never awaited` — async mock 未正确配置

**任务**：
1. 运行 `pytest --warning-filter=error` 定位最严重的
2. 修复 `datetime.utcnow()` 在 `human_loop.py` 和其他文件
3. 修复 async mock warnings（await 正确的 mock call）

**文件**：
- `apps/api/app/agents/human_loop.py`
- `apps/api/app/commands/handlers/`（多处）
- `apps/api/app/commands/executor.py`

**Est**: ~30 min

---

## Z.5 — Final Verification

```bash
# Backend
cd apps/api && source .venv/bin/activate
python -m pytest tests/ --cov=app --cov-fail-under=80 -q

# Frontend
cd apps/web && npx next build

# E2E (需要服务启动)
cd apps/web && npx playwright test
```

**目标**：
- [ ] 覆盖率 ≥ 80%
- [ ] Next.js build ✅
- [ ] 0 pre-existing failures (4 known failures can be xfail-annotated)
- [ ] Rate limiting enabled
- [ ] LLM retry working
- [ ] Python deprecation warnings < 50 (从 551 减少)

---

## Exit Criteria

- [ ] `pytest --cov-fail-under=80` 绿色通过
- [ ] `next build` 绿色通过
- [ ] Rate limiting 在 `/chat` 端点生效
- [ ] LLM retry 机制可验证
- [ ] Python warnings 大幅减少
- [ ] 所有新工作 commit 到 git
