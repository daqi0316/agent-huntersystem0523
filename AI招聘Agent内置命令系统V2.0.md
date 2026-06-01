# AI招聘Agent 内置命令系统 V2.0

> 版本: 2.0 | 更新: 2026-06-01 | 适用: AI招聘Agent全场景

---

## 一、命令体系总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI招聘Agent 内置命令体系                               │
├──────────────┬──────────────┬──────────────┬──────────────┬─────────────────┤
│  任务控制     │  对话管理     │  数据CRUD    │  系统操作     │   快捷操作       │
├──────────────┼──────────────┼──────────────┼──────────────┼─────────────────┤
│ /restart     │ /new         │ /read        │ /help        │ / (唤起面板)     │
│ /pause       │ /history     │ /write       │ /status      │ // (自然语言)    │
│ /resume      │ /switch      │ /delete      │ /settings    │ /r /p /s /h /n   │
│ /cancel      │ /back        │ /add         │ /debug       │                  │
│ /retry       │ /clear       │ /update      │ /export      │                  │
│ /rollback    │ /merge       │ /list        │ /import      │                  │
│ /snapshot    │ /fork        │ /search      │ /version     │                  │
│ /checkpoint  │ /diff        │ /batch       │ /config      │                  │
└──────────────┴──────────────┴──────────────┴──────────────┴─────────────────┘
```

### 命令命名规范
- 所有命令以 `/` 开头，不区分大小写
- 支持参数: `/command arg1 arg2 --flag=value`
- 支持管道: `/list candidates | /filter score>80`
- 快捷别名: `/r` = `/restart`, `/p` = `/pause`

---

## 二、任务控制命令（Task Control）

### `/restart` — 重启当前任务

**作用**：从头重新开始当前招聘任务，清除所有状态，保留历史快照

**语法**：
```
/restart                    # 基础重启
/restart --save             # 保存快照后重启（默认）
/restart --force            # 强制重启，不保存快照
/restart --template <id>    # 基于模板重启
```

**使用场景**：
- 用户觉得 AI 理解错了需求，想重新开始
- 任务执行到一半发现方向不对
- 测试不同招聘策略
- 基于历史成功案例模板快速重启

**交互示例**：
```
用户: /restart

AI:
⚠️ 确认重启任务？

当前任务: 招聘 Java 后端工程师 (task_20250601_001)
已执行: 发布职位 → 收到15份简历 → 解析完成 → 筛选中

重启后将清除所有进度，是否继续？

[确认重启] [保存快照后重启] [取消]

用户: 确认重启

AI:
✅ 任务已重启 (task_20250601_002)

新任务 ID: task_20250601_002
旧任务快照已保存: snap_20250601_001_v8
父任务: task_20250601_001

请描述您的招聘需求:
```

**实现逻辑**：
```typescript
async function handleRestart(
  sessionId: string, 
  options: RestartOptions = { saveSnapshot: true }
): Promise<CommandResult> {
  // 1. 获取当前任务
  const currentTask = await getCurrentTask(sessionId);

  // 2. 保存最终快照（可选）
  if (options.saveSnapshot) {
    await createSnapshot(currentTask.task_id, {
      reason: 'user_restart',
      final_state: currentTask.state,
      timestamp: new Date()
    });
  }

  // 3. 标记旧任务为 cancelled
  await updateTaskStatus(currentTask.task_id, 'cancelled');

  // 4. 创建新任务（关联旧任务）
  const newTask = await createTask({
    user_id: currentTask.user_id,
    parent_task_id: currentTask.task_id,
    template_id: options.templateId,
    status: 'running'
  });

  // 5. 重置会话上下文
  await resetSessionContext(sessionId, newTask.task_id);

  // 6. 返回新任务信息
  return {
    success: true,
    new_task_id: newTask.task_id,
    old_snapshot_id: currentTask.last_snapshot_id,
    message: '任务已重启'
  };
}
```

---

### `/pause` — 暂停当前任务

**作用**：暂停任务执行，保存当前状态，稍后恢复

**语法**：
```
/pause                      # 暂停当前任务
/pause --reason "说明"      # 带原因暂停
/pause --duration 2h        # 定时自动恢复
```

**使用场景**：
- 用户临时离开，不想丢失进度
- 需要人工确认某些信息
- 系统维护
- 非工作时间自动暂停

**交互示例**：
```
用户: /pause --reason "等HR确认预算"

AI:
⏸️ 任务已暂停 (task_20250601_001)

暂停原因: 等HR确认预算
当前状态: 筛选中 (已解析12份简历，3份待确认)
快照 ID: snap_20250601_001_v6

恢复方式:
- 发送 /resume 继续
- 或稍后重新进入对话自动恢复

⏰ 快照保留 7 天，过期后自动清理
```

---

### `/resume` — 恢复暂停的任务

**作用**：从暂停状态恢复任务执行

**语法**：
```
/resume                     # 恢复最近暂停的任务
/resume <task_id>           # 恢复指定任务
/resume --from <snapshot>   # 从指定快照恢复
```

**交互示例**：
```
用户: /resume

AI:
▶️ 恢复任务 (task_20250601_001)

从快照恢复: snap_20250601_001_v6
恢复节点: screening (筛选中)
暂停时长: 2小时15分钟

继续执行...
✅ 已恢复，当前进度: 筛选中 (3份简历待确认)

