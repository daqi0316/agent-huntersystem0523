# 客户白鼠 onboarding 邮件 Drip 模板

> 5 封邮件, 配合站内信 + 微信 + 短信使用, 4 通道冗余。
> 在 Mailchimp / 阿里云邮件推送 (DirectMail) 中可一键导入。

---

## 邮件 1: D-7 — 启动前 1 周 (预约 + 期待管理)

**主题**: 您的 AI 招聘助手 30 天入门 — 启动会议邀请

**正文**:

```
Hi {{ first_name }},

您即将开启 AI 招聘助手 30 天入门。🎉

为了帮您顺利启动, 我们预约了 90 分钟的 1-on-1 启动会议:

📅 时间: {{ meeting_time }}
📍 地点: 飞书会议 ({{ meeting_url }})
👥 出席: 您的客户经理 + AI 评估工程师

会议议程:
1. 互相介绍 + 期望对齐 (15 min)
2. 演示完整流程 (15 min)
3. 配置您专属的评估模板 (30 min)
4. 首次上传 1 个真实 JD (15 min)
5. Q&A + 30 天计划 (15 min)

请提前准备:
- 1 个真实 JD (非 demo, 越真实越好)
- 评估模板偏好 (技术 / 销售 / 通用)
- 5-10 个面试官邮箱 (用于邀请)

期待与您见面!

{{ csm_name }}
客户经理 · AI 招聘助手
```

**触发**: D-7 09:00 (Mailchimp workflow)

---

## 邮件 2: D0 — 启动当天 (欢迎 + 第一步)

**主题**: 欢迎使用 AI 招聘助手 — 您的 30 天从这里开始 🚀

**正文**:

```
Hi {{ first_name }},

欢迎加入! 您的 30 天试用从今天开始。

🎯 30 天目标:
- 上传 ≥ 3 个 JD
- 评估 ≥ 50 个候选人
- 完成 ≥ 5 次面试安排
- 节省 ≥ 10 小时人工

🛠 立即行动 (5 分钟):
1. 登录 https://app.airecruit.com/login
2. 上传您的第 1 个 JD (拖拽即可)
3. 体验 AI 自动解析

📚 资源:
- 完整流程视频: https://airecruit.com/help (8 分钟)
- 帮助中心: https://airecruit.com/help
- 提交工单: 客服 widget (右下角💬)

⏰ 重要时间点:
- D+3: 第 1 次 1-on-1 (15 min, 检查 onboarding)
- D+7: 中期健康度检查
- D+11: 试用到期前 3 天提醒
- D+14: 续订决策

祝试用顺利!

{{ csm_name }}
```

**触发**: D0 09:00 (启动会议后 1 小时)

---

## 邮件 3: D+3 — 第 1 次 1-on-1 之后 (鼓励 + 数据)

**主题**: 您的首周数据 — 简历筛 N 份, 节省 Nh 🤖

**正文**:

```
Hi {{ first_name }},

您的 30 天试用已过 3 天, 下面是您的进度:

📊 您的数据:
- 上传 JD: {{ jd_count }} 个 (目标 3)
- 评估候选人: {{ candidate_count }} 个 (目标 50)
- AI 评分平均分: {{ avg_score }}/100
- 节省时间: {{ hours_saved }}h (按 30min/份人工筛)

{{ if jd_count < 3 }}
💡 建议: 多上传 1-2 个 JD, AI 评估的样本越多, 准确度越高
{{ endif }}

🎓 本周小贴士:
1. 邀请面试官: 设置 → 团队 → 邀请 (建议 2-5 个)
2. 自定义评估模板: 设置 → AI 评估 → 模板 (按岗位调权重)
3. 团队协作: 候选人评论 + @ 同事

⏰ 下一个检查点: D+7 中期会议
{{ meeting_d7 }}

有问题随时找我!

{{ csm_name }}
```

**触发**: D+3 09:00

---

## 邮件 4: D+11 — 试用到期前 3 天 (续订预警)

**主题**: ⚠️ 您的试用还剩 3 天 — 续订享 8 折

**正文**:

