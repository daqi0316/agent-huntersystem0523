# MCP v4 v0.5a Ship Report — 抽 _do_extract_and_link 公共函数 + 恢复 v0.4d LLM 成功测

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/v0.5-replan.md` §4 v0.5a 任务拆解
> **Git tag**: `mcp-v4-v0.5a-pre` (commit c787d31) → `mcp-v4-v0.5a-shipped` (commit 88066a3)
> **commit**: 1 个 (`88066a3`)
> **接受门槛**: v0.4d 4 测试全 pass + parse_resume 行为不变 + health-check 14/14

## 1. 概览

| 维度 | 状态 |
|---|---|
| `_do_extract_and_link(raw_resume_id, content, auto_create=True)` 抽出 | ✅ |
| 状态机更新集中（processing → parsed/failed）| ✅ |
| `_handle_parse_resume` 减薄 | ✅ 135 行 → 53 行（减 60%）|
| 恢复 v0.4d LLM 成功测（完整断言）| ✅ |
| parse_resume 行为不变 | ✅（mcp-resume e2e 14/14 + 14 server list_tools 返回 3 工具不变）|
| v0.4d 4 测试 | ✅ 4/4 |
| mcp 14 server e2e | ✅ 14/14 |
| 全栈 health-check | ✅ 14/14（9 步全过）|

## 2. 改动 diff

| 文件 | 改动 |
|---|---|
| `apps/api/app/tools/resume_parser.py` | +63 / -51（净 +12）|
| `apps/api/tests/mcp/integration/test_resume_parser_v0_4d.py` | +55 / 0 |

总 +118 / -51。

## 3. 关键决策

### 3.1 公共函数签名

```python
async def _do_extract_and_link(
    raw_resume_id: str,
    content: str,
    auto_create: bool = True,
) -> dict[str, Any]:
```

**为什么 `auto_create` 默认 True**：
- v0.5b retry_raw_resume 强制 auto_create=True（retry 语义就是"重新创建/链候选人"）
- v0.4d 之前 parse_resume 默认 auto_create=True
- 保持调用方（_handle_parse_resume）传参语义不变

**为什么不暴露新工具/服务**：
- v0.5a 是内部 refactor，零 call surface 变化
- v0.5b 才会新增 `retry_raw_resume` 工具定义（tools 列表 + handlers 映射）

### 3.2 状态机边界统一

`processing → parsed/failed` 全部集中在 `_do_extract_and_link`：

| 状态 | 触发条件 | 字段更新 |
|---|---|---|
| `processing` | _handle_parse_resume 第一落 | `status=PROCESSING`（新行）|
| `failed` | LLM 抛异常 或 email 为空 | `status=FAILED, error_message=low_confidence_or_extraction_error` |
| `parsed` | LLM 成功 + (auto_create=True 路径) | `status=PARSED, candidate_id=created.id` |

**v0.5b retry 工具** 复用这条转换链：`failed → processing → parsed/failed`。

### 3.3 auto_create=False 早返回保留

原代码 `else: return {"status": "success", "data": {raw_resume_id, candidate_id="", auto_create_skipped: True}}` — **不**创建候选人、**不**更新 raw_resumes 状态。

v0.5a 保持原行为不变（明确写在 docstring 里），避免 v0.4d 之前存在的隐式契约被破坏。

**未来 v0.6 候选**：auto_create=False 时也写 `status=PARSED`（不链 candidate_id），让 retry 工具可识别"已解析但未建档"。

### 3.4 LLM 成功测恢复策略

v0.4d ship 时"不崩溃"断言不够（ship report §4 备注：MagicMock + AsyncMock + schema 验证三件套反复打架）。

v0.5a 抽公共函数后，state 落库从 2 处合并到 1 处，**用更稳的 mock 模式**：

```python
fake_rr = MagicMock()
fake_rr.status = None
fake_rr.candidate_id = None

# 1 个 db.get 拿 raw_resume mock（取代 3 层 MagicMock 嵌套）
with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
    mock_db.get = AsyncMock(return_value=fake_rr)
    ...
    result = await _do_extract_and_link("rr-test-3", "raw text", auto_create=True)

