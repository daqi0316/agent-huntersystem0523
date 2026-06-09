# 面试录音功能实施计划（Momus 审核修正版）

> 日期：2026-06-08  
> 状态：待确认 / 未实施  
> 依据：`AI_招聘_Agent_系统架构文档_含录音功能.md` + 当前 repo 实现扫描  
> 审核口径：按 Momus 标准检查清晰性、可验证性、边界、风险、依赖与验收门槛。

---

## 0. 审核结论

原架构文档方向正确，但不能直接实施，原因：

1. **技术栈不一致**：文档写 MySQL / Elasticsearch；当前系统是 PostgreSQL / Redis / Qdrant / MinIO。
2. **录音入口混淆**：文档主写后端 `sounddevice` 本机录音，但产品真实入口是 Next.js 浏览器。
3. **MVP 边界过大**：实时 ASR、说话人分离、情绪分析、雷达图、90 天自动归档不适合首版一起做。
4. **合规缺口**：录音必须有显式同意、操作者、访问权限、保留策略字段。
5. **验证缺口**：必须纳入现有 `scripts/health-check.sh`，否则不算完成。

修正后建议：**浏览器录音上传为产品主路径；本地 `sounddevice` MCP 录音仅作为可选内部 demo/运维路径。**

---

## 1. 当前代码落点

| 能力 | 当前文件 | 结论 |
|---|---|---|
| 面试 Agent | `apps/api/app/agents/interview_agent.py` | 已有评价表生成、反馈汇总，可扩展转录文本评估 |
| 面试 MCP Server | `apps/api/app/mcp_servers/builtin/interview_server.py` | 已聚合 7 个面试工具，录音工具应并入这里 |
| 面试工具 | `apps/api/app/tools/interview.py`, `apps/api/app/tools/interview_extended.py` | 已有 schedule/cancel/feedback/complete/detail |
| 面试 API | `apps/api/app/api/interviews.py` | 已有 CRUD、评价保存、状态流转 |
| 面试模型 | `apps/api/app/models/interview.py`, `apps/api/app/models/interview_evaluation.py` | 缺独立录音元数据表 |
| 文件存储 | README 标明 MinIO | 录音文件应优先走 MinIO；本地存储仅 fallback |
| 前端 | `apps/web` | 需新增录音 UI，禁止裸 `fetch`，走现有 API wrapper |
| 健康检查 | `docs/system-health-check.md`, `scripts/health-check.sh` | 任何代码改动后必须跑 |

---

## 2. MVP 范围

### 2.1 必做

1. 浏览器端录音：开始 / 暂停 / 继续 / 停止。
2. 录音文件上传后端。
3. 录音元数据入库。
4. Mock ASR Provider 跑通转录闭环。
5. 转录文本可写回录音记录。
6. 面试 Agent 可基于转录文本生成结构化反馈。
7. MCP 面试工具暴露录音状态/转录触发能力。
8. 单元测试 + API 测试 + MCP handler 测试 + 前端基础测试。
9. `bash scripts/health-check.sh` 通过。

### 2.2 暂缓

1. 实时 ASR。
2. 说话人分离。
3. 情绪、语速、关键词深度分析。
4. 雷达图复杂可视化。
5. Elasticsearch。
6. 自动 90 天清理任务。
7. 后端 `sounddevice` 真实录音工具。
8. Qwen3-ASR / omlx 真实模型接入。

暂缓项不得混入 MVP，否则范围失控。

---

## 3. 产品主路径

```text
用户进入面试页面
  -> 点击“开始录音”
  -> 浏览器 MediaRecorder 采集音频
  -> 点击“停止录音”
  -> 前端上传音频文件
  -> 后端创建 interview_recordings 记录
  -> 后端保存到 MinIO 或本地 fallback
  -> 用户点击“转写”或系统自动触发 mock ASR
  -> transcript 写回 interview_recordings
  -> InterviewAgent 基于 transcript 生成反馈
  -> 反馈写入 interview_evaluations / interview feedback
```

---

## 4. 数据模型设计

新增模型：`apps/api/app/models/interview_recording.py`

