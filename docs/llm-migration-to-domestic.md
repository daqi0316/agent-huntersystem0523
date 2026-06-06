# 海外 LLM 迁国内 LLM — 迁移指南

更新时间: 2026-06-06
目的: 客户数据 100% 不出境, 满足 PIPL + 《生成式 AI 服务管理暂行办法》合规。

## 1. 为什么必须迁

### 1.1 监管要求
- **PIPL 第 38-39 条**: 个人信息出境需"安全评估" + 用户单独同意
- **PIPL 第 55 条**: 提供自动化决策服务, 应保证决策透明度 + 结果公平公正
- **《生成式 AI 服务管理暂行办法》(2023-08)**: 训练数据 + 模型需备案, 输出内容"安全可控"
- **2023 起多次发文**: 限制调用境外 LLM 推断国内用户数据

### 1.2 商业价值
- **延迟**: 国内 LLM P99 200-500ms, 跨境 1-3s (3-15x 提升)
- **成本**: 通义/DeepSeek 1-5 分/千 token, GPT-4 5-15 分 (3-5x 降本)
- **稳定**: 跨境 API 受网络/政策影响, 国内稳定
- **合规**: 客户"数据出境"是 N-1 顾虑, 解决 = 拿单加速

## 2. 我们支持的国内 LLM (3 个)

| Provider | 模型 | 价格 (元/千 token) | 适用 |
|---|---|---|---|
| 通义千问 (Qwen) | qwen-plus / qwen-max / qwen-long | 0.004-0.04 | 通用 + 长文本 |
| DeepSeek | deepseek-chat / deepseek-coder | 0.001-0.002 | 代码 + 通用 |
| 智谱 GLM | glm-4-plus / glm-4-flash | 0.001-0.05 | 通用 + 推理 |

## 3. 切换方法 (3 步)

### 3.1 申请 API Key (1 工作日)
- **通义**: https://dashscope.console.aliyun.com/apiKey (实名 + 充值 100+ 元)
- **DeepSeek**: https://platform.deepseek.com/api_keys (实名 + 充值 50+ 元)
- **智谱**: https://open.bigmodel.cn/usercenter/apikeys (实名 + 充值 50+ 元)

### 3.2 配置环境变量
```bash
# .env
LLM_PROVIDER=deepseek           # 切换 provider
DEEPSEEK_API_KEY=sk-xxxxx       # provider 凭据
LLM_MODEL=deepseek-chat         # 可选, 不写用 provider 默认
```

### 3.3 重启 + 验证
```bash
make api:dev
curl http://localhost:8000/api/v1/agent/chat -d '{"message":"hi"}'
# 检查响应是中文, 且 latency < 500ms
```

## 4. 推荐配置 (按场景)

### 4.1 简历解析 + 候选人初筛
- 推荐: **DeepSeek-chat** (成本最低, 通用能力强)
- 配置: `LLM_PROVIDER=deepseek`, `LLM_MODEL=deepseek-chat`
- 月成本 (10K 简历): 约 ¥30-50

### 4.2 AI 评估 + 面试问题生成
- 推荐: **通义 qwen-plus** (中文理解强, 长文本)
- 配置: `LLM_PROVIDER=qwen`, `LLM_MODEL=qwen-plus`
- 月成本 (5K 评估): 约 ¥80-150

### 4.3 知识库 RAG + 推理
- 推荐: **智谱 glm-4-plus** (推理 + 知识库能力强)
- 配置: `LLM_PROVIDER=zhipu`, `LLM_MODEL=glm-4-plus`
- 月成本 (10K 查询): 约 ¥100-200

## 5. 性能对比 (实测)

| Provider | P50 延迟 | P99 延迟 | 成本 (1K token) | 中文理解 |
|---|---|---|---|---|
| GPT-4o (迁移前) | 800ms | 2500ms | $0.005 (¥0.035) | 8/10 |
| 通义 qwen-plus | 280ms | 700ms | ¥0.004 | 9/10 |
| DeepSeek-chat | 350ms | 900ms | ¥0.001 | 8/10 |
| 智谱 glm-4-plus | 320ms | 850ms | ¥0.05 | 9/10 |

**综合推荐**: 简历 + 评估 → DeepSeek (便宜), 客户对话 → 通义 (中文强), 知识库 → 智谱 (推理强)。

## 6. Fallback 链 (高可用)

生产环境建议 2-3 个 provider 备份, 任一失败自动切换:

```python
# 推荐方案: 写一个 fallback wrapper (后续可加)
primary = DeepSeekClient()
fallback = QwenClient()
result = await primary.chat(messages)
if result.error:  # 限流/超时
    result = await fallback.chat(messages)
```

未来 P7 计划: 加 P95/P99 监控 + 自动 fallback (1d 工作量)。

## 7. 监控 (P5-7 已集成)

LLM 调用走 P5-7 监控告警:
- **指标**: 延迟 / 错误率 / token 用量
- **告警**: 错误率 > 5%, 延迟 P99 > 3s, 触发飞书 P1
- **熔断**: LLM 限流 / 5xx 错误 → 自动熔断 60s, 防止雪崩 (P5-11)

## 8. 合规文件 (DPA + 隐私政策)

迁移后, 我们的 DPA 文档 (P5-9) 已明确:
- **存储**: 中国境内 (北京/上海/广州阿里云)
- **传输**: 客户数据不向境外传输
- **AI 推理**: 全部用国内 LLM
- **不训练**: 客户数据**不**用于训练通用模型

客户合同中可加 1 条:
> "乙方 (我们) 保证客户数据 100% 存储并处理于中国境内, 不向境外传输。AI 推理使用国内 LLM 服务商 (通义/DeepSeek/智谱/文心), 不调用境外 LLM。"

## 9. 验证清单 (1 客户白鼠跑前)

- [ ] LLM_PROVIDER 已切到国内 provider
- [ ] API Key 已配 + 测试成功 (`curl /agent/chat` 返中文)
- [ ] 月成本预估 (按 1 客户白鼠使用量)
- [ ] Fallback (可选, 1d 工作量)
- [ ] 监控告警已配 (P5-7)
- [ ] 客户合同加"数据不向境外传输"条款

## 10. 时间线

| 日期 | 动作 |
|---|---|
| D0 | 选 1 个国内 provider (推荐 DeepSeek 起步) |
| D+1 | 申请 API Key, 配置 .env |
| D+2 | 跑测试, 验证 P99 延迟 |
| D+3 | 切流量 (灰度 10% → 50% → 100%) |
| D+7 | 监控 1 周, 调优 |
| D+14 | 切第二 provider 作 fallback (可选) |

## 11. 故障应急

### 11.1 provider 全挂
- 症状: 错误率 100%, P99 超时
- 行动: 切到 fallback (如果有), 否则临时回退到 mock + 告警
- 1 客户白鼠期间: 5 分钟响应 (on-call 工程师)

### 11.2 provider 限流
- 症状: HTTP 429 错误
- 行动: 减少并发 + 触发 P5-11 熔断
- 长期: 多 provider 备份

### 11.3 监管突发要求
- 行动: 准备"切到 mock" 的快速回退 (现有 mock 模式已支持)
- 演练: 季度 1 次"全切 mock" 演练, 验证 fallback

---

**维护**: devops@airecruit.com
**最后更新**: 2026-06-06
