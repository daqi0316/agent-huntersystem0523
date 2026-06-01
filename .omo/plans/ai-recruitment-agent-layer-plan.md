# AI 招聘系统 — Agent 层补完计划

> 基於：`AI_Recruitment_Multi_Agent_System_Prompt_Architecture.md` (v1.0, 2026-05-27)
> 目標：將當前 Agent 系統提升至與架構文檔完全一致
> 作者：Sisyphus
> 驗證規則：每個 Phase 完成後 `lsp_diagnostics` clean + `pytest` 現有不能紅 + 新增測試覆蓋

---

## 當前狀態 vs 文檔目標

| Agent | 文檔代號 | 當前狀態 | 差距 |
|-------|---------|---------|------|
| Orchestrator | 調度中樞 (Type-A) | ✅ `orchestrator_agent.py` 已有 DAG 分解+路由 | 缺 System Prompt、Context Package 格式、消息傳遞協議、命名記憶規範 |
| Sourcing | 獵手 (Prompt-B) | ❌ 僅 `search_candidates` DB 工具 | 無獨立 Agent 實體、無人才 Mapping、無渠道策略、無話術生成 |
| Screening | 篩官 (Prompt-C) | ✅ Pipeline + Aggregator 已實現 | 需整合為統一 ScreeningAgent，補評分維度、風險標記 |
| Interview | 面試官助理 (Prompt-D) | ⚠️ HumanLoopAgent + InterviewService | 缺評價表生成、反饋收集/匯總、面試輪次定義 |
| Offering | 談判專家 (Prompt-E) | ❌ 完全不存在 | 從零建設 |
| Onboarding | 迎新官 (Prompt-F) | ❌ 完全不存在 | 從零建設 |
| Analytics | 數據官 (Prompt-G) | ❌ 僅 `get_dashboard_stats` 計數 | 從零建設 |

### 共享層差距

| 層 | 文檔要求 | 當前狀態 | 差距 |
|----|---------|---------|------|
| 共享記憶 | KV 存儲 + 命名規範 | ✅ SummaryService + MemoryFactService | 缺 KV 存儲層，命名規範未實現 |
| 消息傳遞 | 結構化消息格式 | ❌ 無 | 當前是直接函數調用，無標準消息協議 |
| 安全策略 | 數據最小化/審計/隔離 | ❌ 僅 JWT 認證 | 缺 Agent 級權限隔離、操作審計日誌、敏感數據脫敏 |

---

## 執行策略（Momus Audit 修正後）

- **Phase 1 全串行**：1.1 → 1.2 → 1.3（接口 freeze 後才可並行開發內部件）
- **Phase 2 新建 Agent 使用薄 adapter**：先直接函數調用，後續 Phase 3.2 MessageBus 完成後只改 adapter
- **Phase 3.2（MessageBus） 提前到 Phase 2 之前**：避免 Phase 2 Agent 重複改造
- **新模型必須含 Alembic migration**
- **System Prompt 放在獨立目錄 `agents/prompts/`，不硬編碼在 Python 類中**
- **新增 AgentRegistry：統一管理 Agent 名稱→實例映射**
- **send_reminder 先做 stub（log-only），郵件集成延後**

```
依賴圖（修正後）：
Phase 1 (串行)
  └── 1.1 Orchestrator System Prompt + Context Package + AgentRegistry
       └── 1.2 Screening 統一化
            └── 1.3 Interview 功能補全
                 │
Phase 1.5 (共享層基礎建設)
  ├── 1.5.1 KV 共享記憶層 (parallel-ready with 1.3)
  ├── 1.5.2 AgentRegistry (已在 1.1 完成)
  └── 1.5.3 MessageBus 消息傳遞協議
       │
Phase 2 (新建缺失 Agent，使用 MessageBus)
  ├── 2.1 Sourcing Agent
  ├── 2.2 Offering Agent (parallel-ready with 2.1)
  ├── 2.3 Onboarding Agent (parallel-ready with 2.1, 2.2)
  └── 2.4 Analytics Agent (parallel-ready with 2.1-2.3)
       │
Phase 3 (共享層安全增強，parallel with Phase 2)
  ├── 3.1 安全策略 - 審計日誌 (parallel-ready with 2.x)
  ├── 3.2 安全策略 - 數據最小化 (parallel-ready with 2.x)
  └── 3.3 安全策略 - 權限隔離 (parallel-ready with 2.x)
```

