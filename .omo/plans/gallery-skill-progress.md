# Gallery SKILL.md 安装器 - 开发进度

## 完成状态：✅ 主体完成，待测试

## 做了什么

### 1. 架构决策
采用**折中方案**（Hermes 轻量版）：
- SKILL.md 解析后生成**受限 Python handler**（不是通用 bash 工具）
- LLM 只能执行 SKILL.md 里写过的命令（安全边界）
- 内存注册 + 持久化到 `_gallery/<name>/SKILL.md`

### 2. 删除了什么
- `apps/api/app/skills/skill_gallery_installer.py`（冗余，gallery.py 已实现）
- `apps/api/app/skills/_gallery/github_issues/`（测试产物）

### 3. 改造了 `gallery.py`

**新功能**：
- `install_gallery_skill_from_url/path/content` → 安装 SKILL.md
- `_restore_from_disk()` → 启动时自动恢复注册
- 解析 frontmatter + bash 命令块
- 生成受限 handler 并注册到 `_gallery_tools` / `_gallery_handlers`

**流程**：
```
安装：SKILL.md → 解析 → 注册内存 → 保存 _gallery/<name>/SKILL.md
启动：扫描 _gallery/*/SKILL.md → 重新解析 + 注册
```

### 4. 清理了 `agent_service.py`
- 移除 `skill_gallery_installer` 引用
- 统一走 `gallery.py`

## 验证结果
- ✅ 解析 + 注册成功
- ✅ handler 执行 bash 命令正常
- ✅ 持久化到 `_gallery/<name>/SKILL.md`
- ✅ 重启后从磁盘恢复
- ✅ agent_service.py 引用正确

## 待完成

### 高优先级
1. **真实 SKILL.md 测试**：用真实的 Hermes github-issues SKILL.md 完整测试安装流程
2. **LLM 对话测试**：通过 agent_service 完整对话测试，LLM 能否调用生成的工具
3. **`list_gallery_skills` 工具**：目前只返回工具列表，缺少 skill 维度的信息

### 中优先级
4. **工具参数支持**：当前 handler 不接受参数，但 SKILL.md 里命令可能有变量（如 `gh issue list --repo=$REPO`）
5. **错误处理增强**：subprocess 超时、gh not found 等情况的用户体验
6. **安全验证**：危险模式检测是否足够

### 低优先级
7. **cleanup 工具**：卸载 gallery skill（从内存注销 + 删除文件）
8. **`load_skill` 整合**：Gallery skill 是否也应该通过 `load_skill` 工具暴露给 LLM？

## 文件清单

### 修改的文件
- `apps/api/app/skills/gallery.py`（重写）
- `apps/api/app/services/agent_service.py`（清理引用）

### 删除的文件
- `apps/api/app/skills/skill_gallery_installer.py`
- `apps/api/app/skills/_gallery/github_issues/`（整个目录）

### 新增文件
- `apps/api/app/skills/gallery.py`

## 技术细节

### SKILL.md 解析
- frontmatter 用 yaml 解析（需要 `name` 字段）
- body 按 `## 标题` 分割 action
- 每个 action 的代码块里找 `gh ` 或 `curl ` 命令

### handler 生成
- 生成 Python 函数字符串
- 用 `exec()` 执行到全局命名空间
- 危险模式检测：`__import__`, `os.system`, `os.popen`, `shutil.rmtree`, `eval`, `exec(`

### 启动恢复
- 模块首次导入时 `_restore_from_disk()` 自动执行
- 扫描 `_gallery/*/SKILL.md`，逐个解析 + 注册
