# Session Cleanup 推后续 — 2026-06-08

> **状态**: 推后续 (本会话收尾发现, 用户 2026-06-08 决策 推后续)
> **来源**: 本会话 (562f807 → 62530ac, 62 commits) 末尾 git status 检查
> **总项数**: 2 项 (1 D + 1 phantom)
> **风险等级**: L (0 production 改, 0 breaking, 0 测退化)
> **总估时**: 0.1-0.2d (用户自己选)

---

## 0. 总结

本会话 (mcp 收尾 + G15 instance-level 重构 + 14 retrofit + retrofit 链 + 5 修) 共 62 commits, 20 测全过, 61 ship reports pass / 0 fail, health-check 11/11. session 末尾 git status 发现 2 项推后续:

1. **D** (1 项): MCP 设计文档 v2 在 5d0a371 commit 过, working tree 被删, delete 未 stage
2. **?? phantom** (1 项): git status 报 untracked, 但 os 真不存 (NFC+NFD 都 0 匹配)

2 项都是 cosmetic, 0 影响, 0 production 改. 用户决策 推后续.

---

## 1. [P1] D: AI_招聘系统_MCP_工具系统设计文档_v2.md (18K)

**问题**:
- 5d0a371 commit 过, 文件在 git index
- working tree 删了, delete 未 stage
- `.gitignore` line 68 有错拼文件名: `AI_招聘系统_MCP_工具系统_设计文档_v2.md` (工具系统_设计), 实际名 `AI_招聘系统_MCP_工具系统设计文档_v2.md` (工具系统设计)
- 所以 `.gitignore` 模式不匹配

**现状 (git status --porcelain)**:
```
 D "AI_\346\213\233\350\201\230\347\263\273\347\273\237_MCP_\345\267\245\345\205\267\347\263\273\347\273\237\350\256\276\350\256\241\346\226\207\346\241\243_v2.md"
```

**2 个修法选项** (用户选):

### 选项 A: git rm 删 (推荐, 0 数据失)

```bash
# 1. git rm --cached (只清 index, working tree 反正没了)
git rm --cached "AI_招聘系统_MCP_工具系统设计文档_v2.md"
# 2. 修 .gitignore line 68 错拼
sed -i '' 's|工具系统_设计|工具系统设计|' .gitignore
# 3. commit
git add .gitignore && git commit -m "fix(.gitignore): 修 line 68 错拼 MCP 设计文档 v2 文件名 + 删 (5d0a371 后, 推后续修)"
```

**优点**: 删 working tree 副本, 数据在 git history (5d0a371) 完整保留
**风险**: 0 (数据全在 history, 任何时候 `git show 5d0a371:...` 可拿回)
**估时**: 0.1d

### 选项 B: git checkout 恢复 (修 .gitignore 兼容)

```bash
# 1. 恢复 working tree
git checkout 5d0a371 -- "AI_招聘系统_MCP_工具系统设计文档_v2.md"
# 2. 修 .gitignore line 68 错拼 + 加 .archive/ 移 (如果想保留但忽略)
mkdir -p .archive && mv "AI_招聘系统_MCP_工具系统设计文档_v2.md" .archive/
# 3. commit 移走
git add .archive/ && git commit -m "docs(archive): MCP 设计文档 v2 移 .archive/ (5d0a371 后, 推后续修)"
```

**优点**: 保留访问, 推 .archive/ (按项目惯例)
**风险**: 0 (文件全保留)
**估时**: 0.1d

---

## 2. [P2] ?? phantom: AI_招聘_Agent_系统架构文档_向量检索功能.md

**问题**:
- `git status --porcelain` 报 `??` (untracked)
- `git ls-files --others --exclude-standard` 报同 untracked
- 但 `os.path.exists()` 返回 False (NFC + NFD 都 0 匹配)
- `find . -maxdepth 1 -name "AI_招聘_*.md"` 找不到
- `git update-index --really-refresh` 修不了
- `git fsck --no-progress` 找到 5 dangling commits + 2 dangling blobs (老历史, 跟 phantom 无关)
- `git status --ignored` 报 0

