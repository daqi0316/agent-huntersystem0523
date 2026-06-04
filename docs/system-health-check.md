# 系统健康检查 SOP

> 创建：2026-06-04
> 触发原因：之前的改动只验 tsc + e2e mock 登录，导致用户浏览器登录失败（"Failed to fetch"）的问题被忽略
> 适用范围：**任何代码改动后**，无论大小

## 目标

确保每次改动后，用户能真正从浏览器登录 → 进入 /agent → 看到 ContextBar。
不依赖 e2e 测试（e2e 是 mock 登录的，验不了真实后端可达性）。

## 失败案例（为什么要这条 SOP）

2026-06-04 教训：
- 改完代码只跑 `tsc --noEmit` + `npx tsx scripts/verify-contextbar.ts`（mock 后端 e2e）
- 16/16 测试通过，自信地说"系统 OK"
- 用户开浏览器点登录 → "Failed to fetch"
- 真实原因：后端 8000 端口没起，前端 fetch 全部 reject
- **e2e 测试完全没发现这个问题**，因为它用 `page.addInitScript` 注入了 mock token，绕过了真实后端检查

## 健康检查流程（6 步）

### Step 1: 基础设施层
```bash
lsof -i:5432 -i:6379 -i:6333 -i:9000 2>&1 | grep LISTEN
```
**期望**：四个端口都有 `LISTEN` 状态进程
**缺哪个**：
```bash
cd /Users/qixia/agent-huntersystem0523
docker compose -f docker-compose.dev.yml up -d postgres redis qdrant minio
```

### Step 2: 后端进程层
```bash
lsof -i:8000 2>&1 | grep LISTEN
```
**期望**：uvicorn 在 8000 监听
**没有**：
```bash
cd /Users/qixia/agent-huntersystem0523/apps/api
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
（或 `make api:dev`）

### Step 3: 后端可登录
```bash
curl -sS -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e-tester@test.com","password":"E2ePass123!"}' | jq
```
**期望**：返回 `{"access_token": "...", ...}`

**如果失败**：
- 401 → 用户不存在，先注册：`POST /auth/register`
- 422 → schema 错，检查 curl body
- 500 → 后端崩溃，看 uvicorn 日志

### Step 4: 后端可验证 token
```bash
TOKEN=$(curl -sS -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e-tester@test.com","password":"E2ePass123!"}' \
  | jq -r .access_token)

curl -sS -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/auth/me | jq
```
**期望**：返回 `{"id": "...", "email": "...", "name": "...", "role": "hr"}`

### Step 5: 前端可达
```bash
curl -sS -o /dev/null -w "GET /login  → HTTP %{http_code}\n" http://localhost:3007/login
curl -sS -o /dev/null -w "GET /agent  → HTTP %{http_code}\n" http://localhost:3007/agent
curl -sS -o /dev/null -w "GET /        → HTTP %{http_code}\n" http://localhost:3007/
```
**期望**：login=200，agent=200，/=307（重定向到 /login）

**没有 dev server**：
```bash
cd /Users/qixia/agent-huntersystem0523/apps/web
npx next dev --port 3007
```

### Step 6: 端到端真实登录
启动 Playwright 脚本，**真实后端、真实表单、真实跳转**：
```bash
cd /Users/qixia/agent-huntersystem0523/apps/web
npx tsx scripts/verify-login-e2e.ts
```
（脚本待写 —— 见下方"待办"）

**期望输出**：
- ✅ /login 页面渲染表单
- ✅ 填 e2e-tester@test.com / E2ePass123! 提交
- ✅ 跳转到 /dashboard
- ✅ /agent 页面 ContextBar 缩略按钮可见
- ✅ ⌘K 打开抽屉，6 个 section 全部渲染
- ✅ 0 console error

## 一键检查脚本

未来可写 `scripts/health-check.sh` 把以上 6 步串起来：
```bash
#!/bin/bash
set -e
echo "=== 1. 基础设施 ==="
lsof -i:5432 -i:6379 -i:6333 -i:9000 >/dev/null 2>&1 || {
  echo "❌ 基础设施未全起"; exit 1; }
echo "✅ 基础设施 OK"

echo "=== 2. 后端进程 ==="
lsof -i:8000 >/dev/null 2>&1 || {
  echo "❌ uvicorn 未运行"; exit 1; }
echo "✅ uvicorn OK"

echo "=== 3. 后端登录 ==="
TOKEN=$(curl -sS -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e-tester@test.com","password":"E2ePass123!"}' \
  | jq -r .access_token)
[ -n "$TOKEN" ] || { echo "❌ 登录失败"; exit 1; }
echo "✅ 登录 OK, token=${TOKEN:0:20}..."

echo "=== 4. /auth/me ==="
curl -sS -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/auth/me | jq -e .email >/dev/null || {
  echo "❌ /auth/me 失败"; exit 1; }
echo "✅ /auth/me OK"

echo "=== 5. 前端 ==="
curl -sS -o /dev/null -w "%{http_code}" http://localhost:3007/login | grep -q 200 || {
  echo "❌ 前端 /login 不可达"; exit 1; }
echo "✅ 前端 OK"

echo "=== 全部通过 ==="
```

## 强制执行点

**任何**改完代码后的回应必须包含"健康检查结果"，例如：
> ✅ tsc 0 错误
> ✅ 14/14 单元测试
> ✅ 16/16 e2e（mock）
> ✅ **系统健康检查 6/6**（基础设施 + 后端 + 前端 + 真实登录全过）
> ✅ 浏览器手测 /agent → ContextBar 缩略按钮可见

**缺少"真实后端登录验证"的报告 = 不算改完**。

## 待办

- [ ] 写 `scripts/health-check.sh` 串起 6 步
- [ ] 写 `scripts/verify-login-e2e.ts` 真实端到端登录（区别于 `verify-contextbar.ts` 的 mock）
- [ ] 在 `CLAUDE.md` 加引用此文档
- [ ] 清理 `auth-context.tsx` 的"降级登录"代码（这是临时糊的，不是真修复）

## 关联

- 教训来源：2026-06-04 用户反馈"每次改完系统就登入不进去，有没有做好全盘考虑"
- 与 e2e mock 的区别：`verify-contextbar.ts` 用 `page.addInitScript` 注入 mock token，**不验证真实后端可达性**。本 SOP 强制走真实路径。
