# AI 招聘 Agent 系统架构文档（含面试子 Agent + 录音功能集成）

> **版本**: v1.1  
> **日期**: 2026-06-06  
> **作者**: qixia  
> **推理框架**: omlx  
> **本地模型**: Qwen3-ASR-1.7B-8bit / Qwen3.6-35B-A3B-4bit  
> **运行环境**: macOS (Apple Silicon)

---

## 目录

1. [架构总览](#1-架构总览)
2. [分层架构详解](#2-分层架构详解)
3. [录音功能详细设计](#3-录音功能详细设计)
4. [面试子 Agent 详细设计](#4-面试子-agent-详细设计)
5. [模型分工策略](#5-模型分工策略)
6. [Agent vs MCP 工具设计原则](#6-agent-vs-mcp-工具设计原则)
7. [附录](#7-附录)

---

## 1. 架构总览

```
+-------------------------------------------------------------+
|                    用户交互层                                |
|  +--------------+         +--------------+                  |
|  | AI 对话入口   |         | 管理后台界面  |                  |
|  | (默认路径)    |         | (隐藏/兜底)   |                  |
|  +------+-------+         +------+-------+                  |
|         |                        |                           |
|         +-----------+------------+                           |
|                     |                                         |
|                     v                                         |
|  +----------------------------------------------+            |
|  | 编排层 (Orchestrator)                         |            |
|  | 意图识别 / Agent 路由 / 结果聚合               |            |
|  +--------------------+--------------------------+            |
|                       |                                       |
|  +--------------------+-------------------------------+       |
|  |              业务子 Agent 层                        |       |
|  |  +-----+ +-----+ +-----+ +---------+ +-----+ +-----+ |   |
|  |  |简历 | |寻访 | |筛选 | |面试协调 | |薪酬 | |入职 | |   |
|  |  |解析 | |Agent| |Agent| |  Agent  | |谈判 | |跟进 | |   |
|  |  |Agent| |3工具| |3工具| |  4工具  | |Agent| |Agent| |   |
|  |  |3工具| |     | |     | | ★重点   | |3工具| |3工具| |   |
|  |  +-----+ +-----+ +-----+ +----+----+ +-----+ +-----+ |   |
|  |                               |                        |   |
|  |         面试子 Agent 内部架构（含录音功能）            |   |
|  |  +--------+ +--------+ +--------+ +--------+        |   |
|  |  |面试准备| |面试执行| |面试评估| |结果反馈|        |   |
|  |  |3功能   | |3功能   | |3功能   | |3功能   |        |   |
|  |  |        | |含录音  | |含ASR   | |含备注  |        |   |
|  |  +--------+ +--------+ +--------+ +--------+        |   |
|  +-----------------------------------------------------+   |
|                       |                                       |
|  +--------------------+-------------------------------+       |
|  |              共享层（4 个工具）                      |       |
|  |         记忆 / 知识 / 通知 / 权限                  |       |
|  +--------------------+-------------------------------+       |
|                       |                                       |
|  +--------------------+-------------------------------+       |
|  |              MCP Server 层                         |       |
|  |  +----------+ +----------+ +--------------+       |       |
|  |  |内置 MCP  | |外部 Skill| |面试专用 MCP  |       |       |
|  |  |工具集    | |加载器    | |  含录音工具   |       |       |
|  |  |4工具     | |3功能     | |4工具+1录音   |       |       |
|  |  +----------+ +----------+ +--------------+       |       |
|  +-----------------------------------------------------+   |
|                       |                                       |
|  +--------------------+-------------------------------+       |
|  |         业务系统 API + 数据库                       |       |
|  |  +--------+ +----------+ +--------------+         |       |
|  |  | MySQL  | | Qdrant   | |Elasticsearch |         |       |
|  |  |关系型  | |向量数据库| |全文检索      |         |       |
|  |  +--------+ +----------+ +--------------+         |       |
|  |  +----------------------------------------+      |       |
|  |  | 录音文件存储 (本地文件系统 / 对象存储)   |      |       |
|  |  +----------------------------------------+      |       |
|  +-----------------------------------------------------+   |
+-------------------------------------------------------------+
```

---

## 2. 分层架构详解

### 2.1 用户交互层

| 组件 | 职责 | 说明 |
|------|------|------|
| **AI 对话入口** | 用户与系统的主要交互界面 | 默认路径，支持自然语言输入 |
| **管理后台界面** | 兜底操作界面 | 隐藏入口，用于异常处理、数据查看、人工干预 |

**录音功能入口**：
- 用户在 AI 对话中输入：「开始面试录音」
- 或点击界面上的「开始录音」按钮
- 系统通过 Orchestrator 路由到面试协调 Agent，触发录音 MCP 工具

---

### 2.2 编排层 (Orchestrator)

**核心职责**：
1. **意图识别**：解析用户输入，判断真实意图
2. **Agent 路由**：将任务分发给合适的子 Agent
3. **结果聚合**：收集子 Agent 返回结果，整合后返回给用户

**录音相关意图示例**：
```
用户: "开始面试录音"
-> 意图识别: "interview_record_start"
-> Agent 路由: 面试协调 Agent
-> 参数: action="start_recording", interview_id="INT-001"

用户: "停止录音并生成面试记录"
-> 意图识别: "interview_record_stop_and_summarize"
-> Agent 路由: 面试协调 Agent
-> 参数: action="stop_recording", generate_summary=true
```

---

### 2.3 业务子 Agent 层

| Agent | 工具数 | 核心职责 | 是否涉及录音 |
|-------|--------|----------|-------------|
| 简历解析 Agent | 3 工具 | 简历上传、解析、信息提取 | 否 |
| 寻访 Agent | 3 工具 | 人才搜索、主动触达、渠道管理 | 否 |
| 筛选 Agent | 3 工具 | 简历筛选、初评、排序 | 否 |
| **面试协调 Agent** | **4+1 工具** | **面试全流程管理（含录音）** | **是** |
| 薪酬谈判 Agent | 3 工具 | 薪资分析、谈判策略、Offer 生成 | 否 |
| 入职跟进 Agent | 3 工具 | 入职准备、培训安排、试用期跟踪 | 否 |

---

### 2.4 面试子 Agent 内部架构（含录音功能）

面试协调 Agent 内部拆分为 **4 大模块**，其中**面试执行模块**和**面试评估模块**与录音功能深度集成：

#### 模块一：面试准备

| 功能 | 说明 | 对应 MCP 工具 |
|------|------|---------------|
| JD 对齐 | 对比岗位 JD 与候选人简历，识别匹配度 | `jd_matcher` |
| 题库生成 | 基于 JD 和简历自动生成定制化面试题 | `question_bank_generator` |
| 面试官匹配 | 根据候选人技术栈匹配最合适的面试官 | `interviewer_matcher` |

#### 模块二：面试执行（含录音功能）

| 功能 | 说明 | 对应 MCP 工具 |
|------|------|---------------|
| **录音控制** | **启动/暂停/停止面试录音** | **`audio_recorder`** |
| 语音/视频接入 | 支持在线面试的实时接入 | `meeting_connector` |
| 实时记录 | 面试过程中的实时文本记录 | `live_note_taker` |
| 追问辅助 | 根据候选人回答智能推荐追问问题 | `follow_up_helper` |

#### 模块三：面试评估（含 ASR 转录）

| 功能 | 说明 | 对应 MCP 工具 |
|------|------|---------------|
| **ASR 转录** | **将录音转为文本，供评估使用** | **`asr_transcriber`** |
| 评分模型 | 多维度结构化评分（技术/沟通/文化匹配） | `scoring_model` |
| 能力雷达图 | 生成可视化能力评估雷达图 | `radar_chart_generator` |
| 对比分析 | 与历史候选人或岗位标准进行对比 | `candidate_comparator` |

#### 模块四：结果反馈

| 功能 | 说明 | 对应 MCP 工具 |
|------|------|---------------|
| 评语生成 | 自动生成结构化面试评语 | `feedback_generator` |
| 推荐结论 | 输出 Hire/Reject/Pending 建议 | `recommendation_engine` |
| 备注同步 | 将面试结果同步到招聘主系统 | `interview_note_sync` |

---

### 2.5 共享层（4 个工具）

| 工具 | 职责 | 被调用方 |
|------|------|----------|
| **记忆** | 维护对话历史、候选人状态、面试进度、录音状态 | 所有子 Agent |
| **知识** | 公司制度、岗位知识库、面试标准、录音合规规范 | 所有子 Agent |
| **通知** | 邮件/短信/站内信发送（含录音开始/结束通知） | 面试、入职等 Agent |
| **权限** | 角色权限控制、数据访问限制、录音文件访问权限 | 所有子 Agent |

---

### 2.6 MCP Server 层（含录音 MCP 工具）

MCP Server 分为 **三大模块**，**面试专用 MCP** 新增录音相关工具：

#### 2.6.1 内置 MCP 工具集

| 工具 | 说明 |
|------|------|
| 简历解析器 | 解析 PDF/Word 简历，提取结构化信息 |
| JD 生成器 | 根据岗位需求自动生成 JD 文本 |
| 邮件发送 | 发送面试邀请、结果通知等邮件 |
| 日历调度 | 管理面试官和候选人的时间安排 |

#### 2.6.2 外部 Skill 加载器

| 功能 | 说明 |
|------|------|
| skill.md 识别 | 扫描并解析外部 skill.md 文件 |
| 动态注册 | 将识别到的 skill 注册为可用工具 |
| handler 生成 | 自动生成工具调用 handler |

#### 2.6.3 面试专用 MCP（含录音工具）

| 工具 | 说明 | 依赖 |
|------|------|------|
| **`audio_recorder`** | **本地录音控制（启动/暂停/停止）** | **macOS 麦克风 + Python sounddevice** |
| **ASR 语音转录** | 将录音文件转为文本 | Qwen3-ASR-1.7B-8bit (omlx) |
| 面试录音分析 | 分析录音中的情绪、语速、关键词 | Qwen3.6-35B-A3B-4bit (omlx) |
| 评分算法 | 执行结构化评分计算 | Qwen3.6-35B-A3B-4bit (omlx) |
| 备注同步 | 将面试结果写入招聘主系统 | 业务系统 API |

---

### 2.7 业务系统 API + 数据库层

| 组件 | 类型 | 用途 |
|------|------|------|
| **MySQL** | 关系型数据库 | 候选人信息、面试记录、录音元数据 |
| **Qdrant** | 向量数据库 | 简历向量嵌入、语义搜索、录音文本向量 |
| **Elasticsearch** | 全文检索引擎 | 简历全文检索、录音转录文本检索 |
| **本地文件系统** | 文件存储 | 原始录音文件 (.wav/.mp3) |

**录音文件存储策略**：
- 原始录音文件存储在本地文件系统（或对象存储）
- MySQL 存储录音元数据（文件名、时长、路径、关联面试 ID）
- Qdrant 存储录音转录文本的向量嵌入（用于语义检索）

---

## 3. 录音功能详细设计

### 3.1 录音 MCP 工具设计

#### 工具: `audio_recorder`（本地录音控制）

```json
{
  "name": "audio_recorder",
  "description": "控制本地麦克风录音，支持启动、暂停、停止录音，并将录音保存为 WAV 文件。适用于 macOS 本地面试录音场景。",
  "parameters": {
    "action": {
      "type": "string",
      "enum": ["start", "pause", "resume", "stop", "get_status"],
      "description": "录音控制动作"
    },
    "interview_id": {
      "type": "string",
      "description": "关联的面试 ID，用于生成录音文件名"
    },
    "duration": {
      "type": "integer",
      "default": 3600,
      "description": "最大录音时长（秒），默认 1 小时"
    },
    "sample_rate": {
      "type": "integer",
      "enum": [16000, 44100, 48000],
      "default": 16000,
      "description": "采样率。ASR 推荐 16kHz，音乐推荐 44.1kHz"
    },
    "channels": {
      "type": "integer",
      "enum": [1, 2],
      "default": 1,
      "description": "声道数。ASR 推荐单声道"
    },
    "output_format": {
      "type": "string",
      "enum": ["wav", "mp3"],
      "default": "wav",
      "description": "输出音频格式"
    },
    "output_dir": {
      "type": "string",
      "default": "./recordings",
      "description": "录音文件输出目录"
    }
  },
  "returns": {
    "status": "string",
    "recording_id": "string",
    "file_path": "string",
    "duration_seconds": "float",
    "file_size_mb": "float",
    "sample_rate": "integer",
    "channels": "integer",
    "started_at": "datetime",
    "stopped_at": "datetime"
  }
}
```

#### 工具: `asr_transcriber`（语音转录 - 已更新支持录音文件）

```json
{
  "name": "asr_transcriber",
  "description": "将面试录音文件转录为文本，基于 omlx 本地 Qwen3-ASR-1.7B-8bit 模型。支持整文件转录和分段流式转录。",
  "parameters": {
    "audio_file_path": {
      "type": "string",
      "description": "录音文件路径（由 audio_recorder 生成）"
    },
    "language": {
      "type": "string",
      "enum": ["zh", "en", "auto"],
      "default": "zh",
      "description": "识别语言"
    },
    "mode": {
      "type": "string",
      "enum": ["full", "chunked"],
      "default": "full",
      "description": "转录模式：full=整文件转录，chunked=分段转录（适合长录音）"
    },
    "chunk_duration": {
      "type": "integer",
      "default": 30,
      "description": "分段转录时每段时长（秒），仅 chunked 模式有效"
    },
    "speaker_diarization": {
      "type": "boolean",
      "default": false,
      "description": "是否启用说话人分离（区分面试官和候选人）"
    },
    "output_format": {
      "type": "string",
      "enum": ["text", "json_with_timestamps", "srt"],
      "default": "json_with_timestamps",
      "description": "输出格式"
    }
  },
  "returns": {
    "transcription": "string",
    "segments": [
      {
        "start_time": "float",
        "end_time": "float",
        "text": "string",
        "speaker": "string",
        "confidence": "float"
      }
    ],
    "full_text": "string",
    "processing_time_seconds": "float",
    "model_used": "string"
  }
}
```

---

### 3.2 macOS 录音实现方案

#### 方案选择：sounddevice（推荐）

| 库 | 优点 | 缺点 | 推荐场景 |
|----|------|------|----------|
| **sounddevice** | API 简洁、依赖少、支持 numpy 数组、macOS 兼容好 | 功能相对简单 | **推荐：快速实现、ASR 前置录音** |
| pyaudio | 功能丰富、底层控制精细 | 安装复杂、依赖多、API 繁琐 | 复杂音频处理 |
| arecord (命令行) | 无需 Python 依赖 | 灵活性差 | 简单脚本 |

**推荐 sounddevice 的原因**：
1. **安装简单**：`pip install sounddevice` 即可，无需额外系统依赖
2. **API 简洁**：几行代码即可实现录音
3. **numpy 原生支持**：录音数据直接是 numpy 数组，方便后续处理
4. **macOS 兼容**：基于 PortAudio，跨平台支持好
5. **适合 ASR**：可以直接控制采样率为 16kHz（ASR 模型推荐）

#### 安装步骤

```bash
# 1. 安装 sounddevice
pip install sounddevice soundfile numpy

# 2. 验证麦克风权限（macOS 首次使用需要授权）
# 系统设置 -> 隐私与安全性 -> 麦克风 -> 允许终端/IDE 访问

# 3. 测试录音设备列表
python -c "import sounddevice as sd; print(sd.query_devices())"
```

---

### 3.3 录音 -> ASR -> 面试 Agent 完整数据流

```
用户操作
"开始面试录音" / 点击 录音按钮
    |
    v
+-------------------------------------------------------------+
| 编排层 (Orchestrator)                                       |
| 意图识别: "interview_record_start"                           |
| Agent 路由 -> 面试协调 Agent                                  |
+---------------------+---------------------------------------+
                      |
                      v
+-------------------------------------------------------------+
| 面试协调 Agent                                               |
| 决策: 需要启动录音                                           |
| 调用 MCP 工具: audio_recorder.start()                        |
+---------------------+---------------------------------------+
                      |
                      v
+-------------------------------------------------------------+
| MCP Server: audio_recorder                                   |
| 1. 调用 sounddevice 启动麦克风输入流                         |
| 2. 实时采集音频数据（16kHz, 单声道, int16）                  |
| 3. 音频数据暂存内存（numpy 数组）                            |
| 4. 用户面试进行中...                                         |
+---------------------+---------------------------------------+
                      |
                      v（用户说"停止录音"）
+-------------------------------------------------------------+
| 面试协调 Agent                                               |
| 决策: 需要停止录音并转录                                     |
| 调用 MCP 工具: audio_recorder.stop()                         |
+---------------------+---------------------------------------+
                      |
                      v
+-------------------------------------------------------------+
| MCP Server: audio_recorder                                   |
| 1. 停止音频流                                                |
| 2. 合并音频数据为 numpy 数组                                  |
| 3. 保存为 WAV 文件: REC-INT-xxx-20260606_143052.wav          |
| 4. 返回文件路径和元数据                                       |
+---------------------+---------------------------------------+
                      |
                      v
+-------------------------------------------------------------+
| 面试协调 Agent                                               |
| 决策: 录音完成，需要 ASR 转录                                 |
| 调用 MCP 工具: asr_transcriber()                             |
| 参数: audio_file_path="./recordings/REC-INT-xxx.wav"          |
+---------------------+---------------------------------------+
                      |
                      v
+-------------------------------------------------------------+
| MCP Server: asr_transcriber                                  |
| 1. 加载 WAV 文件                                             |
| 2. omlx 加载 Qwen3-ASR-1.7B-8bit 模型                       |
| 3. 模型推理：音频 -> 文本                                     |
| 4. 返回转录结果（含时间戳）                                   |
+---------------------+---------------------------------------+
                      |
                      v
+-------------------------------------------------------------+
| 面试协调 Agent                                               |
| 1. 接收 ASR 转录文本                                         |
| 2. 调用 scoring_model 进行面试评估                            |
| 3. 调用 feedback_generator 生成评语                          |
| 4. 调用 interview_note_sync 同步到数据库                       |
+---------------------+---------------------------------------+
                      |
                      v
+-------------------------------------------------------------+
| 业务系统                                                     |
| MySQL: 写入 interview_records 表                             |
|   - 面试基本信息                                             |
|   - 录音文件路径                                             |
|   - ASR 转录文本                                             |
|   - 评分结果                                                 |
|   - 面试评语                                                 |
|                                                              |
| 文件系统: 保存原始录音文件                                    |
|   ./recordings/REC-INT-xxx-20260606_143052.wav               |
|                                                              |
| Qdrant: 存储转录文本向量（用于语义检索）                      |
+-------------------------------------------------------------+
```

---

### 3.4 录音文件管理策略

#### 文件命名规范

```
REC-{interview_id}-{YYYYMMDD}_{HHMMSS}.{format}

示例:
REC-INT-2026-001-20260606_143052.wav
REC-INT-2026-001-20260606_143052.json  (ASR 转录结果)
REC-INT-2026-001-20260606_143052_summary.md  (面试总结)
```

#### 存储目录结构

```
./recordings/
├── 2026/
│   ├── 06/
│   │   ├── 06/
│   │   │   ├── REC-INT-2026-001-20260606_143052.wav
│   │   │   ├── REC-INT-2026-001-20260606_143052.json
│   │   │   └── REC-INT-2026-001-20260606_143052_summary.md
│   │   └── 07/
│   └── 07/
└── archive/  (过期录音归档)
```

#### 数据保留策略

| 数据类型 | 保留时长 | 处理方式 |
|----------|----------|----------|
| 原始录音文件 | 90 天 | 过期后转存冷存储或删除 |
| ASR 转录文本 | 永久 | 存入数据库，支持全文检索 |
| 面试评分结果 | 永久 | 存入数据库 |
| 录音元数据 | 永久 | 存入 MySQL |

---

## 4. 面试子 Agent 详细设计

### 4.1 四大内部模块（含录音集成）

```
+-------------------------------------------------------------+
|                    面试协调 Agent                           |
|                                                             |
|  +------------+  +------------+  +------------+  +------------+  |
|  |   面试准备  |  |   面试执行  |  |   面试评估  |  |   结果反馈  |  |
|  |            |  |            |  |            |  |            |  |
|  | - JD对齐   |  | - 录音控制  |  | - ASR转录  |  | - 评语生成  |  |
|  | - 题库生成 |  |   启动     |  |   文本     |  | - 推荐结论  |  |
|  | - 面试官   |  |   暂停     |  | - 评分模型  |  | - 备注同步  |  |
|  |   匹配     |  |   停止     |  | - 能力雷达  |  |            |  |
|  |            |  | - 实时记录 |  | - 对比分析  |  |            |  |
|  |            |  | - 追问辅助 |  |            |  |            |  |
|  +------+-----+  +------+-----+  +------+-----+  +------+-----+  |
|         |              |              |              |              |
|         +--------------+--------------+--------------+              |
|                        |                                            |
|                        v                                            |
|              +---------+----------+                                  |
|              |     共享层         |                                  |
|              | 记忆/知识/通知/权限 |                                  |
|              +--------------------+                                  |
+-------------------------------------------------------------+
```

### 4.2 面试专用 MCP 工具（含录音）

#### 完整工具清单

| 工具名 | 用途 | 调用时机 | 依赖 |
|--------|------|----------|------|
| `audio_recorder` | 本地录音控制（启动/暂停/停止） | 面试开始时 | macOS 麦克风 + sounddevice |
| `asr_transcriber` | 语音转录（录音文件 -> 文本） | 录音停止后 | omlx + Qwen3-ASR-1.7B-8bit |
| `interview_prep` | 面试准备工具集 | 面试开始前 | Qwen3.6-35B |
| `scoring_engine` | 评分与雷达图生成 | 面试结束后 | Qwen3.6-35B |
| `note_sync` | 面试备注同步 | 评估完成后 | 业务系统 API |

### 4.3 系统提示词框架（含录音指令）

```markdown
# 面试协调 Agent 系统提示词（含录音功能）

## 角色定位
你是招聘系统中的「面试协调专家」，负责从面试准备到结果反馈的全流程管理。
你的目标是确保每一次面试都能高效、公正、结构化地进行，并产出可复用的面试数据。

## 核心职责

### 1. 面试准备
- 根据岗位 JD 和候选人简历，分析匹配度
- 生成定制化面试题库（技术题 + 行为题 + 情景题）
- 为候选人匹配最合适的面试官组合

### 2. 面试执行（含录音控制）
- 录音控制：根据用户指令启动/暂停/停止面试录音
  - 用户说「开始录音」-> 调用 audio_recorder.start()
  - 用户说「暂停录音」-> 调用 audio_recorder.pause()
  - 用户说「继续录音」-> 调用 audio_recorder.resume()
  - 用户说「停止录音」-> 调用 audio_recorder.stop()
- 语音/视频面试的实时接入与记录
- 面试过程中提供智能追问建议
- 实时转录面试对话（通过 ASR 工具）

### 3. 面试评估（含 ASR 转录）
- ASR 转录：录音停止后，自动调用 asr_transcriber 将录音转为文本
- 基于转录文本和候选人表现，执行多维度结构化评分
- 生成候选人能力雷达图
- 与历史候选人或岗位标准进行对比分析

### 4. 结果反馈
- 自动生成结构化面试评语（基于 ASR 转录文本）
- 输出 Hire/Reject/Pending 推荐结论
- 将面试结果（含录音文件路径、转录文本）同步到招聘主系统

## 可用工具清单

| 工具名 | 用途 | 调用时机 |
|--------|------|----------|
| audio_recorder | 本地录音控制 | 面试开始/暂停/停止时 |
| asr_transcriber | 语音实时转录 | 录音停止后 |
| interview_prep | 面试准备工具集 | 面试开始前 |
| scoring_engine | 评分与雷达图生成 | 面试结束后 |
| note_sync | 面试备注同步 | 评估完成后 |

## 录音工作流标准

1. 接收编排层指令，确认面试类型（初面/复面/终面）
2. 调用 interview_prep 准备面试材料
3. 【录音阶段】
   a. 用户说「开始录音」-> 调用 audio_recorder.start()
   b. 面试进行中，音频数据实时采集到内存
   c. 用户说「停止录音」-> 调用 audio_recorder.stop()
   d. 录音文件保存到 ./recordings/ 目录
4. 【ASR 转录阶段】
   a. 调用 asr_transcriber(audio_file_path=录音文件路径)
   b. omlx 加载 Qwen3-ASR-1.7B-8bit 模型进行转录
   c. 获取带时间戳的转录文本
5. 【评估阶段】
   a. 调用 scoring_engine(转录文本, JD要求)
   b. 生成多维度评分和雷达图
6. 【反馈阶段】
   a. 调用 feedback_generator 生成评语
   b. 调用 note_sync 将结果（含录音路径、转录文本）写入数据库
7. 向编排层返回结构化面试报告

## 输出格式规范

```json
{
  "status": "completed",
  "candidate_id": "CAND-2026-001",
  "candidate_name": "张三",
  "interview_round": "1st",
  "interview_type": "technical",
  "interview_date": "2026-06-06T14:00:00Z",
  "interviewer_ids": ["EMP-001", "EMP-002"],

  "recording": {
    "recording_id": "REC-INT-2026-001-20260606_143052",
    "file_path": "./recordings/REC-INT-2026-001-20260606_143052.wav",
    "duration_seconds": 1800,
    "file_size_mb": 55.2
  },

  "asr_transcription": {
    "full_text": "面试官：请先介绍一下你自己... 候选人：您好，我是张三...",
    "segments": [
      {
        "start_time": 0.0,
        "end_time": 15.5,
        "text": "面试官：请先介绍一下你自己",
        "speaker": "interviewer"
      },
      {
        "start_time": 16.0,
        "end_time": 120.0,
        "text": "候选人：您好，我是张三，毕业于...",
        "speaker": "candidate"
      }
    ]
  },

  "scores": {
    "technical": 85,
    "communication": 90,
    "culture_fit": 88,
    "learning_ability": 82,
    "problem_solving": 87
  },
  "overall_score": 86.4,
  "recommendation": "hire",

  "strengths": [
    "扎实的算法基础",
    "良好的沟通表达能力",
    "对业务场景理解深入"
  ],
  "weaknesses": [
    "分布式系统设计经验不足"
  ],

  "notes": "张三在技术面试中表现优秀...",
  "synced": true,
  "synced_at": "2026-06-06T15:30:00Z"
}
```

## 约束条件
- 评分必须基于面试实际表现（含 ASR 转录文本分析），不得主观臆断
- 评语必须具体、可验证，引用转录文本中的具体回答作为依据
- 所有面试数据（含录音文件路径、转录文本）必须同步到主系统
- 涉及候选人隐私信息需遵循权限控制
- 录音文件保留 90 天后自动归档或删除，转录文本永久保留
```

---

## 5. 模型分工策略

| 模型 | 参数规模 | 职责 | 选择原因 |
|------|----------|------|----------|
| **Qwen3.6-35B-A3B-4bit** | 35B (4bit 量化) | 编排层意图识别、面试评估推理、评语生成、题库生成 | 参数大，推理能力强，适合复杂决策和生成任务 |
| **Qwen3-ASR-1.7B-8bit** | 1.7B (8bit 量化) | **语音转录：录音文件 -> 文本** | 轻量、低延迟，专精语音任务，适合 ASR 场景 |
| **omlx 推理框架** | - | 统一调度、模型切换、量化推理、内存管理 | 本地部署，隐私可控，支持 Apple Silicon |

### 录音场景下的模型分工

```
用户: "开始面试录音"
    |
    +---> Qwen3.6-35B（理解意图、制定计划）
    |       |
    |       +---> 需要录音？
    |       |       +---> 调用 audio_recorder MCP 工具
    |       |               +---> sounddevice（本地麦克风录音）
    |       |
    |       +---> 录音停止，需要转录？
    |       |       +---> 调用 asr_transcriber MCP 工具
    |       |               +---> omlx 加载 Qwen3-ASR-1.7B-8bit
    |       |               +---> 模型推理：音频 -> 文本
    |       |
    |       +---> 需要生成评语？
    |       |       +---> Qwen3.6-35B 自身完成（基于转录文本）
    |       |
    |       +---> 需要评分推理？
    |               +---> Qwen3.6-35B 自身完成
    |
    +---> omlx 负责模型加载、切换、资源管理
```

---

## 6. Agent vs MCP 工具设计原则

### 6.1 核心区别

| 维度 | Agent | MCP 工具 |
|------|-------|----------|
| **角色定位** | 指挥官/决策者 | 士兵/执行者 |
| **核心能力** | 意图理解、策略规划、任务编排 | 具体技能执行、数据处理 |
| **知识范围** | 业务流程、上下文记忆 | 技术实现、API 调用 |
| **状态管理** | 维护对话状态、任务状态 | 无状态，单次调用 |
| **复用性** | 业务专属，不可跨领域复用 | 技术通用，可跨 Agent 复用 |
| **替换成本** | 高（涉及业务逻辑） | 低（只改实现，不改接口） |

### 6.2 判断标准：什么应该做成 MCP 工具？

**应该做成 MCP 工具的情况**：
- 涉及具体技术实现（如语音转录、录音控制、PDF 解析、邮件发送）
- 多个 Agent 可能共用（如 ASR 转录，寻访 Agent 打电话也要用）
- 需要独立测试和版本管理
- 实现可能频繁变更（如换模型、换 API、换录音库）

**应该留在 Agent 提示词里的情况**：
- 业务决策逻辑（如「什么情况下推荐 Hire」）
- 上下文理解和意图推理
- 多步骤任务的编排策略（如「先录音 -> 再转录 -> 再评估」）

### 6.3 本项目中的具体分工

```
面试协调 Agent（提示词内）
+-- "判断这是初面还是复面"
+-- "决定需要哪些评分维度"
+-- "根据评分输出推荐结论"
+-- "组织最终面试报告的结构"
+-- "决定何时启动/停止录音"

MCP 工具（外部实现）
+-- audio_recorder: "控制麦克风录音"
+-- asr_transcriber: "把音频变成文字"
+-- scoring_model: "按规则计算分数"
+-- question_bank_generator: "根据输入生成题目"
+-- interview_note_sync: "把数据写入数据库"
```

### 6.4 一句话总结

> **Agent 决定「做什么」和「按什么顺序做」，MCP 工具负责「具体怎么做」。**
>
> 录音控制（audio_recorder）是技术实现，应该做成 MCP 工具；
> 何时录音、录音后做什么，是业务决策，留在 Agent 提示词里。

---

## 7. 附录

### 7.1 术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| Agent | Agent | 智能体，具备自主决策能力的 AI 实体 |
| MCP | Model Context Protocol | 模型上下文协议，用于标准化 AI 工具调用 |
| ASR | Automatic Speech Recognition | 自动语音识别，将语音转为文本 |
| omlx | - | 本地大模型推理框架，支持 Apple Silicon |
| Qdrant | - | 开源向量数据库，用于语义搜索 |
| Orchestrator | Orchestrator | 编排器，负责 Agent 调度和任务分发 |
| JD | Job Description | 岗位描述 |
| RAG | Retrieval-Augmented Generation | 检索增强生成 |
| sounddevice | - | Python 音频 I/O 库，基于 PortAudio |
| WAV | Waveform Audio File Format | 无损音频文件格式 |

### 7.2 录音功能代码示例

#### 核心录音代码（sounddevice）

```python
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import time
from datetime import datetime
import threading

# ========== 配置 ==========
SAMPLE_RATE = 16000  # ASR 推荐 16kHz
CHANNELS = 1         # 单声道
DTYPE = 'int16'
OUTPUT_DIR = "./interview_recordings"
os.makedirs(OUTPUT_DIR, exist_ok=True)


class InterviewRecorder:
    # 本地音频录音器 - 基于 sounddevice

    def __init__(self, output_dir="./recordings"):
        self.output_dir = output_dir
        self.recording = False
        self.paused = False
        self.audio_data = []
        self.stream = None
        self.start_time = None
        self.recording_id = None
        self.interview_id = None
        os.makedirs(output_dir, exist_ok=True)

    def _audio_callback(self, indata, frames, time_info, status):
        # 音频流回调函数
        if status:
            print(f"音频状态: {status}")
        if self.recording and not self.paused:
            self.audio_data.append(indata.copy())

    def start(self, interview_id: str, duration: int = 3600) -> dict:
        # 开始录音
        if self.recording:
            return {"status": "error", "message": "录音已在进行中"}

        self.interview_id = interview_id
        self.recording_id = f"REC-{interview_id}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.audio_data = []
        self.recording = True
        self.paused = False
        self.start_time = datetime.now()

        # 启动音频输入流
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._audio_callback
        )
        self.stream.start()

        # 启动定时器，到达最大时长自动停止
        if duration > 0:
            threading.Timer(duration, self.stop).start()

        return {
            "status": "recording",
            "recording_id": self.recording_id,
            "interview_id": interview_id,
            "started_at": self.start_time.isoformat(),
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS
        }

    def pause(self) -> dict:
        # 暂停录音
        if not self.recording:
            return {"status": "error", "message": "没有正在进行的录音"}
        self.paused = True
        return {
            "status": "paused",
            "recording_id": self.recording_id,
            "paused_at": datetime.now().isoformat()
        }

    def resume(self) -> dict:
        # 恢复录音
        if not self.recording:
            return {"status": "error", "message": "没有正在进行的录音"}
        self.paused = False
        return {
            "status": "recording",
            "recording_id": self.recording_id,
            "resumed_at": datetime.now().isoformat()
        }

    def stop(self) -> dict:
        # 停止录音并保存文件
        if not self.recording:
            return {"status": "error", "message": "没有正在进行的录音"}

        self.recording = False
        self.paused = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if len(self.audio_data) == 0:
            return {"status": "error", "message": "没有录制到音频数据"}

        audio_array = np.concatenate(self.audio_data, axis=0)
        filename = f"{self.recording_id}.wav"
        file_path = os.path.join(self.output_dir, filename)
        sf.write(file_path, audio_array, SAMPLE_RATE)

        duration = len(audio_array) / SAMPLE_RATE
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        stopped_at = datetime.now()

        return {
            "status": "completed",
            "recording_id": self.recording_id,
            "interview_id": self.interview_id,
            "file_path": file_path,
            "duration_seconds": round(duration, 2),
            "file_size_mb": round(file_size, 2),
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "started_at": self.start_time.isoformat(),
            "stopped_at": stopped_at.isoformat()
        }

    def get_status(self) -> dict:
        # 获取当前录音状态
        if not self.recording:
            return {"status": "idle"}
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            "status": "paused" if self.paused else "recording",
            "recording_id": self.recording_id,
            "interview_id": self.interview_id,
            "elapsed_seconds": round(elapsed, 2),
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS
        }


# ========== 使用示例 ==========
if __name__ == "__main__":
    recorder = InterviewRecorder(output_dir="./interview_recordings")

    # 1. 开始录音
    result = recorder.start(interview_id="INT-2026-001")
    print(f"开始录音: {result}")

    # 2. 模拟录音 10 秒
    print("录音中...（10秒）")
    time.sleep(10)

    # 3. 停止录音
    result = recorder.stop()
    print(f"录音完成: {result}")
```

#### 完整面试录音 + ASR 流程示例

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 面试录音 + ASR 转录完整示例

import json
import time
from datetime import datetime
import os

# 假设 InterviewRecorder 类已定义（见上方代码）

class ASRTranscriber:
    # ASR 转录器 - omlx + Qwen3-ASR-1.7B-8bit

    def __init__(self, model_path: str = None):
        self.model_path = model_path
        self.model = None
        # TODO: 加载 omlx 模型
        # import omlx
        # self.model = omlx.load(model_path)

    def transcribe(self, audio_file: str) -> dict:
        # 转录音频文件
        print(f"开始 ASR 转录: {audio_file}")

        # TODO: 实际调用 omlx + Qwen3-ASR-1.7B-8bit
        # result = self.model.transcribe(audio_file)

        # 模拟返回结果
        mock_result = {
            "full_text": "面试官：请先介绍一下你自己。候选人：您好，我是张三...",
            "segments": [
                {"start": 0, "end": 5, "text": "面试官：请先介绍一下你自己", "speaker": "interviewer"},
                {"start": 6, "end": 60, "text": "候选人：您好，我是张三，毕业于北京大学...", "speaker": "candidate"}
            ],
            "processing_time": 10.5,
            "model": "Qwen3-ASR-1.7B-8bit"
        }

        print(f"ASR 转录完成: {len(mock_result['full_text'])} 字符")
        return mock_result


def demo_interview_with_recording():
    # 演示：面试录音 + ASR 转录完整流程

    interview_id = "INT-2026-001"
    candidate_name = "张三"

    print(f"
{'='*60}")
    print(f"面试流程演示: {candidate_name} ({interview_id})")
    print(f"{'='*60}
")

    # 1. 初始化组件
    recorder = InterviewRecorder(output_dir="./interview_recordings")
    asr = ASRTranscriber()

    # 2. 开始录音
    print("【步骤 1】启动面试录音")
    result = recorder.start(interview_id)
    print(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}
")

    # 3. 模拟面试进行
    print("【步骤 2】面试进行中...（模拟 5 秒）")
    time.sleep(5)
    print("面试结束
")

    # 4. 停止录音
    print("【步骤 3】停止录音")
    record_result = recorder.stop()
    print(f"结果: {json.dumps(record_result, indent=2, ensure_ascii=False)}
")

    # 5. ASR 转录
    print("【步骤 4】ASR 语音转录")
    audio_file = record_result["file_path"]
    asr_result = asr.transcribe(audio_file)
    print(f"结果: {json.dumps(asr_result, indent=2, ensure_ascii=False)}
")

    # 6. 保存完整面试记录
    print("【步骤 5】保存面试记录")
    interview_record = {
        "interview_id": interview_id,
        "candidate_name": candidate_name,
        "recording": record_result,
        "transcription": asr_result,
        "created_at": datetime.now().isoformat()
    }

    record_file = os.path.join("./interview_recordings", f"{interview_id}_record.json")
    with open(record_file, 'w', encoding='utf-8') as f:
        json.dump(interview_record, f, ensure_ascii=False, indent=2)

    print(f"面试记录已保存: {record_file}
")
    print(f"{'='*60}")
    print("面试流程完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    demo_interview_with_recording()
```

### 7.3 参考资源

- [MCP 官方文档](https://modelcontextprotocol.io/)
- [omlx GitHub 仓库](https://github.com/ml-explore/omlx)
- [Qwen3 模型文档](https://qwenlm.github.io/)
- [sounddevice 文档](https://python-sounddevice.readthedocs.io/)
- [PortAudio 官网](http://www.portaudio.com/)
- [Qdrant 官方文档](https://qdrant.tech/documentation/)

---

> **文档维护说明**：本架构文档随系统迭代持续更新。新增子 Agent 或 MCP 工具时，需同步更新对应章节。录音功能相关代码需在实际环境中测试 macOS 麦克风权限和 omlx 模型加载。