---

## Phase 0：基礎設施建設（新增）

### 0.1 AgentRegistry — 統一 Agent 註冊與發現

**目標**：解決 F4（route() 返回類型問題）和 M1（無註冊中心）。統一管理所有 Agent 的名稱→實例映射。

```
0.1.1	apps/api/app/agents/registry.py（新建）
	- AgentRegistry 單例類
	  register(name: str, agent: BaseAgent) → None
	  resolve(name: str) → BaseAgent | None
	  list_agents() → list[str]
	  get_status(name: str) → dict（查詢 Agent 是否可用）
	- 支援 lazy registration（import 時自動註冊）

0.1.2	apps/api/app/agents/__init__.py
	- 導入所有 Agent 模塊，觸發自動註冊

0.1.3	tests/test_agents/test_registry.py（新建）
	- 測試 register/resolve/list
	- 測試重名註冊處理
	- 測試不存在的 name 返回 None
```

### 0.2 System Prompt 目錄結構

**目標**：解決 M4（System Prompt 硬編碼），將所有 Prompt 移至獨立文件。

```
0.2.1	apps/api/app/agents/prompts/（新建目錄）
	- orchestrator.md — Type-A（文檔第 105-156 行）
	- sourcing.md — Prompt-B（文檔第 187-273 行）
	- screening.md — Prompt-C（文檔第 301-389 行）
	- interview.md — Prompt-D（文檔第 417-502 行）
	- offering.md — Prompt-E（文檔第 531-610 行）
	- onboarding.md — Prompt-F（文檔第 638-712 行）
	- analytics.md — Prompt-G（文檔第 741-823 行）

0.2.2	apps/api/app/agents/prompts/__init__.py
	- load_prompt(name: str) → str — 從文件加載，不存在時返回 ""
	- reload_prompts() — 熱加載（開發模式）
```

### 0.3 BaseAgent 擴展

**目標**：為所有 Agent 增加通用能力（System Prompt 注入、註冊自動化）。

```
0.3.1	apps/api/app/agents/base.py（擴展現有）
	- 增加 self.system_prompt: str（從 prompts/ 目錄加載）
	- 增加 self.agent_type: str（類名稱自動推導）
	- __init_subclass__ 掛鉤：自動呼叫 AgentRegistry.register()
	- 增加 async def load_prompt(self) → 自動對應文件
```

---

## Phase 1：強化現有 Agent（全串行）

### 1.1 Orchestrator 強化

**目標**：為 Orchestrator 加上文檔定義的 System Prompt (Type-A)，實現 Context Package 格式和顯示路由宣告。

**當前**：`orchestrator_agent.py` 已有 LLM 分解 + DAG 調度。RouterAgent 有 8 類型意圖分類。

```
1.1.1	apps/api/app/agents/orchestrator_agent.py
	- 繼承 BaseAgent 新特性（自動加載 system_prompt）
	- 實現 Context Package（Pydantic model: task_id, agent_type, instruction, context, shared_memory_keys）
	- decompose() 結果改為 Context Package 格式
	- 聚合結果時標註數據來源："根據 {AgentName} 返回..."
	- 異常處理：子 Agent 失敗時重試 1 次，仍失敗則降級
	- 多階段任務檢測：入口判斷指令是否包含多個階段關鍵詞
	  → 是：走 decompose() → DAG 調度
	  → 否：走 RouterAgent 單意圖路由

1.1.2	apps/api/app/agents/router_agent.py
	- 擴展意圖映射表，增加 offering / onboarding / analytics 三種新意圖
	- 更新 PROMPT_TEMPLATE 和 _RULES 關鍵詞列表（增加 offer/入職/數據報表等關鍵詞）
	- route() 改為透過 AgentRegistry 解析（名稱→實例）
	- 新增 get_available_intents() 方法

1.1.3	apps/api/app/services/agent_service.py
	- chat_with_tools() 入口處增加多階段檢測
	  → 調用 Orchestrator.guess_type() 判斷是否多階段
	  → 多階段：走 Orchestrator.run()
	  → 單階段：保持現有 tool-calling 循環

1.1.4	tests/test_agents/test_orchestrator.py（新建）
```