[查看待筛选队列] [继续筛选] [跳过此步骤]
```

**实现逻辑**：
```typescript
async function handleResume(
  sessionId: string, 
  taskId?: string,
  snapshotId?: string
): Promise<CommandResult> {
  // 1. 查找可恢复的任务
  const task = taskId 
    ? await getTaskById(taskId)
    : await getLastPausedTask(sessionId);

  if (!task) {
    return { error: '没有找到可恢复的任务' };
  }

  // 2. 从指定快照或最新快照恢复状态
  const snapshot = snapshotId 
    ? await getSnapshotById(snapshotId)
    : await getLatestSnapshot(task.task_id);

  const restoredState = await restoreFromSnapshot(snapshot.snapshot_id);

  // 3. 更新任务状态
  await updateTaskStatus(task.task_id, 'running');

  // 4. 恢复 LangGraph 执行
  await resumeLangGraph(task.task_id, restoredState);

  return {
    task_id: task.task_id,
    restored_from: snapshot.snapshot_id,
    current_node: restoredState.current_node,
    paused_duration: calculatePausedDuration(task),
    message: '任务已恢复'
  };
}
```

---

### `/cancel` — 取消当前任务

**作用**：终止任务，保存最终快照

**语法**：
```
/cancel                     # 取消当前任务
/cancel --archive           # 取消并归档
/cancel --delete            # 取消并删除（不可逆）
```

**交互示例**：
```
用户: /cancel

AI:
⚠️ 确认取消任务？

当前任务: 招聘 Java 后端工程师
进度: 筛选中 (已解析12份简历)

取消后:
- 所有进度将保存为快照
- 可随时通过 /resume 恢复
- 或从历史任务中查看

[确认取消] [保存并归档] [继续执行]
```

---

### `/retry` — 重试当前步骤

**作用**：重新执行当前失败的步骤

**语法**：
```
/retry                      # 重试当前步骤
/retry --strategy auto      # 自动选择策略
/retry --strategy manual    # 手动指定参数
/retry --max-attempts 3     # 最大重试次数
```

**交互示例**：
```
用户: /retry --strategy auto

AI:
🔄 重试当前步骤

步骤: 安排面试 (interview)
上次失败: 面试官日历冲突
失败时间: 2025-06-01 10:30

重试策略:
1. 自动选择其他时间段
2. 更换面试官
3. 手动指定

[自动重试] [选择策略] [跳过此步骤]

AI: 正在自动重试...
✅ 面试已安排: 2025-06-03 14:00
面试官: 王经理
会议室: A-301
```

---

### `/rollback {n}` — 回溯到历史版本

**作用**：回退到任务的某个历史状态

**语法**：
```
/rollback 3                 # 回溯到第3个版本
/rollback --to <snapshot>   # 回溯到指定快照
/rollback --preview         # 预览回溯结果（不执行）
```

**交互示例**：
```
用户: /rollback 3

AI:
⏪ 回溯到版本 3

版本历史:
[v8] 当前 - 筛选中 (3份待确认)
[v7] 2025-06-01 10:30 - 解析完成
[v6] 2025-06-01 10:25 - 解析中
[v5] 2025-06-01 10:20 - 寻访中 ⬅️ 目标版本
[v4] 2025-06-01 10:15 - 职位已发布
[v3] 2025-06-01 10:10 - 任务创建
[v2] 2025-06-01 10:05 - 意图识别
[v1] 2025-06-01 10:00 - 开始

回溯到 v5 将:
- 保留 v1-v5 的历史
- 从 v5 创建新分支 (v9)
- v6-v8 仍保留在原始分支

[确认回溯] [查看 v5 详情] [取消]
```

---

### `/snapshot` — 手动创建快照

**作用**：立即保存当前任务状态

**语法**：
```
/snapshot                   # 创建快照
/snapshot --name "描述"     # 带名称的快照
/snapshot --tag important   # 带标签的快照
```

**交互示例**：
```
用户: /snapshot --name "筛选完成待面试" --tag important

AI:
📸 快照已创建

快照 ID: snap_20250601_001_v9
名称: 筛选完成待面试
标签: important
任务: 招聘 Java 后端工程师
节点: 筛选中
时间: 2025-06-01 10:35:00

快照内容:
- 已解析简历: 12份
- 匹配通过: 5份
- 待确认: 3份
- 已拒绝: 4份

此快照可用于:
- 稍后恢复 (/resume)
- 回溯 (/rollback)
- 对比分析 (/diff)
```

---

### `/checkpoint` — 创建检查点（轻量快照）

**作用**：创建轻量级检查点，用于快速回退

**语法**：
```
/checkpoint                 # 创建检查点
/checkpoint --auto          # 开启自动检查点（每步自动创建）
```

> 与 `/snapshot` 区别：`/checkpoint` 更轻量，仅保存关键状态，不保存完整对话历史

---

## 三、对话管理命令（Dialog Management）

### `/new` — 开启新对话

**作用**：结束当前对话，开始全新的独立对话

**语法**：
```
/new                        # 开启新对话
/new --copy-context         # 复制当前上下文到新对话
/new --template <id>        # 基于模板创建
```

**交互示例**：
```
用户: /new

AI:
🆕 新对话已创建