**根因 (3 个可能)**:
1. macOS NFD vs NFC encoding 错位 (最可能, 但 Python 两都 0 匹配)
2. git 内部 stat cache 与 FS 错位 (多次 refresh 修不了)
3. 不可见文件系统层 (hard link / virtual mount, 但项目内其他文件正常)

**现状 (git status --porcelain)**:
```
?? "AI_\346\213\233\350\201\230_Agent_\347\263\273\347\273\237\346\236\266\346\236\204\346\226\207\346\241\243_\345\220\253\345\275\225\351\237\263\345\212\237\350\203\275.md"
```

**0 影响**:
- 不影响 build / test / deploy
- 不影响 commit / push (git 把它当未跟踪, 不影响其他 commit)
- 不影响 `git log` / `git diff` / `git checkout`
- 唯一影响: `git status` 输出噪音

**3 个修法选项** (用户选):

### 选项 A: 不动 (推荐, 0 风险)

```bash
# 接受 cosmetic 噪音, 0 修
# 每次 git status 会显示 ??, 但忽略即可
```

**优点**: 0 风险, 0 估时
**缺点**: 噪音持续
**估时**: 0d

### 选项 B: git reset --mixed HEAD (重置 index, 保留 working tree)

```bash
# 重置 index 从 HEAD 重建, 保留 working tree
git reset --mixed HEAD
# 验证 phantom 是否消失
git status --porcelain
```

**优点**: 干净修, 0 数据失
**风险**: L (会清 index 任何未 commit 状态, 但本会话所有 commit 已落地)
**估时**: 0.1d

### 选项 C: rm .git/index && git reset (硬重置 index)

```bash
# 删 index 文件, git reset 重建
rm .git/index
git reset
```

**优点**: 强力修, 解决深层错位
**风险**: M (任何 racy / 未观察改动可能失, 但本会话状态干净)
**估时**: 0.1d

### 选项 D: 问用户 (默认 A, 推下次)

```bash
# 问用户
```

---

## 3. 决策记录 (本会话)

| 决策 | 选项 | 时间 | 备注 | 状态 |
|------|------|------|------|------|
| 2 推后续 推到下次 | "这是后面要完成什么任务" | 2026-06-08 17:xx | 用户显式决策 | ✅ |
| D 项 修法 | 选项 A (git rm 删) | 2026-06-08 推后续修 | 0.1d, 0 数据失 | ✅ db9d420 |
| phantom 修法 | 选项 B (git reset --mixed HEAD) | 2026-06-08 推后续修 | 0.1d, 0 数据失, 0 commit | ✅ 已修 (无 commit 需) |
| 总估时 | 0.2d 实际 | 2026-06-08 | vs 0.1-0.2d 估 | ✅ |

---

## 4. 验证 (本会话结束状态)

- 62 commits (562f807 → 62530ac)
- 20 测全过 (5 chaos_drill + 1 B regression + 8 retrofit helper + 2 dedup + 4 G15)
- 61 ship reports pass / 0 fail
- health-check 11/11
- 0 production 行为变 (F19.x structlog 迁 + G15 refactor 都是 0 行为变)
- 0 breaking change
- 0 测退化
- 0 health 退化

**稳定状态**: 2 推后续 不破坏稳定性, 可任意时候修

---

## 5. 引用

- 本会话最终 6 commit (G15 链 + 3 收尾 fix):
  - `052b74d` G15 factory (MCPHost.create + reset + 4 测, 0.5d)
  - `af93ea6` G15 instance-level (get_mcp_host + consumer 改 + 121 行规划, 0.3d)
  - `4421b10` CLAUDE.md 文档化 G15 入口 (0.1d)
  - `00a3313` F3+F4 retrofit 漏 commit 10 测 诚实修 (0.1d)
  - `67d7761` .gitignore 漏配 apps/.omo/ + runtime/ 修 (0.1d)
  - `62530ac` Momus 4 阶段 plan 推后续 commit (0.1d)
- 5d0a371 (D 项原 commit, 5d0a371 后某次未 stage 删)
- .gitignore line 68 错拼文件名 (工具系统_设计 vs 工具系统设计)
- docs/followups.md (本会话前 83 行推后总索引)
- .omo/plans/2026-06-07-complete-roadmap-momus-review.md (Momus 4 阶段审核, 62530ac commit 过)