```
Hi {{ first_name }},

您的 14 天试用将在 3 天后 (D+14) 结束, 续订享**限时 8 折 + 1 个月高级版**。

📊 您的 30 天数据:
- 上传 JD: {{ jd_count }} 个
- 评估候选人: {{ candidate_count }} 个
- 完成面试: {{ interview_count }} 次
- 节省时间: {{ hours_saved }}h
- 健康度: {{ health_score }}/100 ({{ health_grade }})

💡 续订 3 选 1:

A) 月付 (无折扣, 灵活)
   - SMB: ¥299/月
   - Pro: ¥999/月
   - Enterprise: ¥2999/月

B) 年付 (8 折, 节省 2 个月)
   - SMB: ¥2870/年 (¥239/月)
   - Pro: ¥9590/年
   - Enterprise: ¥28790/年

C) 老带新 (再 -10%)
   - 生成推荐码, 双方各得 1 个月高级版
   - 推荐码: https://app.airecruit.com/referral

🔄 续订流程 (1 分钟):
1. 登录 → 设置 → 订阅
2. 选版本 + 选周期
3. 微信/支付宝/对公转账

⏰ 决策截止: D+14 23:59 (过期降级为只读, 数据保留 30 天)

{{ if health_score < 50 }}
💬 看到您的健康度偏低 ({{ health_score }}), 我们 1-on-1 聊聊怎么帮您? 预约 30 分钟: {{ meeting_link }}
{{ endif }}

期待继续合作!

{{ csm_name }}
```

**触发**: D+11 09:00

---

## 邮件 5: D+14 — 试用到期日 (感谢 + 决策确认)

**主题**: 您的 14 天试用结束 — 期待继续合作 🎉

**正文**:

```
Hi {{ first_name }},

您的 14 天试用已结束。感谢您选择 AI 招聘助手!

📊 最终数据:
- 评估候选人: {{ candidate_count }} 个
- 完成面试: {{ interview_count }} 次
- 节省时间: {{ hours_saved }}h
- 您的健康度: {{ health_score }}/100

🎯 续订状态:
{{ if renewed }}
✅ 您已续订 ({{ plan_name }}), 数据已保留
{{ else if paused }}
⏸ 您已选择暂停, 数据保留至 D+44
{{ else }}
❓ 您尚未决策, 数据保留 30 天 (D+44)
{{ endif }}

{{ if not renewed }}
💡 3 选 1 立即决策:
1. 续订: https://app.airecruit.com/settings/subscription
2. 暂停 30 天: 上述页面, 暂停后数据保留
3. 导出数据: https://app.airecruit.com/settings/privacy (JSON 格式)

{{ if health_score >= 70 }}
🎁 健康度高 (≥ 70), 续订额外送 1 个月 (限 D+17 前)
{{ endif }}
{{ endif }}

无论您的选择是什么, 我们都期待听到您的反馈。

5 分钟问卷: https://airecruit.com/nps-survey?pilot={{ pilot_id }}

{{ csm_name }}
```

**触发**: D+14 18:00 (下班前)

---

## 实施细节

### 邮件服务商
- **国内 (推荐)**: 阿里云邮件推送 (DirectMail), 0.001 元/封
- **海外**: Mailchimp, 免 2000 联系人
- **自建**: 难, 不推荐

### 触发方式
- **Mailchimp Customer Journey**: 拖拽式, 5 步 5 封
- **DirectMail**: 模板 + cron 触发 (与我们的 onboarding-touch-cadence.py 集成)
- **SendGrid**: 类似 Mailchimp

### 变量替换
- `{{ first_name }}`: 联系人 first_name (注册时收集)
- `{{ csm_name }}`: 客户经理 (sales 用户表)
- `{{ meeting_time/url }}`: Calendly 链接
- `{{ jd_count }}` 等: API 实时拉 (启动 cron 拉 + 嵌入)

### 退订
- 邮件底部必须含"退订"链接 (PIPL 强制)
- 退订后该 contact 不再发 drip, 但 30 天续订通知除外 (重要信息)

### 配合触达通道
- D+1: in-app + 微信模板
- D+3: in-app + 微信模板 + 邮件
- D+7: in-app + 微信模板 + 邮件 + 短信
- D+11: in-app + 微信模板 + 邮件 + 短信
- D+14: in-app + 微信模板 + 邮件 + 短信

**目标**: 任一通道送达率 ≥ 95%, 总体 ≥ 99%。

---

**维护**: marketing@airecruit.com
**最后更新**: 2026-06-06
