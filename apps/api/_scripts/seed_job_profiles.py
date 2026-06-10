"""Seed: 多岗位画像模板 + active version。

用法: python3 apps/api/_scripts/seed_job_profiles.py
首次跑会创建 6 个岗位模板，幂等(code 冲突跳过)。
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.job_profile import JobProfile, JobProfileVersion, JobProfileVersionStatus

logger = logging.getLogger(__name__)

PROFILES: list[dict] = [
    {
        "code": "Java_P7",
        "title": "高级 Java 工程师",
        "level": "P7",
        "department": "技术部",
        "description": "负责核心业务系统设计与开发，主导技术方案评审。",
        "hard_requirements": [
            "5年以上 Java 开发经验",
            "精通 Spring Boot/Cloud 微服务体系",
            "熟悉 MySQL 分库分表与性能优化",
            "有高并发系统设计经验",
            "熟悉分布式理论（CAP/BASE）",
        ],
        "soft_requirements": [
            "具备技术方案文档撰写能力",
            "良好的跨团队沟通协作",
            "有技术指导意愿",
        ],
        "evaluation_dimensions": [
            {
                "dimension": "技术深度",
                "weight": 0.35,
                "must_have": "能深入讲解 JVM 和分布式事务",
                "key_questions": ["JVM 调优实战", "分布式事务选型"],
                "red_flags": ["无法解释线上 OOM 排查"],
            },
            {
                "dimension": "系统设计",
                "weight": 0.30,
                "must_have": "能独立完成中大型系统架构设计",
                "key_questions": ["设计一个高并发订单系统"],
                "red_flags": ["只会 CRUD 设计"],
            },
            {
                "dimension": "项目经验",
                "weight": 0.20,
                "must_have": "主导过至少 2 个核心项目",
                "key_questions": ["项目难点与决策"],
                "red_flags": ["描述空洞无细节"],
            },
            {
                "dimension": "团队协作",
                "weight": 0.15,
                "must_have": "能有效推动跨团队合作",
                "key_questions": ["处理分歧的案例"],
                "red_flags": ["无法举出协作实例"],
            },
        ],
        "salary_band": {
            "base_min": 40000, "base_max": 55000,
            "total_min": 600000, "total_max": 800000,
            "currency": "CNY", "period": "monthly",
        },
        "interview_focus": [
            "验证主导程度而非参与程度",
            "观察系统思维而非单一知识点",
        ],
    },
    {
        "code": "FE_P7",
        "title": "高级前端工程师",
        "level": "P7",
        "department": "技术部",
        "description": "负责前端架构设计与核心模块开发，推动前端工程化。",
        "hard_requirements": [
            "5年以上前端开发经验",
            "精通 React/Vue 等主流框架原理",
            "熟悉前端性能优化与监控体系",
            "有 TypeScript 大型项目经验",
            "熟悉 Node.js 全栈开发",
        ],
        "soft_requirements": [
            "良好的 UI/UX 敏感度",
            "能推动前端技术规范落地",
            "具备技术分享能力",
        ],
        "evaluation_dimensions": [
            {
                "dimension": "框架深度",
                "weight": 0.30,
                "must_have": "理解 React/Vue 核心机制和 diff 算法",
                "key_questions": ["虚拟 DOM 设计取舍", "响应式原理"],
                "red_flags": ["只会用不会写原理"],
            },
            {
                "dimension": "工程化能力",
                "weight": 0.25,
                "must_have": "能搭建完整的前端 CI/CD 体系",
                "key_questions": ["构建工具链设计"],
                "red_flags": ["未接触过工程化"],
            },
            {
                "dimension": "性能优化",
                "weight": 0.25,
                "must_have": "能定位并解决复杂性能问题",
                "key_questions": ["首屏优化方案", "内存泄漏排查"],
                "red_flags": ["只背过优化 checklist"],
            },
            {
                "dimension": "项目管理",
                "weight": 0.20,
                "must_have": "能独立管理前端项目交付",
                "key_questions": ["进度把控与风险识别"],
                "red_flags": ["只能执行不能规划"],
            },
        ],
        "salary_band": {
            "base_min": 35000, "base_max": 50000,
            "total_min": 500000, "total_max": 700000,
            "currency": "CNY", "period": "monthly",
        },
        "interview_focus": [
            "关注技术选型思辨而非背诵",
            "观察对用户体验的理解深度",
        ],
    },
    {
        "code": "PM_P7",
        "title": "高级产品经理",
        "level": "P7",
        "department": "产品部",
        "description": "负责产品线规划与需求管理，驱动产品迭代。",
        "hard_requirements": [
            "5年以上产品经理经验",
            "精通需求分析与 PRD 撰写",
            "有数据驱动决策经验",
            "熟悉 A/B 测试与用户研究方法",
            "有跨团队推动能力",
        ],
        "soft_requirements": [
            "优秀的逻辑与结构化思维",
            "良好的用户同理心",
            "具备数据分析基础能力",
        ],
        "evaluation_dimensions": [
            {
                "dimension": "产品思维",
                "weight": 0.30,
                "must_have": "能从用户价值出发设计产品方案",
                "key_questions": ["设计一个增长实验"],
                "red_flags": ["只会堆功能"],
            },
            {
                "dimension": "数据分析",
                "weight": 0.25,
                "must_have": "能用数据验证产品假设",
                "key_questions": ["数据异动归因"],
                "red_flags": ["看不懂核心指标"],
            },
            {
                "dimension": "项目管理",
                "weight": 0.25,
                "must_have": "能独立推动复杂项目按时交付",
                "key_questions": ["多项目优先级管理"],
                "red_flags": ["经常延期"],
            },
            {
                "dimension": "沟通协作",
                "weight": 0.20,
                "must_have": "能与技术/设计/运营高效协同",
                "key_questions": ["处理需求冲突案例"],
                "red_flags": ["无法说服团队"],
            },
        ],
        "salary_band": {
            "base_min": 35000, "base_max": 50000,
            "total_min": 500000, "total_max": 700000,
            "currency": "CNY", "period": "monthly",
        },
        "interview_focus": [
            "关注问题定义而非解决方案",
            "观察数据素养而非直觉判断",
        ],
    },
    {
        "code": "AI_P7",
        "title": "AI 算法工程师",
        "level": "P7",
        "department": "AI 部",
        "description": "负责 AI 模型研发与落地，包括 NLP/CV/推荐系统。",
        "hard_requirements": [
            "5年以上 AI 算法研发经验",
            "精通深度学习框架（PyTorch/TF）",
            "有模型部署与 MLOps 经验",
            "扎实的数学基础（线性代数/概率论）",
            "在顶会或核心业务上有落地成果",
        ],
        "soft_requirements": [
            "良好的工程习惯",
            "能阅读英文论文并复现",
            "具备技术判断力",
        ],
        "evaluation_dimensions": [
            {
                "dimension": "算法深度",
                "weight": 0.35,
                "must_have": "理解主流模型原理与适用场景",
                "key_questions": ["Transformer 自注意力机制"],
                "red_flags": ["只会调包不懂原理"],
            },
            {
                "dimension": "工程能力",
                "weight": 0.25,
                "must_have": "能独立完成模型训练→部署全链路",
                "key_questions": ["模型 Serving 方案设计"],
                "red_flags": ["只做过 offline 实验"],
            },
            {
                "dimension": "业务理解",
                "weight": 0.20,
                "must_have": "能将业务问题转化为算法问题",
                "key_questions": ["业务指标到损失函数"],
                "red_flags": ["不关心业务效果"],
            },
            {
                "dimension": "创新能力",
                "weight": 0.20,
                "must_have": "有从论文到落地的创新案例",
                "key_questions": ["改进 baseline 的方法"],
                "red_flags": ["完全复制开源方案"],
            },
        ],
        "salary_band": {
            "base_min": 45000, "base_max": 65000,
            "total_min": 650000, "total_max": 900000,
            "currency": "CNY", "period": "monthly",
        },
        "interview_focus": [
            "关注对 AI 本质的理解而非花哨 demo",
            "观察工程思维与实验严谨性",
        ],
    },
    {
        "code": "SRE_P7",
        "title": "高级 SRE 工程师",
        "level": "P7",
        "department": "基础架构部",
        "description": "负责生产环境稳定性保障与可观测性体系建设。",
        "hard_requirements": [
            "5年以上运维/ SRE 经验",
            "精通 Linux 内核与网络协议栈",
            "有大规模 K8s 集群管理经验",
            "熟悉可观测性技术栈（Prometheus/Grafana/ELK）",
            "有故障应急与复盘能力",
        ],
        "soft_requirements": [
            "强烈的运维责任心",
            "能编写自动化工具",
            "良好的 on-call 意识",
        ],
        "evaluation_dimensions": [
            {
                "dimension": "基础设施",
                "weight": 0.30,
                "must_have": "理解分布式系统可靠设计",
                "key_questions": ["K8s 调度原理", "etcd 故障场景"],
                "red_flags": ["只会 YAML 不会排障"],
            },
            {
                "dimension": "监控体系",
                "weight": 0.25,
                "must_have": "能设计完整可观测性方案",
                "key_questions": ["Metrics/Logging/Tracing 选型"],
                "red_flags": ["只会配告警"],
            },
            {
                "dimension": "自动化",
                "weight": 0.25,
                "must_have": "能编写工具减少人工操作",
                "key_questions": ["故障自愈方案设计"],
                "red_flags": ["习惯手动操作"],
            },
            {
                "dimension": "安全意识",
                "weight": 0.20,
                "must_have": "具备基础安全防护意识",
                "key_questions": ["供应链安全"],
                "red_flags": ["从不关注安全"],
            },
        ],
        "salary_band": {
            "base_min": 40000, "base_max": 55000,
            "total_min": 600000, "total_max": 800000,
            "currency": "CNY", "period": "monthly",
        },
        "interview_focus": [
            "关注故障响应思路而非工具会多少",
            "观察对可靠性的理解深度",
        ],
    },
    {
        "code": "HRBP_M2",
        "title": "HRBP 经理",
        "level": "M2",
        "department": "人力资源部",
        "description": "作为业务伙伴支持技术团队的人力资源管理工作。",
        "hard_requirements": [
            "5年以上 HRBP 经验",
            "精通绩效管理与人才盘点",
            "熟悉组织发展(OD)方法论",
            "有技术团队支持经验",
            "具备劳动法基础",
        ],
        "soft_requirements": [
            "极强的同理心与沟通能力",
            "能处理复杂人际关系",
            "具备商业敏感度",
        ],
        "evaluation_dimensions": [
            {
                "dimension": "业务理解",
                "weight": 0.30,
                "must_have": "能理解技术团队的业务逻辑",
                "key_questions": ["如何评估技术团队效能"],
                "red_flags": ["只懂 HR 不懂业务"],
            },
            {
                "dimension": "人才管理",
                "weight": 0.30,
                "must_have": "能独立完成人才梯队建设",
                "key_questions": ["人才盘点方法论"],
                "red_flags": ["只会执行总部制度"],
            },
            {
                "dimension": "组织发展",
                "weight": 0.20,
                "must_have": "能诊断组织问题并提出改进方案",
                "key_questions": ["组织架构调整案例"],
                "red_flags": ["没有 OD 经验"],
            },
            {
                "dimension": "沟通影响",
                "weight": 0.20,
                "must_have": "能在复杂场景下有效沟通",
                "key_questions": ["处理员工关系的案例"],
                "red_flags": ["回避冲突"],
            },
        ],
        "salary_band": {
            "base_min": 30000, "base_max": 45000,
            "total_min": 450000, "total_max": 600000,
            "currency": "CNY", "period": "monthly",
        },
        "interview_focus": [
            "关注商业理解而非 HR 流程",
            "观察组织敏感度",
        ],
    },
]


async def seed() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    created = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        for data in PROFILES:
            code = data["code"]
            existing = await db.execute(select(JobProfile).where(JobProfile.code == code))
            if existing.scalar_one_or_none() is not None:
                logger.info("  ⏭️   %s — 已存在", code)
                skipped += 1
                continue

            profile = JobProfile(
                id=str(uuid.uuid4()),
                code=data["code"],
                title=data["title"],
                level=data["level"],
                department=data["department"],
                description=data.get("description"),
                hard_requirements=data["hard_requirements"],
                soft_requirements=data["soft_requirements"],
                evaluation_dimensions=data["evaluation_dimensions"],
                salary_band=data["salary_band"],
                interview_focus=data.get("interview_focus", []),
                is_active=True,
            )
            db.add(profile)

            version = JobProfileVersion(
                id=str(uuid.uuid4()),
                job_profile_id=profile.id,
                version=1,
                status=JobProfileVersionStatus.ACTIVE,
                change_reason="初始 seed 版本",
                snapshot={
                    "code": profile.code,
                    "title": profile.title,
                    "level": profile.level,
                    "department": profile.department,
                    "description": profile.description,
                    "hard_requirements": profile.hard_requirements,
                    "soft_requirements": profile.soft_requirements,
                    "evaluation_dimensions": profile.evaluation_dimensions,
                    "salary_band": profile.salary_band,
                    "interview_focus": profile.interview_focus,
                },
                created_by="system-seed",
                activated_by="system-seed",
            )
            db.add(version)
            created += 1

        await db.commit()

    logger.info("Seed 完成: created=%d, skipped=%d", created, skipped)


def main() -> int:
    asyncio.run(seed())
    return 0


if __name__ == "__main__":
    sys.exit(main())