旧对话: session_20250601_001
  - 任务状态: 已保存 (task_20250601_001)
  - 可随时恢复: /resume task_20250601_001

新对话: session_20250601_002
  - 无关联任务
  - 开始新的招聘流程

请描述您的需求:
```

---

### `/history` — 查看对话历史

**作用**：查看当前对话的历史消息和任务流转

**语法**：
```
/history                    # 查看最近20条
/history --all              # 查看全部历史
/history --filter agent     # 按Agent过滤
/history --export json      # 导出为JSON
```

**交互示例**：
```
用户: /history

AI:
📜 对话历史 (session_20250601_001)

[10:00] 用户: 帮我招一个 Java 后端
[10:00] AI: 好的，请提供具体要求...
[10:01] 用户: 5年经验，北京，40-60k
[10:01] AI: 已创建任务 task_20250601_001
[10:02] AI: 职位已发布到 Boss直聘、脉脉
[10:05] AI: 收到15份简历，开始解析...
[10:10] AI: 解析完成，12份有效
[10:15] AI: 筛选中，5份匹配度>80%
[10:20] AI: [等待确认] 是否安排面试？
[10:25] 用户: /pause
[10:25] AI: 任务已暂停
[10:35] 用户: /resume
[10:35] AI: 任务已恢复

任务流转图:
start → intent → sourcing → resume_parser → screening → [paused] → [resumed]

[查看完整日志] [导出历史] [回溯到某一步]
```

---

### `/switch {agent}` — 切换到指定 Agent

**作用**：强制切换到某个 Agent 执行任务

**语法**：
```
/switch screening           # 切换到筛选Agent
/switch --list              # 列出所有可用Agent
/switch --auto              # 自动选择最佳Agent
```

**交互示例**：
```
用户: /switch screening

AI:
🔄 切换到 筛选 Agent

当前: 编排层 (Orchestrator)
目标: 筛选 Agent (Screening)

上下文:
- 任务: task_20250601_001
- 当前候选人: cand_001, cand_002, cand_003
- 职位: job_001 (Java 后端)

筛选 Agent 已激活，可用命令:
- match_candidate {candidate_id} - 分析匹配度
- screen_candidate {candidate_id} - 执行初筛
- get_screening_queue - 查看待筛选队列

请指示:
```

---

### `/back` — 返回上一步

**作用**：回退到上一个执行节点

**语法**：
```
/back                       # 返回上一步
/back --to <node>           # 返回到指定节点
/back --keep-data           # 保留当前数据返回
```

---

### `/clear` — 清空当前对话上下文

**作用**：清除对话历史，但保留任务状态

**语法**：
```
/clear                      # 清空对话
/clear --all                # 清空所有（包括任务状态）
/clear --soft               # 软清空（可恢复）
```

**交互示例**：
```
用户: /clear

AI:
🧹 对话上下文已清空

保留:
- 任务状态: task_20250601_001 (筛选中)
- 快照历史: v1-v9

清除:
- 对话消息历史
- 临时变量
- 缓存数据

新对话将基于当前任务状态继续
```

---

### `/merge` — 合并对话上下文

**作用**：将其他对话的上下文合并到当前对话

**语法**：
```
/merge <session_id>         # 合并指定会话
/merge --all-tasks          # 合并所有任务上下文
```

> **新增命令**：解决多会话数据孤岛问题

---

### `/fork` — 分叉对话（创建并行分支）

**作用**：基于当前状态创建并行对话分支

**语法**：
```
/fork --name "分支A"        # 创建命名分支
/fork --strategy A/B        # 创建A/B测试分支
```

> **新增命令**：支持并行测试不同招聘策略

---

### `/diff` — 对比不同版本/分支

**作用**：对比两个快照或分支的差异

**语法**：
```
/diff v5 v8                 # 对比版本5和8
/diff --branches            # 对比所有分支
```

> **新增命令**：便于追踪变更和决策依据

---

## 四、数据CRUD命令（核心新增）

> 这是V2.0的核心增强，提供对招聘数据的直接读写删改能力

### 4.1 读取命令（Read）

#### `/read` — 读取数据

**作用**：读取系统中的各类数据

**语法**：
```
/read <resource> <id>       # 读取指定资源
/read candidate cand_001    # 读取候选人信息
/read job job_001           # 读取职位信息
/read task task_001         # 读取任务信息
/read resume <id>           # 读取简历内容
/read interview <id>        # 读取面试记录
/read settings              # 读取系统设置
```

**参数**：
```
--format json|markdown|table  # 输出格式
--fields field1,field2       # 指定字段
--depth 1|2|3                # 关联深度
```

**交互示例**：
```
用户: /read candidate cand_003 --format markdown

AI:
📋 候选人详情 (cand_003)

┌─────────────────────────────────────────┐
│ 基本信息                                │
├─────────────────────────────────────────┤
│ 姓名: 张三                              │
│ 电话: 138****5678                       │
│ 邮箱: zhangsan@email.com                │
│ 当前状态: 筛选通过                      │
│ 匹配度: 87%                             │
├─────────────────────────────────────────┤
│ 简历摘要                                │
├─────────────────────────────────────────┤
│ 5年Java后端经验，熟悉Spring Cloud...    │
├─────────────────────────────────────────┤
│ 技能标签                                │
├─────────────────────────────────────────┤
│ Java, Spring Boot, MySQL, Redis, K8s   │
├─────────────────────────────────────────┤
│ 面试记录                                │
├─────────────────────────────────────────┤
│ 暂无                                    │
└─────────────────────────────────────────┘

