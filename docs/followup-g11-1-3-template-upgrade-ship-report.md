<!-- ship-report-template: g5-g8-v1 -->
# G11-1/3 Ship Report — A6 check_ship_report.py 加 G5 长度 + G8 必填 (0.2d, momus v1 推后续)

> momus v2 (2026-06-08) §G11-1/3 = G5 (0.1d) + G8 (0.1d) momus v1 推后续
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G11 详细)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 1 文件改 (scripts/check_ship_report.py) + 1 文件新建 (本 report) | ✅ |
| 估时 | 0.2d 实际 | ✅ |
| 测试 | 11 老 mcp-v4-v1.4 pass + 2 合成测 (1 good pass / 1 bad G5 抓到) | ✅ |
| 风险 | L (lint 检查, 不影响 production) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 1 文件改 ✅ 2 合成测 ✅ grandfather ✅ marker opt-in ✅ health 11/11 ✅ 5 强约束 | 6 ✅ |

## 2. 背景

Momus v1 (0c2a8fa) 推后续 3 项没接 (G5 + G7 + G8), 整合到 v2 G11 (P1, 0.5d 总). 本 PR 是 G11-1/3 = G5 + G8 (0.2d), 剩 G7 (0.3d 防御 check 升级) 推 G11-2/3.

- **G5 (0.1d)**: A6 check_ship_report.py 加长度限制 ≤30 行/章节, 防 ship report 膨胀
- **G8 (0.1d)**: ship report 模板加 2 行 — "测试策略: mock X / 真 Y" + "rollback: git revert + N 文件"

## 3. 修法

| 子项 | 修法 | 文件 |
|---|---|---|
| G5 长度检查 | `MAX_SECTION_LINES = 30` + 9 章节长度扫 | scripts/check_ship_report.py |
| G8 §4 必填 | `SECTION_4_REQUIRED_PATTERN = re.compile(r"测试策略[:：].*?(?:mock\|真)")` | 同上 |
| G8 §8 必填 | `SECTION_8_REQUIRED_PATTERN = re.compile(r"rollback[:：].*?git revert")` | 同上 |
| 名称 pattern 扩 | `NAME_PATTERN` 加 `followup-` 分支 (新 ship report 命名) | 同上 |
| Grandfather | 老 mcp-v4-v* 跳过 G5/G8 (mcp-v4-v* 已大改不可能 retrofit) | 同上 |
| Marker opt-in | `STRICT_MARKER = "<!-- ship-report-template: g5-g8-v1 -->"` 在新 report 首行启用强制 | 同上 |
| 14 老 followup-* grandfather | 无 marker → 不强制 G5/G8 (避免 retrofit 14 老 report 0.5d+) | 同上 |

## 4. 测试

测试策略: mock 检查器 (in-process `check_ship_report()` 函数调用) / 真 docs/ 扫 (命令行 `python3 scripts/check_ship_report.py docs/`)

| 测 | 输入 | 期望 | 结果 |
|---|---|---|---|
| 测 1 | mcp-v4-v1.4-a1 到 b6 (11 老) | pass (grandfather) | ✅ 11 pass |
| 测 2 | 合成含 marker + 全合规 | pass | ✅ pass |
| 测 3 | 合成含 marker + §3 35 行 | fail (G5 抓到) | ✅ fail "§3 36 行 > 30" |
| 测 4 | mcp-v4-v1.0a/v1.0b (pre-5 强约束) | fail (5 强约束缺) | 36 fail (独立问题, 非本 PR) |
| 测 5 | 14 老 followup-* (无 marker) | pass (grandfather) | ✅ 14 pass |

## 5. 退出门槛

- [x] G5 长度检查加进 checker (MAX_SECTION_LINES = 30)
- [x] G8 §4 测试策略必填
- [x] G8 §8 rollback 必填
- [x] NAME_PATTERN 扩到 followup-*
- [x] grandfather 机制 (老 mcp-v4-v* + 14 老 followup-*)
- [x] marker opt-in 启用
- [x] 合成测 1 pass + 1 fail 验证
- [x] health-check 11/11

## 6. 未在范围

- G11-2/3 (G7 防御 check 升级, 0.3d) — 推 G11-2/3 PR
- 36 老 mcp-v4-v1.0a/v1.0b 5 强约束 retrofit — 推独立 PR (估时 0.5-1d)
- 14 老 followup-* retrofit (如需) — marker opt-in 已 grandfather, 不需 retrofit
- §3 修法章节 ≤ 30 行的内容裁剪 — 新模板 (本 report) 遵守, 老 report 不强制

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| G11-2/3 (G7 防御 check 升级) | 0.3d | P1 | momus v1 推后续, 推 G11-2/3 PR |
| 36 老 mcp-v4-v1.0a/v1.0b 5 强约束 retrofit | 0.5-1d | P3 | pre-5 强约束 era, 非阻塞 |
| G12 F21 drill (Phase C 收尾) | 1d | P1 | momus v2 G12 |
| G13 F11-F14 retro-fit 4 项 | 1.6d | P1 | momus v2 G13 |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 个 commit, 1 文件 check_ship_report.py 改回)

- 不破坏任何老 ship report (grandfather + marker 双向保护)
- 不影响 production code (纯 lint 工具)
- 不需迁移步骤

## 9. 引用

- Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G11 §G5+G8 详细)
- Refs: `docs/mcp-v4-momus-audit-2026-06-08.md` (momus v1 §G5+G8 原始建议)
- Refs: `4e99d30` (momus v2 ship, 推后续起点)
- Refs: `e553fb2` (G16+G17 docs ship, 本 PR 前一 commit)
- Refs: `scripts/check_ship_report.py` (A6 原始 9 章节 + 5 强约束检查)