### 1.2 ScreeningAgent 統一化

**目標**：將現有 PipelineAgent + AggregatorAgent + ScreeningService 整合為統一 Agent。

**當前**：`pipeline.py` (解+匹+門控) + `aggregator.py` (3 維度並行) + `screening.py` (服務封裝)。

```
1.2.1	apps/api/app/agents/screening_agent.py（新建）
	- 繼承 BaseAgent，自動加載 prompts/screening.md
	- 封裝 PipelineAgent + AggregatorAgent 為內部件
	- integrate 方法：調用 Pipeline → Aggregator → 合併輸出
	- 評分維度擴展為文檔的 6 維度
	- 風險標記系統（gap/job_hopping/skill_inflation/salary_mismatch）
	- batch_screen() 批量處理，輸出 Markdown 對比矩陣

1.2.2	apps/api/app/services/screening.py
	- 重構為調用 ScreeningAgent 而非直接 Pipeline+Aggregator
	- 保持 DB status 流轉和返回格式不變（向後兼容）

1.2.3	apps/api/app/api/screening.py（新建）
	- 註冊路由到 api_router
	- POST /screen, POST /screen/batch, GET /screen/{candidate_id}/result

1.2.4	apps/api/app/models/（無新模型，復用現有）
```

### 1.3 InterviewAgent 功能補全

**目標**：補全文檔 Prompt-D 的缺失功能（評價表、反饋收集、輪次定義）。

**send_reminder 先做 stub**（log-only），郵件/SMS 集成分離為後續 Phase。

```
1.3.1	apps/api/app/agents/interview_agent.py（新建）
	- 繼承 BaseAgent，自動加載 prompts/interview.md
	- 封裝 HumanLoopAgent + InterviewService
	- generate_evaluation_form(interview_id, round) — LLM 生成結構化評價表
	- collect_feedback(interview_id, feedback_data) — 收集面試官反饋
	- summarize_feedback(candidate_id) — LLM 匯總多輪反饋
	- schedule_interview_rounds() — 按文檔 4 輪標準安排
	- send_reminder(interview_id) — stub：log 已發送，不實際發送

1.3.2	apps/api/app/models/interview_evaluation.py（新建）
	- 模型 + alembic migration

1.3.3	apps/api/app/services/interview.py
	- 擴展 schedule() 支持 4 輪定義（R1-R4）
	- 新增 get_interviewer_availability(), batch_schedule()

1.3.4	apps/api/app/api/interviews.py（擴展現有）
	- POST /interviews/{id}/evaluation, GET /interviews/{id}/evaluation
	- GET /candidates/{id}/feedback-summary
```

---

## Phase 1.5：共享層基礎建設

### 1.5.1 KV 共享記憶層

**目標**：Redis KV 存儲 + 命名規範 + TTL。降級鏈：Redis → 單 worker in-memory → 多 worker 無共享（文檔說明）。

```
1.5.1.1	apps/api/app/services/shared_memory.py（新建）
	- Redis KV 存儲（降級 in-memory dict）
	- 命名規範強制：{agent_type}/{resource_type}/{resource_id}/{version}
	- set(key, value, ttl), get(key), delete(key), list(prefix)
	- TTL 默認 24h，版本自動 +1
	- get_context(agent_type, resource_ids) — 批量組裝 Context Package

1.5.1.2	apps/api/app/agents/orchestrator_agent.py
	- 調用 SharedMemory.get_context() 組裝 Context Package

1.5.1.3	tests/test_services/test_shared_memory.py（新建）
```

