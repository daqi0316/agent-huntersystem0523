"""M1-2: job profiles and Java_P7 seed.

Revision ID: m1_2_job_profiles
Revises: m1_1_candidate_recruitment_state
Create Date: 2026-06-08 00:00:00.000000
"""

from typing import Sequence, Union

import json
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "m1_2_job_profiles"
down_revision: Union[str, Sequence[str], None] = "m1_1_candidate_recruitment_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JAVA_P7_PROFILE = {
    "hard_requirements": [
        "本科及以上，计算机相关专业",
        "5年以上 Java 开发经验",
        "有高并发系统实战经验（QPS>1K）",
        "熟悉 Spring Cloud 或 Dubbo 微服务框架",
    ],
    "soft_requirements": [
        "能独立负责模块设计和开发",
        "有跨团队协作经验",
        "对技术有热情，有技术博客或开源贡献优先",
    ],
    "evaluation_dimensions": [
        {
            "dimension": "技术深度",
            "weight": 0.30,
            "must_have": "能深入讲解至少2个技术点的原理和实战经验",
            "key_questions": ["JVM 调优", "GC 算法", "分布式事务", "缓存策略"],
            "scoring_guide": [
                {"score": 5, "evidence": "能深入讲解 JVM 调优、GC 算法选择、线上问题排查"},
                {"score": 4, "evidence": "熟悉常用框架原理，能排查常见问题"},
                {"score": 3, "evidence": "能完成日常开发，但对原理理解不深"},
                {"score": 2, "evidence": "仅了解基本概念，缺乏实战经验"},
                {"score": 1, "evidence": "无法解释核心技术原理或线上问题处理"},
            ],
            "red_flags": ["只能描述 CRUD 工作", "无法解释项目瓶颈和技术取舍"],
        },
        {
            "dimension": "项目经验",
            "weight": 0.25,
            "must_have": "主导过至少1个中大型项目",
            "key_questions": ["交易系统重构", "团队分工", "架构取舍"],
            "scoring_guide": [
                {"score": 5, "evidence": "能画出架构演进和团队分工，清楚说明本人决策"},
                {"score": 3, "evidence": "能描述项目流程，但主导程度证据不足"},
                {"score": 1, "evidence": "项目描述模糊，无法说明具体职责"},
            ],
            "red_flags": ["声称主导但无法说明团队规模", "贡献描述前后不一致"],
        },
        {
            "dimension": "学习能力",
            "weight": 0.15,
            "must_have": "有持续学习证据",
            "key_questions": ["K8s 短板如何补齐", "最近学习的技术"],
            "scoring_guide": [
                {"score": 5, "evidence": "有明确学习计划和实践证据"},
                {"score": 3, "evidence": "有学习意愿但计划模糊"},
                {"score": 1, "evidence": "只表示可以学，无具体行动"},
            ],
            "red_flags": ["对新技术明显抗拒", "无持续学习证据"],
        },
        {
            "dimension": "文化匹配",
            "weight": 0.15,
            "must_have": "能跨团队协作，符合客户第一和团队协作价值观",
            "key_questions": ["跨团队冲突处理", "对前团队评价"],
            "scoring_guide": [
                {"score": 5, "evidence": "能客观复盘冲突并说明协作动作"},
                {"score": 3, "evidence": "能配合团队但主动性一般"},
                {"score": 1, "evidence": "过度负面评价前公司或前领导"},
            ],
            "red_flags": ["过度自我", "对前公司负面评价过多"],
        },
        {
            "dimension": "潜力",
            "weight": 0.15,
            "must_have": "有成长为 P8 的技术影响力或带团队潜力",
            "key_questions": ["技术影响力", "带人经验", "未来半年成长计划"],
            "scoring_guide": [
                {"score": 5, "evidence": "有技术博客、开源、分享或带人结果"},
                {"score": 3, "evidence": "具备成长意愿但影响力证据一般"},
                {"score": 1, "evidence": "缺少成长目标和影响力证据"},
            ],
            "red_flags": ["目标岗位要求带人但完全无协作牵头经验"],
        },
    ],
    "salary_band": {
        "base_min": 40000,
        "base_max": 50000,
        "total_min": 600000,
        "total_max": 800000,
        "currency": "CNY",
        "period": "monthly",
    },
    "interview_focus": [
        "验证高并发项目中的真实职责",
        "追问分布式事务和缓存策略的实战细节",
        "核实 K8s/云原生短板是否可通过学习补齐",
        "识别项目经验包装和主导程度夸大",
    ],
}


def upgrade() -> None:
    op.create_table(
        "job_profiles",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hard_requirements", sa.JSON(), nullable=False),
        sa.Column("soft_requirements", sa.JSON(), nullable=False),
        sa.Column("evaluation_dimensions", sa.JSON(), nullable=False),
        sa.Column("salary_band", sa.JSON(), nullable=False),
        sa.Column("interview_focus", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_job_profiles_code"),
    )
    op.create_index("ix_job_profiles_code", "job_profiles", ["code"])
    op.create_index("ix_job_profiles_title", "job_profiles", ["title"])
    op.create_index("ix_job_profiles_level", "job_profiles", ["level"])
    op.create_index("ix_job_profiles_is_active", "job_profiles", ["is_active"])

    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO job_profiles (
                id, code, title, level, department, description,
                hard_requirements, soft_requirements, evaluation_dimensions,
                salary_band, interview_focus, is_active, created_at, updated_at
            ) VALUES (
                CAST(:id AS UUID), :code, :title, :level, :department, :description,
                CAST(:hard_requirements AS JSON), CAST(:soft_requirements AS JSON),
                CAST(:evaluation_dimensions AS JSON), CAST(:salary_band AS JSON),
                CAST(:interview_focus AS JSON), true, now(), now()
            )
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {
            "id": "11111111-1111-1111-1111-111111111107",
            "code": "Java_P7",
            "title": "高级 Java 工程师",
            "level": "P7",
            "department": "技术部-后端架构组",
            "description": "面向高并发后端架构与核心交易系统的高级 Java 岗位画像",
            "hard_requirements": json.dumps(JAVA_P7_PROFILE["hard_requirements"], ensure_ascii=False),
            "soft_requirements": json.dumps(JAVA_P7_PROFILE["soft_requirements"], ensure_ascii=False),
            "evaluation_dimensions": json.dumps(JAVA_P7_PROFILE["evaluation_dimensions"], ensure_ascii=False),
            "salary_band": json.dumps(JAVA_P7_PROFILE["salary_band"], ensure_ascii=False),
            "interview_focus": json.dumps(JAVA_P7_PROFILE["interview_focus"], ensure_ascii=False),
        },
    )


def downgrade() -> None:
    op.drop_index("ix_job_profiles_is_active", table_name="job_profiles")
    op.drop_index("ix_job_profiles_level", table_name="job_profiles")
    op.drop_index("ix_job_profiles_title", table_name="job_profiles")
    op.drop_index("ix_job_profiles_code", table_name="job_profiles")
    op.drop_table("job_profiles")