[编辑] [删除] [安排面试] [发送通知]
```

---

#### `/list` — 列出数据列表

**作用**：列出系统中的数据列表

**语法**：
```
/list candidates            # 列出所有候选人
/list jobs                  # 列出所有职位
/list tasks                 # 列出所有任务
/list snapshots             # 列出所有快照
/list agents                # 列出所有Agent
```

**过滤与排序**：
```
/list candidates --status active      # 按状态过滤
/list candidates --sort score:desc    # 按分数降序
/list candidates --limit 10 --offset 0 # 分页
/list candidates --filter "score>80 AND status='screened'" # 复合过滤
```

**交互示例**：
```
用户: /list candidates --status active --sort score:desc --limit 5

AI:
📊 候选人列表 (共12人，显示前5)

┌──────┬────────┬────────┬────────┬──────────┬──────────┐
│ ID   │ 姓名   │ 匹配度 │ 状态   │ 更新时间 │ 操作     │
├──────┼────────┼────────┼────────┼──────────┼──────────┤
│ c003 │ 张三   │ 92%    │ 已通过 │ 10:35    │ [查看]   │
│ c007 │ 李四   │ 89%    │ 待面试 │ 10:30    │ [查看]   │
│ c001 │ 王五   │ 87%    │ 筛选中 │ 10:25    │ [查看]   │
│ c009 │ 赵六   │ 85%    │ 已联系 │ 10:20    │ [查看]   │
│ c012 │ 孙七   │ 82%    │ 新简历 │ 10:15    │ [查看]   │
└──────┴────────┴────────┴────────┴──────────┴──────────┘

[上一页] [下一页] [导出] [批量操作]
```

---

#### `/search` — 搜索数据

**作用**：全文搜索系统中的数据

**语法**：
```
/search "Java 5年经验"      # 全文搜索
/search --type candidate    # 限定资源类型
/search --fuzzy             # 模糊搜索
/search --semantic          # 语义搜索（向量匹配）
```

**交互示例**：
```
用户: /search "熟悉微服务架构" --type candidate --semantic

AI:
🔍 搜索结果 (语义匹配)

找到 3 个相关候选人:

1. 张三 (cand_003) - 相似度: 0.92
   技能: Spring Cloud, Docker, K8s...

2. 李四 (cand_007) - 相似度: 0.85
   技能: 微服务, Dubbo, Nacos...

3. 王五 (cand_001) - 相似度: 0.78
   技能: Spring Boot, 分布式系统...

[查看详情] [加入筛选队列] [批量操作]
```

---

### 4.2 写入命令（Write）

#### `/write` — 写入/更新数据

**作用**：创建或更新系统中的数据

**语法**：
```
/write <resource> <id> <data>   # 写入数据
/write candidate cand_003 '{"status": "interview_scheduled"}'
/write job job_001 --file job.json
/write settings --key model --value "gpt-4"
```

**交互模式**：
```
用户: /write candidate cand_003

AI:
✏️ 编辑候选人 (cand_003)

当前数据:
{
  "name": "张三",
  "status": "screened",
  "score": 87
}

请输入要修改的字段 (JSON格式):
或说 "交互模式" 进行问答式编辑

用户: {"status": "interview_scheduled", "interview_time": "2025-06-03 14:00"}

AI:
✅ 数据已更新

变更记录:
- status: screened → interview_scheduled
- interview_time: null → 2025-06-03 14:00

已自动创建快照: snap_20250601_001_v10
```

---

#### `/add` — 添加新数据

**作用**：向系统中添加新数据

**语法**：
```
/add candidate              # 添加候选人
/add job                    # 添加职位
/add note                   # 添加备注
/add tag                    # 添加标签
/add template               # 添加模板
```

**交互示例**：
```
用户: /add candidate

AI:
➕ 添加新候选人

请提供候选人信息:
1. 姓名: 
2. 电话: 
3. 邮箱: 
4. 简历链接/内容: 
5. 应聘职位: 

或上传简历文件，我将自动解析

用户: 上传 resume_zhangsan.pdf

AI:
📄 简历解析完成

提取信息:
- 姓名: 张三
- 电话: 138****5678
- 邮箱: zhangsan@email.com
- 工作年限: 5年
- 技能: Java, Spring Boot, MySQL...

确认添加？ [确认] [编辑] [取消]

用户: 确认

AI:
✅ 候选人已添加 (cand_013)

已自动:
- 解析简历
- 计算匹配度: 85%
- 添加标签: Java, 5年经验
- 加入筛选队列
```

---

### 4.3 删除命令（Delete）

#### `/delete` — 删除数据

**作用**：删除系统中的数据

**语法**：
```
/delete candidate cand_003  # 删除候选人
/delete job job_001         # 删除职位
/delete snapshot snap_001   # 删除快照
/delete --force             # 强制删除（不确认）
```

**安全机制**：
```
用户: /delete candidate cand_003

AI:
⚠️ 确认删除？

即将删除: 候选人 张三 (cand_003)
关联数据:
- 简历: 1份
- 面试记录: 0条
- 备注: 2条