### 1.5.2 MessageBus 消息傳遞協議

**目標**：文檔定義的消息格式 + 發送/接收機制。所有新建 Agent 直接使用 MessageBus。

```
1.5.2.1	apps/api/app/agents/message.py（新建）
	- Message Pydantic model（文檔第 849-863 行 schema）
	- create_message() / validate_message()

1.5.2.2	apps/api/app/agents/message_bus.py（新建）
	- MessageBus 類：send/subscribe/get_status
	- 支援 asyncio.Queue（單 worker）和可擴展到 Redis pub/sub
	- 優先級佇列

1.5.2.3	tests/test_agents/test_message_bus.py（新建）
```

---

## Phase 2：新建缺失 Agent（使用 MessageBus + 薄 adapter）

### 2.1 SourcingAgent

**目標**：文檔 Prompt-B。人才 Mapping + 渠道策略 + 話術生成。

```
2.1.1	apps/api/app/services/sourcing_service.py（新建）
	- search_talent_pool() — DB + 向量混合搜索
	- generate_talent_map() — LLM 生成目標公司/團隊 Mapping（LLM 不可用時返回空列表）
	- generate_channel_strategy() — 渠道預算分配（硬編碼規則，無 LLM 依賴）
	- generate_outreach_template() — LLM 生成個性化話術（LLM 不可用時返回模板）
	- recommend_candidates() — 推薦在庫候選人
	- activate_passive_candidates() — 沉睡候選人激活策略

2.1.2	apps/api/app/agents/sourcing_agent.py（新建）
	- 繼承 BaseAgent，prompts/sourcing.md
	- 輸出格式符合文檔

2.1.3	apps/api/app/api/sourcing.py（新建）
	- POST /sourcing/talent-map, POST /sourcing/outreach
	- GET /sourcing/candidates

2.1.4	apps/api/app/services/agent_service.py
	- 新增 search_talent_pool 工具

2.1.5	tests/test_agents/test_sourcing_agent.py（新建）
```

### 2.2 OfferingAgent

**目標**：文檔 Prompt-E。薪酬設計 + 談判策略 + Offer 生命周期。

```
2.2.1	apps/api/app/models/offer.py（新建）+ alembic migration

2.2.2	apps/api/app/services/offering_service.py（新建）
	- get_salary_benchmark() — 硬編碼基準表（按城市+職級+經驗），非 LLM
	- calculate_total_package() — 總包計算（文檔公式）
	- generate_offer_letter() — LLM 生成（不可用時返回模板）
	- send_offer() — stub（log-only 發送）
	- track_offer_status() — DB 狀態查詢
	- negotiate_strategy() — 按文檔 5 場景對照表生成（規則引擎，無 LLM）
	- risk_assessment() — LLM 輔助風險評估（不可用時返回中等風險默認值）

2.2.3	apps/api/app/agents/offering_agent.py（新建）+ prompts/offering.md

2.2.4	apps/api/app/api/offer.py（新建）
	- POST /offers, GET /offers/{id}, POST /offers/{id}/send
	- POST /offers/{id}/accept, POST /offers/{id}/reject
	- GET /offers/{id}/negotiation-strategy

2.2.5	tests/test_agents/test_offering_agent.py（新建）
```

### 2.3 OnboardingAgent

**目標**：文檔 Prompt-F。入職計劃 + 里程碑 + 轉正評估。

