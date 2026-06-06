# AI 评分披露规范 (P5-10)

更新时间: 2026-06-06
适用: AI Recruitment 全产品
依据: 2026-08 生成式 AI 服务管理办法 (中国)

## 1. 原则

所有 AI 生成的评分 / 推荐 / 评估必须:
- **可追溯**: 标识 LLM / model version / prompt hash / 生成时间
- **可覆盖**: 任何 HR 可手动改写, 改后 AI 评分作废, 落 audit
- **可申诉**: 用户 7 天内可申诉, 7 天内必回复

## 2. AI 评分来源字段 (ai_score_source JSON)

```json
{
  "llm": "qwen3.6",
  "model_version": "Qwen3.6-35B-A3B-4bit",
  "prompt_hash": "sha256:abc123...",
  "generated_at": "2026-06-01T10:30:00Z",
  "temperature": 0.7,
  "max_tokens": 1024
}
```

存储位置:
- `recommendation.ai_score_source` (候选-职位匹配评分)
- `interview_evaluation.ai_score_source` (面试评估)

## 3. UI 标识规则

### 3.1 评分显示
- 评分旁加 "AI 评分" 标签 (小图标 + 文字)
- hover 显示完整 ai_source (LLM / model / 时间)
- score_overridden=True 时显示 "人工改写" 标签 + 原始 AI 分 (划线)

### 3.2 人工覆盖
- 每个 AI 评分下有 "改写" 按钮 (HR 限定)
- 点击 → modal 输入新分 (0-100) + 原因 (≥5 字符)
- 提交后:
  - score 字段更新
  - score_overridden = true
  - score_overridden_by / score_overridden_at / score_override_reason 落库
  - 落 audit (AI_OVERRIDE), 含 original_score / new_score / reason / ai_source

### 3.3 申诉
- 每个 AI 评分下有 "申诉" 按钮
- 点击 → modal 输入原因 (≥10 字符, ≤2000)
- 提交后:
  - 申诉 status = PENDING, due_at = now + 7d
  - 落 audit (APPEAL_FILED)
- 管理员在 /ai-compliance/appeals 处理:
  - accept → RESOLVED_ACCEPTED, 触发 AI 重新评估 (P5-10+)
  - reject → RESOLVED_REJECTED, 写 resolution 备注
  - 落 audit (APPEAL_RESOLVED)

## 4. SLA

| 状态 | SLA |
|---|---|
| 申诉提交 → 首次响应 | 7 天 |
| 申诉提交 → 解决 | 7 天内 (PENDING → RESOLVED_*) |
| 改写评分 → 落 audit | 实时 (同步) |

SLA 超时监控: 飞书 webhook 通知 (P5-7 复用)

## 5. 数据保留

- ai_score_source: 与主记录同生命周期
- audit (AI_OVERRIDE / APPEAL_*): 6 个月 (P5-1 默认)
- 申诉 resolution: 永久 (合规追溯)

## 6. 边界情况

| 情况 | 处理 |
|---|---|
| AI 评分生成失败 | 不写入 score, 留空, 不影响其他业务 |
| 用户改写后又改回原值 | score_overridden 仍为 true, 但 record 在 audit |
| 申诉已 RESOLVED 后再申诉 | 409 Conflict, 提示走新工单 |
| 申诉 7 天后未处理 | 飞书通知管理员, 但不自动拒绝 |

## 7. 与其他 Phase 集成

- P5-1 审计日志: AI_OVERRIDE / APPEAL_FILED / APPEAL_RESOLVED 3 个新 enum
- P5-7 监控告警: appeal 7d SLA 超时进告警 (P2)
- P5-8 配额: AI 评分生成计入 LLM token quota
- P5-11 反垃圾: 申诉频次超阈值 (10次/7d) → 限制

## 8. API 端点 (10 个)

| 端点 | 方法 | 说明 |
|---|---|---|
| /ai-compliance/appeals | POST | 创建申诉 |
| /ai-compliance/appeals | GET | 列表 |
| /ai-compliance/appeals/{id} | GET | 查详情 |
| /ai-compliance/appeals/{id}/resolve | POST | 接受/驳回 |
| /ai-compliance/recommendations/{id}/override-score | POST | 人工改写评分 |
| /ai-compliance/recommendations/{id}/ai-source | GET | 查 AI 来源 |