新增表：`interview_recordings`

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `interview_id` | UUID FK | 关联 `interviews.id` |
| `recording_id` | string | 业务编号，如 `REC-{interview_id}-{timestamp}` |
| `storage_backend` | enum/string | `minio` / `local` |
| `object_key` | string nullable | MinIO object key |
| `file_path` | string nullable | 本地 fallback 路径 |
| `mime_type` | string | `audio/webm`, `audio/wav` 等 |
| `duration_seconds` | float nullable | 录音时长 |
| `file_size_bytes` | int | 文件大小 |
| `sample_rate` | int nullable | 采样率 |
| `channels` | int nullable | 声道数 |
| `status` | enum/string | `uploading`, `recorded`, `transcribing`, `transcribed`, `failed`, `deleted` |
| `transcript_text` | text nullable | 转录全文 |
| `transcript_json` | json/text nullable | 分段、时间戳、置信度 |
| `consent_confirmed_at` | datetime | 录音同意时间 |
| `consent_by_user_id` | string/UUID | 确认录音的人 |
| `created_by` | string/UUID | 上传者 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |
| `deleted_at` | datetime nullable | 软删除 |

### 不变量

1. 无 `consent_confirmed_at` 不允许创建有效录音记录。
2. `status=transcribed` 时必须有 `transcript_text`。
3. `storage_backend=minio` 时必须有 `object_key`。
4. `storage_backend=local` 时必须有 `file_path`。
5. 删除只做软删除；真实物理删除进入后续保留策略任务。

---

## 5. API 设计

挂在现有面试资源下：

```text
POST   /api/v1/interviews/{interview_id}/recordings
GET    /api/v1/interviews/{interview_id}/recordings
GET    /api/v1/interviews/{interview_id}/recordings/{recording_id}
POST   /api/v1/interviews/{interview_id}/recordings/{recording_id}/upload
POST   /api/v1/interviews/{interview_id}/recordings/{recording_id}/transcribe
DELETE /api/v1/interviews/{interview_id}/recordings/{recording_id}
```

### MVP 可简化

如果实现成本过高，首版可合并为：

```text
POST /api/v1/interviews/{interview_id}/recordings/upload
POST /api/v1/interviews/{interview_id}/recordings/{recording_id}/transcribe
GET  /api/v1/interviews/{interview_id}/recordings/{recording_id}
```

### API 规则

1. 必须走 `org_scoped_db`。
2. 必须校验 `interview_id` 存在且属于当前组织。
3. 上传大小限制：MVP 默认 50MB。
4. MIME 白名单：`audio/webm`, `audio/wav`, `audio/mpeg`, `audio/mp4`。
5. 前端禁止裸 `fetch`，必须复用现有授权 API wrapper。

---

## 6. 服务层设计

新增：`apps/api/app/services/interview_recording.py`

职责：

1. 创建录音记录。
2. 校验 consent / 文件大小 / MIME。
3. 保存文件到 MinIO 或本地 fallback。
4. 更新录音状态。
5. 调用 ASR provider。
6. 软删除。

不要把业务逻辑写在 API handler 或 MCP handler 里。

---

## 7. ASR Provider 设计

先抽象，不直接硬接 omlx。

```python
class ASRProvider:
    async def transcribe(self, audio_path: str) -> TranscriptionResult:
        ...
```

实现顺序：

1. `MockASRProvider`：MVP 和测试使用。
2. `LocalOmlxASRProvider`：后续接 Qwen3-ASR-1.7B-8bit。

验收要求：mock provider 可稳定返回：

```json
{
  "full_text": "...",
  "segments": [
    {"start_time": 0, "end_time": 5, "text": "...", "speaker": null, "confidence": 1.0}
  ],
  "model_used": "mock-asr"
}
```

---

## 8. MCP 工具设计

新增工具文件：`apps/api/app/tools/interview_recording.py`

工具清单：

| 工具 | 作用 | MVP |
|---|---|---|
| `create_recording_session` | 创建录音元数据/会话 | 可选 |
| `get_recording_status` | 查询录音/转录状态 | 必做 |
| `transcribe_recording` | 触发 ASR 转录 | 必做 |
| `attach_recording_feedback` | 基于转录文本生成/写入反馈 | 可选 |

并入：`apps/api/app/mcp_servers/builtin/interview_server.py`

约束：

1. 不破坏现有 7 个工具。
2. handler 只调 service，不直接操作 DB。
3. 工具返回统一 `status` + `data/error`。

---

## 9. 前端设计

新增组件建议：

```text
apps/web/components/interviews/InterviewRecorder.tsx
```

状态机：