```
2.3.1	apps/api/app/models/onboarding.py（新建）+ alembic migration
	- CandidateStatus 增加 HIRED / ONBOARDING / PROBATION / CONFIRMED

2.3.2	apps/api/app/services/onboarding_service.py（新建）
	- generate_onboarding_plan() — 按 8 里程碑生成
	- track_onboarding_progress() — 進度跟蹤
	- schedule_check_in() — 安排 check-in
	- collect_feedback() — 收集反饋
	- generate_probation_review() — LLM 生成轉正評估（不可用時返回結構化空殼）

2.3.3	apps/api/app/agents/onboarding_agent.py（新建）+ prompts/onboarding.md

2.3.4	apps/api/app/api/onboarding.py（新建）
```

### 2.4 AnalyticsAgent

**目標**：文檔 Prompt-G。漏斗 + 渠道 + 預測 + 儀表盤。anomaly_detection v1=簡單閾值。

```
2.4.1	apps/api/app/services/analytics_service.py（新建）
	- query_hiring_data() — 多維度 SQL 聚合
	- generate_funnel_report() — 全鏈路轉化率計算
	- generate_channel_report() — 各渠道 ROI/轉化率/成本
	- predict_time_to_fill() — 歷史平均（無數據時返回 "insufficient_data"）
	- anomaly_detection() — v1: 環比下降 > X% 觸發告警
	- KPI：Time to Fill, Offer Acceptance Rate, Time to Start, Cost per Hire, Interview to Offer Ratio
	- 質量 KPI（New Hire Retention / Manager Satisfaction / Candidate NPS）標註為 v2

2.4.2	apps/api/app/agents/analytics_agent.py（新建）+ prompts/analytics.md
```

---

## Phase 3：共享層安全增強（可與 Phase 2 並行）

### 3.1 審計日誌

```
3.1.1	apps/api/app/models/audit_log.py（新建）+ alembic migration
3.1.2	apps/api/app/core/audit_logger.py（新建）
	- log_write(agent, resource, action, details) → 非同步寫入 PostgreSQL
	- 保留 180 天，自動清理
	- 僅 append，不可篡改
```

### 3.2 數據最小化

```
3.2.1	apps/api/app/core/data_minimizer.py（新建）
	- filter_fields(agent_type, data) — 白名單過濾
	- 敏感字段自動脫敏：phone(***XXXX****), id_number(**********XXXX)
```

### 3.3 權限隔離

```
3.3.1	apps/api/app/core/permission.py（新建）
	- AgentPermission + check_permission()
```

---

## 工作量估計（修正後）

| Phase | 新增檔案 | 修改檔案 | 估計工時 |
|-------|---------|---------|---------|
| 0.1 AgentRegistry | 2 | 1 | 2-3h |
| 0.2 Prompts 目錄 | 8 | 1 | 2-3h |
| 0.3 BaseAgent 擴展 | 0 | 1 | 1-2h |
| 1.1 Orchestrator 強化 | 0 | 3 | 6-8h |
| 1.2 Screening 統一化 | 3 | 2 | 10-12h |
| 1.3 Interview 補全 | 3 | 3 | 8-10h |
| 1.5.1 KV 共享記憶 | 2 | 1 | 4-6h |
| 1.5.2 MessageBus | 3 | 0 | 4-6h |
| 2.1 Sourcing Agent | 4 | 1 | 10-12h |
| 2.2 Offering Agent | 5 | 0 | 14-18h |
| 2.3 Onboarding Agent | 4 | 0 | 10-12h |
| 2.4 Analytics Agent | 3 | 1 | 10-12h |
| 3.1 審計日誌 | 3 | 0 | 4-6h |
| 3.2 數據最小化 | 1 | 0 | 4-6h |
| 3.3 權限隔離 | 1 | 0 | 4-6h |
| **總計** | **42** | **13** | **85-110h** |

## Git 分支策略

```
main
└── develop
    ├── feature/phase0-agent-infra
    ├── feature/phase1-agent-enhance (串行 sub-tasks)
    ├── feature/phase1.5-shared-messaging
    ├── feature/phase2-new-agents (parallel sub-branches)
    └── feature/phase3-security (parallel with phase2)
```