# 三件事一次验完
assert result["status"] == "success"
assert result["data"]["candidate_id"] == "cand-1"
assert fake_rr.status == RawResumeStatus.PARSED
assert fake_rr.candidate_id == "cand-1"
```

**v0.5a 新测试 = 1 个**（commit 前 v0.4d 3 个 → commit 后 v0.4d 4 个）。

## 4. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| v0.4d 4 测试全 pass | `pytest tests/mcp/integration/test_resume_parser_v0_4d.py -v` | ✅ 4 passed |
| parse_resume 行为不变 | mcp-resume server list_tools 返回 3 工具 + 14 server e2e 14/14 | ✅ |
| health-check 14/14 | `bash scripts/health-check.sh` | ✅ 14/14 |

`health-check.sh` 9 步详情：
1. ✅ 5432/6379/6333/9000 全部 LISTEN
2. ✅ uvicorn 8000 在跑
3. ✅ 登录成功（e2e-tester@test.com）
4. ✅ /auth/me 返回 user
5. ✅ 前端 /login + /agent 200/307 + _next 200
6. ✅ Playwright verify-login-e2e.ts 通过
7. ✅ 微信 mock 登录 3 步
8. ✅ 限流 60 并发 33 次 429
9. ✅ MCP 工具系统 CI 守门

mcp 14 server e2e 详情（v0.4e 重测）：
- ✅ 5 core: utils/weather/search/screening/knowledge (P95 666ms)
- ✅ 9 secondary: candidate/job/application/interview/evaluation/jd/resume/skill-mgr/dashboard (P95 908ms)
- mcp-resume tools=3（v0.5b 加 retry_raw_resume 后变 4）

## 5. 未在 v0.5a 范围

按 `.omo/plans/v0.5-replan.md` §5：

- ❌ retry_raw_resume 工具（推 v0.5b）
- ❌ mcp-resume Bheavy 完整版（推 v0.6）
- ❌ 14 server 并行 spawn 压测（推 v0.8）
- ❌ skill_mgr 工具扩展（推 v0.7）
- ❌ candidate_search 完整版归位（推 v0.9）
- ❌ retry force=True 参数（语义未定，推 v0.6）
- ❌ (status, updated_at) 复合索引（v0.5b 真不需要）

## 6. 后续路径

**v0.5b（下一步，1d，2 commit）**：
- 新增 `_handle_retry_raw_resume(raw_resume_id: str)` handler
- 校验 status（只接受 failed；processing/parsed 返 CONFLICT）
- 读 raw_resumes 表（不存在返 NOT_FOUND）
- 调 `_do_extract_and_link(raw_resume_id, raw_text)` （v0.5a 抽出）
- tools 列表加 retry_raw_resume 工具定义
- 5 新测试
- e2e 14/14 仍 pass（mcp-resume tools=4）

**v0.6+**：见 v0.5-replan.md §6。

## 7. 回滚方法

```bash
# 失败回滚（v0.5a refactor 是最容易踩雷点）
git checkout mcp-v4-v0.5a-pre   # 回到 v0.5a 改之前
# 或
git revert 88066a3               # 撤销 v0.5a commit
# 改动 2 文件：resume_parser.py (抽函数) + test_resume_parser_v0_4d.py (恢复 LLM 成功测)
# 回滚 = revert 1 commit
```

**回滚影响范围**：
- `_do_extract_and_link` 函数被删除
- `_handle_parse_resume` 恢复成 135 行单函数
- v0.5b retry_raw_resume 工具（未实施）不受影响（v0.5a 抽出公共函数，v0.5b 才用）
- 测试文件 `test_resume_parser_v0_4d.py` 删 1 测试（v0.5a 新加的）

## 8. 引用

- v0.5 重规划: `.omo/plans/v0.5-replan.md` §4
- v0.4 ship report: `docs/mcp-v4-v0.4-ship-report.md`
- e2e 脚本: `scripts/mcp_v4_e2e_14_servers.py`
- health-check 脚本: `scripts/health-check.sh`