```text
idle -> recording -> paused -> recording -> stopped -> uploading -> uploaded -> transcribing -> transcribed
```

MVP UI：

1. 录音同意提示。
2. 开始 / 暂停 / 继续 / 停止按钮。
3. 录音计时。
4. 上传状态。
5. 转写状态。
6. 转录文本展示。

浏览器 API：`MediaRecorder`。

注意：先用 `audio/webm`，不要强行前端转 WAV；后端/ASR 适配另做。

---

## 10. Agent 编排修改

修改：`apps/api/app/agents/interview_agent.py`

新增能力：

1. 接受转录文本作为评估上下文。
2. 生成反馈时必须引用 transcript 中的具体证据。
3. 没有转录文本时，不允许声称“基于录音表现”。

禁止：

1. Agent 直接处理音频文件。
2. Agent 直接写 DB。
3. Agent 对未转录内容做主观推断。

---

## 11. 实施阶段

### P0：计划确认

交付：本文件确认通过。

验收：用户确认 MVP 范围与暂缓项。

### P1：后端模型 + migration

交付：`InterviewRecording` 模型、Alembic migration。

验收：migration 可升级；模型测试通过。

### P2：服务层 + Mock ASR

交付：`InterviewRecordingService`、`MockASRProvider`。

验收：创建、上传元数据、转录状态更新单测通过。

### P3：API

交付：recording upload / get / transcribe endpoint。

验收：API 测试覆盖成功、非法 interview、无 consent、大文件、非法 MIME。

### P4：MCP 工具

交付：`interview_recording.py` 工具并入 `mcp-interview`。

验收：tool schema 测试 + handler 测试通过。

### P5：前端录音组件

交付：`InterviewRecorder` 组件接入面试页面或 Agent 面板。

验收：录音状态机测试；上传调用走授权 API wrapper。

### P6：Agent 反馈闭环

交付：基于 transcript 生成面试反馈。

验收：无 transcript 不生成录音依据；有 transcript 时引用具体片段。

### P7：全链路验证

交付：测试 + 健康检查报告。

验收：

```bash
bash scripts/health-check.sh
```

必须通过。

---

## 12. 测试计划

### 后端单测

1. `InterviewRecordingService.create_recording` 成功。
2. 无 consent 创建失败。
3. 非法 MIME 失败。
4. 超大小失败。
5. mock transcribe 成功写回 transcript。
6. 不存在 interview_id 返回 404/错误。

### MCP 测试

1. `get_recording_status` schema 正确。
2. `transcribe_recording` happy path。
3. invalid recording_id 返回结构化错误。

### 前端测试

1. idle -> recording。
2. recording -> paused -> recording。
3. stop 后出现上传按钮/自动上传。
4. 上传失败有错误提示。
5. 转录完成展示 transcript。

### E2E

最小链路：

```text
登录 -> 进入面试页面 -> mock 录音 blob -> 上传 -> mock 转录 -> 展示 transcript
```

---

## 13. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 浏览器录音权限被拒 | 高 | UI 明确提示并提供重试；不阻塞其他面试功能 |
| 大文件上传慢/失败 | 高 | MVP 限 50MB；错误提示；后续分片上传 |
| ASR 模型接入不稳定 | 高 | 首版 mock provider；真实 omlx 独立阶段接入 |
| 隐私合规缺口 | 高 | consent 字段强制；权限校验；软删除 |
| MinIO 不可用 | 中 | 本地 fallback，但记录 `storage_backend` |
| 文档示例误复制 | 中 | 不复制根文档 Python 示例，重新实现 |
| 健康检查不完整 | 高 | 完成报告必须包含 `scripts/health-check.sh` 结果 |

---

## 14. 完成标准

功能完成必须同时满足：

1. MVP 必做项全部完成。
2. 暂缓项没有被半成品混入。
3. 所有新增 API 有测试。
4. 所有新增 MCP 工具有 schema/handler 测试。
5. 前端无裸 `fetch`。
6. 录音创建必须有 consent。
7. Agent 反馈必须基于 transcript 证据。
8. `bash scripts/health-check.sh` 通过。
9. 如改后端模型，Alembic migration 已验证。
10. 最终回复必须报告健康检查结果。

---

## 15. 建议下一步

用户确认本计划后再进入实施。若要压缩工期，建议只做 P1-P4 后端 + MCP 闭环，前端录音 UI 放第二批。