删除后:
- 数据将移至回收站（保留30天）
- 可随时恢复
- 关联任务不受影响

[确认删除] [移至回收站] [取消]

用户: 确认删除

AI:
🗑️ 已删除 (cand_003)

数据已移至回收站
恢复命令: /restore candidate cand_003
```

---

### 4.4 批量操作命令（Batch）

#### `/batch` — 批量操作

**作用**：对多条数据执行批量操作

**语法**：
```
/batch --action update --target candidates --filter "status='new'" --data "{"status": "screened"}"
/batch --action delete --target candidates --ids c001,c002,c003
/batch --action export --target candidates --format csv
```

**交互示例**：
```
用户: /batch --action update --target candidates --filter "score>80" --data "{"priority": "high"}"

AI:
📦 批量操作

操作: 更新
目标: 候选人
过滤条件: score > 80
影响数量: 5人
更新内容: priority = "high"

确认执行？ [确认] [预览] [取消]

用户: 确认

AI:
✅ 批量更新完成

成功: 5/5
失败: 0

已更新候选人:
- cand_003 (张三)
- cand_007 (李四)
- cand_001 (王五)
- cand_009 (赵六)
- cand_012 (孙七)

已自动创建快照记录变更
```

---

### 4.5 数据操作汇总表

| 命令 | 作用 | 示例 | 安全级别 |
|------|------|------|----------|
| `/read` | 读取数据 | `/read candidate c001` | 只读 |
| `/list` | 列出数据 | `/list candidates --limit 10` | 只读 |
| `/search` | 搜索数据 | `/search "Java" --semantic` | 只读 |
| `/write` | 更新数据 | `/write candidate c001 '{"status":"x"}'` | 需确认 |
| `/add` | 添加数据 | `/add candidate` | 需确认 |
| `/delete` | 删除数据 | `/delete candidate c001` | 需确认+回收站 |
| `/batch` | 批量操作 | `/batch --action update ...` | 需确认+预览 |

---

## 五、系统操作命令（System Operations）

### `/help` — 查看所有命令

**语法**：
```
/help                       # 查看所有命令
/help <command>             # 查看指定命令详情
/help --category task       # 按分类查看
```

**交互示例**：
```
用户: /help

AI:
📖 招聘 Agent 内置命令

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 任务控制
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /restart          重启当前任务 (保存快照后可恢复)
  /pause            暂停任务，保存状态
  /resume           恢复暂停的任务
  /cancel           取消任务，保存最终快照
  /retry            重试当前失败的步骤
  /rollback {n}     回溯到第 n 个版本
  /snapshot         手动创建状态快照
  /checkpoint       创建轻量检查点

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 对话管理
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /new              开启新对话
  /history          查看对话历史
  /switch {agent}   切换到指定 Agent
  /back             返回上一步
  /clear            清空对话上下文
  /merge            合并对话上下文
  /fork             分叉对话（并行分支）
  /diff             对比版本差异

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 数据CRUD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /read             读取数据
  /list             列出数据列表
  /search           搜索数据
  /write            写入/更新数据
  /add              添加新数据
  /delete           删除数据
  /batch            批量操作

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ 系统操作
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /help             显示此帮助
  /status           查看当前任务状态
  /settings         查看/修改设置
  /debug            开启调试模式
  /export           导出任务数据
  /import           导入任务数据
  /version          查看系统版本
  /config           查看/修改配置

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ 快捷操作
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /                 快速唤起命令面板
  //                进入自然语言模式 (不解析命令)
  /r                /restart 快捷方式
  /p                /pause 快捷方式
  /s                /status 快捷方式
  /h                /help 快捷方式
  /n                /new 快捷方式
```

---

### `/status` — 查看当前任务状态

**语法**：
```
/status                     # 查看当前任务
/status --all               # 查看所有任务
/status --monitor           # 实时监控模式
```

**交互示例**：
```
用户: /status

AI:
📊 当前任务状态

任务 ID: task_20250601_001
类型: 招聘流程
状态: 🟢 运行中
当前 Agent: 筛选 Agent
当前节点: screening

进度:
  ✅ 职位发布 (100%)
  ✅ 简历收集 (15份)
  ✅ 简历解析 (12份有效)
  🔄 筛选评估 (5/12 完成)
  ⏳ 面试安排 (等待中)
  ⏳ 薪酬谈判 (未开始)
  ⏳ 入职跟进 (未开始)

当前操作:
  - 候选人: cand_003 (张三)
  - 匹配度: 87%
  - 状态: 待确认是否通过

快照: v9 (最新)
创建时间: 2025-06-01 10:00
已运行: 35分钟

[查看详情] [暂停] [取消] [创建快照]
```

---

### `/settings` — 查看/修改设置

**语法**：
```
/settings                   # 查看当前设置
/settings --edit            # 进入编辑模式
/settings --reset           # 恢复默认设置
```

**交互示例**：
```
用户: /settings

AI:
⚙️ 系统设置

当前设置:
  LLM 模型: DeepSeek V4 Flash
  确认模式: 敏感操作需确认
  通知方式: 站内信
  自动保存: 每步保存快照
  数据保留: 90天
  语言: 中文
  时区: Asia/Shanghai

可修改:
  [切换模型] [修改确认模式] [修改通知方式]
  [调整自动保存频率] [修改数据保留期]

