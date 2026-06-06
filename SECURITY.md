# Security Policy

> AI Recruitment Assistant 安全策略 — 我们认真对待安全与隐私。

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 2.x.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

我们重视每一个安全漏洞报告, 感谢帮助我们保持用户安全。

### 如何报告
- **邮箱**: security@airecruit.com (PGP 公钥见 https://airecruit.com/.well-known/pgp-key.txt)
- **加密**: 强建议 PGP 加密, 避免明文邮件
- **标题**: `[SECURITY] <简短描述>`

### 报告应包含
1. **漏洞描述**: 详细说明问题 + 触发步骤
2. **影响范围**: 哪些数据 / 功能 / 用户受影响
3. **复现步骤**: 最小可复现的 PoC (截图 / curl 命令 / 视频)
4. **环境信息**: 浏览器 / OS / API 版本 / 时间
5. **你的判断**: CVSS 评分 (可选)

### 响应时间 (SLA)

| 严重度 | 首次响应 | 修复目标 |
|---|---|---|
| P0 (Critical) | 1 小时内 | 24 小时内 |
| P1 (High) | 4 小时内 | 7 天内 |
| P2 (Medium) | 1 工作日内 | 30 天内 |
| P3 (Low) | 5 工作日内 | 90 天内 |

### 我们的承诺
1. **不追究善意研究**: 任何不违反法律的善意研究, 我们不追究法律责任
2. **不公开致谢前先告知**: 修复后再公开, 给研究人员审查稿件机会
3. **致谢墙**: 公开致谢有效漏洞报告者 (经同意)
4. **HackerOne 计划**: 2026 Q4 启动, 届时有 bounty

### 范围

**范围内** (欢迎报告):
- airecruit.com 主站 + 所有子域
- API: api.airecruit.com, app.airecruit.com
- 移动端: iOS / Android (上线后)
- 客户端 SDK / CLI 工具

**范围外** (不在 bounty 范围):
- 第三方服务 (阿里云 / 微信 / 钉钉) 的漏洞 → 请直接报告给对应厂商
- 拒绝服务 (DoS) 攻击本身
- 物理安全
- 社会工程学
- 已有 CVE 列表中已公开的依赖漏洞

### 安全实践
- 加密: 静态 AES-256, 传输 TLS 1.3
- 认证: JWT + 双因素 (微信扫码)
- 审计: 全操作日志, 7 年留存
- 漏洞扫描: 每月 1 次阿里云漏洞扫描
- 渗透测试: 每年 1 次第三方
- 等保三级 / ISO 27001 (在办, 2026 Q4 取证)

### 联系方式
- 安全邮箱: security@airecruit.com
- 紧急 (P0): +86-138-XXXX-XXXX (付费用户, 见合同)
- 邮寄: 北京市朝阳区某某大厦 18 层 1801 室

---

最后更新: 2026-06-06
维护: security@airecruit.com
