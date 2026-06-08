<!-- ship-report-template: g5-g8-v1 -->
# F4 Ship Report — Fix retrofit_ship_reports.py §7 renumbering bug (漏加 §8 + 重复 §9) + 14 文件修 (0.2d, momus v2 G18)

> 用户原请求"Retrofit 32 老 mcp-v4-v1.0a/b baseline 升到 66" — F2 (158fbd4) + F3 (2d13fa5) 修完 22 mcp-v4-v* + 0 fail. 本 F4 修 F retrofit (5a63512) 引入的隐性 bug: §7 renumbering 漏加 §8 + 产生重复 §9.
> Refs: `5a63512` (F retrofit, 引入 bug)
> Refs: `2d13fa5` (F3 retrofit, 发现 bug)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 1 脚本改 (retrofit_ship_reports.py 加 dedup + reorder) + 14 文件 dedup 跑 + 2 测加 | ✅ |
| 估时 | 0.2d 实际 (修 + 测 + re-run + 写 ship report) | ✅ 提前完 |
| 测试 | 2 dedup 测过 (含 reorder §7 < §8 < §9) + 8 retrofit helper 测过 + 6 测总过 | ✅ |
| 风险 | L (纯文档 + 脚本幂等, 0 production 改) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 14 dedup ✅ 2 测加 ✅ §9=1 全部 ✅ idempotency ✅ health ✅ 5 强约束 | 6 ✅ |

## 2. 背景

F retrofit (5a63512) ship 后, 14 老 followup-* ship report (F1+F2/F8/F18/F19.x/F20) retrofit 完成. 但实测发现:
- §7 引用 → §7 后续 改名 OK
- §8 回滚 节 加 OK (单独 step)
- §9 引用 节 加 OK (在 §7 后续 之后)
- **bug**: §7 后续 step 的 regex 没排除已存在 §8/§9 情况, 跑过 14 文件后产生重复 §9 节 (一个 from §7 renumbering, 一个 from 单独 §8/§9 step)

14 文件实际结构 (例 F1+F2) — §7 后续 + §9 旧 + §8 回滚 + §9 新 4 段乱序 (双重 §9, 顺序错位 §7→§9→§8→§9). G8 check 容忍 (§9 必填 "引用" 关键词 多个 OK), 但结构脏.

F3 retrofit (2d13fa5) 加 8 retrofit helper 测时, `test_retrofit_ship_reports_handles_7_section` 测 7-section 期望 §8 加 → 发现 §7 renumbering 漏加 §8 (单独 step 在 F retrofit commit 加的, 不在当前 script). 进一步发现 14 文件有重复 §9.

## 3. 修法 (3 子项)

| 子项 | 修法 | 文件 |
|---|---|---|
| Step 4: dedup §9 | 检测 §9 出现 2+ 次, 保留最后一个, 合并前面内容到末尾 | scripts/retrofit_ship_reports.py |
| Step 5: reorder §7/§8/§9 | 检测顺序错位 (§7 < §8 但 §8 > §9), 提取 + 重排 | 同上 |
| re-run 14 验证 | dedup 跑 13 (G16+G17 已合规跳过) | docs/followup-* (13 改) |

## 4. 测试

测试策略: mock dedup + reorder §8/§9 (subprocess 写临时文件) / 真 check_ship_report.py docs/ 跑 (验 0 fail) / 真 14 文件 grep §9=1 (验 dedup 实际生效)

| 测 | 输入 | 期望 | 结果 |
|---|---|---|---|
| 测 1: dedup §9 (2→1) | §7 后续 + §9 旧 + §8 回滚 + §9 新 | dedup 后 §9=1, 顺序 §7<§8<§9, old+new 内容都保留 | ✅ 2 passed |
| 测 2: idempotency dedup 后 | §7/§8/§9 都合规 (各 1) | 无变化 | ✅ 1 passed |
| 测 3: check_ship_report.py docs/ | 全 docs/ 扫 | 59 pass / 0 fail | ✅ |
| 测 4: 14 文件 grep §9=1 | 14 followup-* ship report | §7=1 §8=1 §9=1 (all 14) | ✅ 14/14 |
| 测 5: 5 chaos_drill + B regression + retrofit helpers 8 + retrofit dedup 2 | 16 测总 | 全过 | ✅ 16 passed |
| 测 6: health-check 11/11 | bash scripts/health-check.sh | 保持 | ✅ 11/11 |

**总: 16 测过 (5 retrofit helper + 2 dedup + 5 chaos_drill + 1 B regression + 3 总摘要)**

## 5. 退出门槛

- [x] retrofit_ship_reports.py 加 Step 4 (dedup) + Step 5 (reorder)
- [x] 14 文件 dedup 跑 (13 改 + 1 已合规)
- [x] §9=1 全部 14 文件
- [x] G8 check 59 pass / 0 fail (不退化)
- [x] 16 测全过
- [x] health-check 11/11 保持
- [x] 0 production code 改

## 6. 未在范围

- 无 (bug 修复 + dedup idempotency 全过, 0 fail)
- 后续可加更多 retrofit helper 测 (现 10 测覆盖核心函数, 未覆盖 edge case 如文件不存在 / 空文件)

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| F4 retrofit helper 测继续 | 0.1d | P3 | 现 10 测, 加 edge case 测 (空文件/不存在/权限) |
| Phase D 远期按 docs/phase-d-session-plan.md 11 session 计划 | - | - | - |

## 8. 回滚

rollback: git revert HEAD~1..HEAD + 17 文件 (1 脚本改 + 14 docs/ 重复 §9 修 + 2 测)

- 不破坏任何文件 (纯脚本 + 文档 dedup)
- 不影响 production code (0 改)
- 不需迁移步骤

## 9. 引用

- Refs: [G18 推后续](docs/mcp-v4-momus-audit-v2-2026-06-08.md)
- Refs: [G8 检查器](scripts/check_ship_report.py)
- Refs: [retrofit_ship_reports.py (本 PR 改)](scripts/retrofit_ship_reports.py)
- Refs: [F3 8 测](apps/api/tests/scripts/test_retrofit_helpers.py) 暴露 bug
- Refs: [F4 2 测](apps/api/tests/scripts/test_retrofit_dedup_helpers.py) 防 regression
- Refs: `5a63512` (F retrofit, 引入 bug)
- Refs: `2d13fa5` (F3 retrofit, 测暴露 bug)