[保存设置] [恢复默认] [取消]
```

---

### `/debug` — 开启调试模式

**语法**：
```
/debug                      # 开启/关闭调试模式
/debug --level verbose      # 设置调试级别
/debug --export             # 导出调试日志
```

**交互示例**：
```
用户: /debug

AI:
🐛 调试模式已开启

当前状态详情:
  Session: session_20250601_001
  Task: task_20250601_001
  Thread: thread_abc123
  Current Node: screening
  State Hash: a1b2c3d4

LangGraph 状态:
  {
    "messages": [...],
    "current_agent": "screening",
    "candidate_id": "cand_003",
    "match_score": 87,
    "pending_confirmation": true,
    ...
  }

MCP 工具调用日志:
  [10:30:15] parse_resume -> success (1.2s)
  [10:30:18] match_candidate -> success (0.8s)
  [10:30:20] screen_candidate -> pending_confirmation

最近快照:
  v9: snap_20250601_001_v9 (10:35:00)
  v8: snap_20250601_001_v8 (10:30:15)
  v7: snap_20250601_001_v7 (10:25:00)

[查看完整日志] [导出调试信息] [关闭调试]
```

---

### `/export` — 导出数据

**语法**：
```
/export                     # 导出当前任务
/export --format json       # 指定格式
/export --range all         # 导出范围
/export --destination s3    # 导出目标
```

**支持格式**：JSON, CSV, Markdown, PDF, Excel

---

### `/import` — 导入数据

**语法**：
```
/import <file>              # 导入文件
/import --preview           # 预览导入内容
/import --merge             # 合并导入（不覆盖）
```

---

### `/version` — 查看系统版本

**语法**：
```
/version                    # 查看版本
/version --check            # 检查更新
/version --changelog        # 查看更新日志
```

---

### `/config` — 查看/修改配置

**语法**：
```
/config                     # 查看配置
/config --edit              # 编辑配置
/config --reload            # 重载配置
```

> **新增命令**：区分 `/settings`（用户级）和 `/config`（系统级）

---

## 六、快捷操作

### 命令面板

```
用户输入: /

AI:
┌─────────────────────────────────────┐
│ 🔍 命令面板                          │
├─────────────────────────────────────┤
│ 最近使用                            │
│  /status  /snapshot  /read          │
│                                     │
│ 常用命令                            │
│  /restart  /pause  /resume  /help   │
│                                     │
│ 数据操作                            │
│  /list  /search  /add  /write       │
│                                     │
│ 输入命令或搜索...                   │
└─────────────────────────────────────┘
```

### 快捷别名

| 快捷键 | 完整命令 | 说明 |
|--------|----------|------|
| `/` | 唤起命令面板 | 快速选择命令 |
| `//` | 转义模式 | 输入以 `//` 开头的自然语言，不解析为命令 |
| `/r` | `/restart` | 快速重启 |
| `/p` | `/pause` | 快速暂停 |
| `/s` | `/status` | 快速查看状态 |
| `/h` | `/help` | 快速查看帮助 |
| `/n` | `/new` | 快速新对话 |
| `/l` | `/list` | 快速列出 |
| `/d` | `/debug` | 快速调试 |

---

## 七、命令实现架构

### 7.1 整体架构

```
用户输入
  │
  ├── 以 "/" 开头? ──→ 命令解析器 (Command Parser)
  │                      │
  │                      ├── 解析命令名 + 参数
  │                      │
  │                      ├── 权限检查 (Permission Check)
  │                      │
  │                      ├── 匹配命令处理器
  │                      │       │
  │                      │       ├── 任务控制 ──→ 操作任务状态
  │                      │       ├── 对话管理 ──→ 操作会话状态
  │                      │       ├── 数据CRUD ──→ 操作业务数据
  │                      │       └── 系统操作 ──→ 系统功能
  │                      │
  │                      ├── 执行前确认（如需要）
  │                      │
  │                      ├── 执行命令
  │                      │
  │                      └── 记录日志 + 创建快照
  │
  └── 普通输入 ──→ 意图识别 ──→ Agent 路由
```

### 7.2 核心代码骨架

```typescript
// commands/types.ts
export interface CommandContext {
  sessionId: string;
  userId: string;
  currentTask?: Task;
  currentState?: StateSnapshot;
  permissions: string[];
}

export interface CommandResult {
  success: boolean;
  message: string;
  data?: any;
  action?: 'continue' | 'pause' | 'restart' | 'switch_agent' | 'confirm_required';
  snapshot?: SnapshotInfo;
}

export interface CommandHandler {
  (args: string[], context: CommandContext): Promise<CommandResult>;
  name: string;
  description: string;
  category: 'task' | 'dialog' | 'crud' | 'system';
  permissions?: string[];
  needConfirm?: boolean;
  aliases?: string[];
}

// commands/registry.ts
class CommandRegistry {
  private commands: Map<string, CommandHandler> = new Map();
  private aliases: Map<string, string> = new Map();

  register(handler: CommandHandler): void {
    this.commands.set(handler.name, handler);
    handler.aliases?.forEach(alias => {
      this.aliases.set(alias, handler.name);
    });
  }

  get(name: string): CommandHandler | undefined {
    const cmdName = this.aliases.get(name) || name;
    return this.commands.get(cmdName);
  }

  listByCategory(category?: string): CommandHandler[] {
    const all = Array.from(this.commands.values());
    return category ? all.filter(c => c.category === category) : all;
  }
}

// commands/executor.ts
export class CommandExecutor {
  private registry: CommandRegistry;
  private permissionChecker: PermissionChecker;
  private snapshotManager: SnapshotManager;

  async execute(
    input: string, 
    context: CommandContext
  ): Promise<CommandResult> {
    // 1. 解析命令
    const parsed = this.parseCommand(input);
    const handler = this.registry.get(parsed.command);

    if (!handler) {
      return {
        success: false,
        message: `未知命令: ${parsed.command}\n输入 /help 查看所有命令`
      };
    }

    // 2. 权限检查
    if (handler.permissions && !this.hasPermission(context, handler.permissions)) {
      return {
        success: false,
        message: '权限不足，无法执行此命令'
      };
    }

    // 3. 确认检查（敏感操作）
    if (handler.needConfirm && !parsed.flags.force) {
      return {
        success: false,
        action: 'confirm_required',
        message: `执行 "${handler.name}" 需要确认，请添加 --force 或交互确认`
      };
    }

    // 4. 执行命令
    const result = await handler(parsed.args, context);

    // 5. 自动创建快照（如需要）
    if (result.success && handler.category === 'crud') {
      result.snapshot = await this.snapshotManager.create({
        taskId: context.currentTask?.task_id,
        reason: `command:${handler.name}`,
        triggeredBy: context.userId
      });
    }

    // 6. 记录审计日志
    await this.auditLog.record({
      command: parsed.command,
      args: parsed.args,
      userId: context.userId,
      result: result.success,
      timestamp: new Date()
    });

    return result;
  }

  private parseCommand(input: string): ParsedCommand {
    const parts = input.trim().split(/\s+/);
    const command = parts[0].toLowerCase();
    const args: string[] = [];
    const flags: Record<string, any> = {};

    for (let i = 1; i < parts.length; i++) {
      const part = parts[i];
      if (part.startsWith('--')) {
        const [key, value] = part.slice(2).split('=');
        flags[key] = value || true;
      } else if (part.startsWith('-')) {
        flags[part.slice(1)] = true;
      } else {
        args.push(part);
      }
    }

    return { command, args, flags, raw: input };
  }
}

// 注册所有命令
const registry = new CommandRegistry();

// 任务控制
registry.register({
  name: '/restart',
  description: '重启当前任务',
  category: 'task',
  aliases: ['/r'],
  needConfirm: true,
  handler: handleRestart
});

registry.register({
  name: '/pause',
  description: '暂停任务',
  category: 'task',
  aliases: ['/p'],
  handler: handlePause
});

// 对话管理
registry.register({
  name: '/new',
  description: '开启新对话',
  category: 'dialog',
  aliases: ['/n'],
  handler: handleNew
});

// 数据CRUD
registry.register({
  name: '/read',
  description: '读取数据',
  category: 'crud',
  handler: handleRead
});

registry.register({
  name: '/list',
  description: '列出数据',
  category: 'crud',
  aliases: ['/l'],
  handler: handleList
});

registry.register({
  name: '/write',
  description: '写入数据',
  category: 'crud',
  needConfirm: true,
  handler: handleWrite
});

registry.register({
  name: '/add',
  description: '添加数据',
  category: 'crud',
  needConfirm: true,
  handler: handleAdd
});

registry.register({
  name: '/delete',
  description: '删除数据',
  category: 'crud',
  needConfirm: true,
  permissions: ['data:delete'],
  handler: handleDelete
});

registry.register({
  name: '/batch',
  description: '批量操作',
  category: 'crud',
  needConfirm: true,
  permissions: ['data:batch'],
  handler: handleBatch
});

// 系统操作
registry.register({
  name: '/help',
  description: '查看帮助',
  category: 'system',
  aliases: ['/h'],
  handler: handleHelp
});

registry.register({
  name: '/status',
  description: '查看状态',
  category: 'system',
  aliases: ['/s'],
  handler: handleStatus
});

registry.register({
  name: '/debug',
  description: '调试模式',
  category: 'system',
  aliases: ['/d'],
  handler: handleDebug
});
```

### 7.3 数据CRUD命令实现示例

```typescript
// commands/crud/read.ts
async function handleRead(
  args: string[],
  context: CommandContext
): Promise<CommandResult> {
  const [resource, id] = args;
  const format = context.flags.format || 'markdown';
  const fields = context.flags.fields?.split(',') || [];
  const depth = parseInt(context.flags.depth) || 1;

  // 1. 验证资源类型
  const validResources = ['candidate', 'job', 'task', 'resume', 'interview', 'settings'];
  if (!validResources.includes(resource)) {
    return {
      success: false,
      message: `无效的资源类型: ${resource}\n有效类型: ${validResources.join(', ')}`
    };
  }

  // 2. 读取数据
  const data = await dataService.read(resource, id, { depth });

  if (!data) {
    return {
      success: false,
      message: `未找到: ${resource}/${id}`
    };
  }

  // 3. 过滤字段
  const filteredData = fields.length > 0 
    ? pickFields(data, fields)
    : data;

  // 4. 格式化输出
  const formatted = formatOutput(filteredData, format);

  return {
    success: true,
    message: formatted,
    data: filteredData
  };
}

// commands/crud/batch.ts
async function handleBatch(
  args: string[],
  context: CommandContext
): Promise<CommandResult> {
  const action = context.flags.action;
  const target = context.flags.target;
  const filter = context.flags.filter;
  const ids = context.flags.ids?.split(',');
  const data = context.flags.data ? JSON.parse(context.flags.data) : null;

  // 1. 验证参数
  if (!action || !target) {
    return {
      success: false,
      message: '缺少必要参数: --action 和 --target'
    };
  }

  // 2. 查询目标数据
  let targets: string[];
  if (ids) {
    targets = ids;
  } else if (filter) {
    targets = await dataService.queryIds(target, filter);
  } else {
    return {
      success: false,
      message: '请指定 --ids 或 --filter'
    };
  }

  // 3. 预览模式
  if (context.flags.preview) {
    return {
      success: true,
      message: `预览: 将影响 ${targets.length} 条记录`,
      data: { targets, action, data }
    };
  }

  // 4. 执行批量操作
  const results = await batchService.execute({
    action,
    target,
    ids: targets,
    data,
    userId: context.userId
  });

  // 5. 创建快照
  const snapshot = await snapshotManager.create({
    taskId: context.currentTask?.task_id,
    reason: `batch:${action}:${target}`,
    affectedCount: targets.length,
    triggeredBy: context.userId
  });

  return {
    success: true,
    message: `批量操作完成: 成功 ${results.success.length}/${targets.length}`,
    data: results,
    snapshot
  };
}
```

---

## 八、与自然语言的结合

命令系统不是替代自然语言，而是**增强**：

```
用户: 帮我重新来一遍，刚才的招聘需求我理解错了

AI: 
检测意图: 用户想重启任务
检测到关键词 "重新来一遍" -> 建议执行 /restart

AI:
我检测到您想重新开始。当前任务进度是 筛选中 (5份简历已匹配)。

选项:
1. [🔄 重启任务] - 清除所有进度，从头开始
2. [⏸️ 暂停当前] - 保存进度，稍后继续
3. [📸 创建快照] - 保存当前状态，然后重启
4. [💬 继续当前] - 保持现有进度

或者您可以直接输入命令:
- /restart --save  (保存并重启)
- /pause           (暂停)
- /snapshot        (仅保存快照)

用户: 1
AI: ✅ 任务已重启...
```

### 自然语言转命令映射

| 用户表达 | 识别意图 | 建议命令 |
|----------|----------|----------|
| "从头再来" | 重启任务 | `/restart` |
| "暂停一下" | 暂停任务 | `/pause` |
| "继续" | 恢复任务 | `/resume` |
| "查看所有候选人" | 列出数据 | `/list candidates` |
| "搜索会Java的" | 搜索数据 | `/search "Java" --type candidate` |
| "删除张三" | 删除数据 | `/delete candidate <id>` |
| "把这些人标记为高优先级" | 批量更新 | `/batch --action update ...` |
| "现在什么情况" | 查看状态 | `/status` |
| "出什么问题" | 调试模式 | `/debug` |

---

## 九、安全与权限

### 9.1 操作分级

| 级别 | 操作 | 要求 |
|------|------|------|
| L1-只读 | /read, /list, /search, /status, /help | 无限制 |
| L2-普通 | /write, /add, /snapshot, /export | 登录用户 |
| L3-敏感 | /delete, /batch, /rollback, /import | 需确认 |
| L4-危险 | /cancel --delete, /clear --all, /config | 管理员+二次确认 |

### 9.2 回收站机制

```
/delete 操作 → 移至回收站（保留30天）
              → 可随时 /restore 恢复
              → 30天后自动清理
```

### 9.3 审计日志

```
每条命令执行记录:
- 时间戳
- 用户ID
- 命令内容
- 执行结果
- 影响数据量
- 快照ID
```

---

## 十、V2.0 优化点总结

### 相比V1.0的改进

| 维度 | V1.0 | V2.0 |
|------|------|------|
| **命令数量** | 18个 | 28个 |
| **数据操作** | 无 | 完整CRUD（7个命令） |
| **批量操作** | 无 | `/batch` 支持批量读写删 |
| **搜索能力** | 无 | `/search` 支持全文+语义搜索 |
| **分支管理** | 无 | `/fork`, `/diff` 支持并行分支 |
| **安全机制** | 简单确认 | 分级权限+回收站+审计日志 |
| **快捷操作** | 6个 | 8个（新增 `/l`, `/d`） |
| **配置分离** | 混合 | `/settings`(用户) + `/config`(系统) |
| **输出格式** | 固定 | 支持 JSON/Markdown/Table |
| **管道支持** | 无 | 支持 `\| /filter` 管道操作 |

### 使用建议

1. **日常操作**：多用快捷别名（`/r`, `/p`, `/s`）
2. **数据管理**：`/list` + `/search` 快速定位，`/read` 查看详情
3. **批量处理**：`/batch` 处理大量数据，先用 `--preview` 预览
4. **安全操作**：敏感操作默认需确认，可配置 `--force` 跳过
5. **调试排查**：`/debug` 查看内部状态，`/diff` 对比版本差异

---

> **文档版本**: 2.0  
> **最后更新**: 2026-06-01  
> **作者**: AI招聘Agent团队  
> **状态**: 草案 → 评审中
