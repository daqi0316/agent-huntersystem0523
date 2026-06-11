"""P4-2: 候选人技能向量化 + Qdrant 存储"""
from __future__ import annotations

import logging

from app.core.qdrant import get_qdrant
from app.llm import get_llm_client
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

CANDIDATE_SKILLS_COLLECTION = "candidate_skills"


async def get_skill_vector_store() -> QdrantService:
    """获取候选人技能向量存储服务（自动创建 collection）"""
    client = await get_qdrant()
    svc = QdrantService(client=client, collection=CANDIDATE_SKILLS_COLLECTION)
    return svc


async def ensure_skill_collection():
    """确保 candidate_skills collection 存在（idempotent）"""
    client = await get_qdrant()
    svc = QdrantService(client=client, collection=CANDIDATE_SKILLS_COLLECTION)

    # 获取 embedding 维度
    llm = get_llm_client()
    test_vec = await llm.embed("test")
    if not test_vec:
        logger.warning("Failed to get embedding dimension, using default 1024")
        vector_size = 1024
    else:
        vector_size = len(test_vec)

    await svc.ensure_collection(vector_size)
    logger.info("Candidate skills collection ready (dim=%d)", vector_size)
    return svc


async def index_candidate_skills(candidate_id: str, skill_text: str, payload: dict | None = None):
    """将候选人技能嵌入向量并存入 Qdrant

    Args:
        candidate_id: 候选人 ID
        skill_text: 用于向量化的技能文本（如 "python, react, docker, aws"）
        payload: 附加 payload（如 name, current_title, current_company 等）
    """
    llm = get_llm_client()
    vector = await llm.embed(skill_text)
    if not vector:
        logger.warning("Empty embedding for candidate %s, skipping index", candidate_id)
        return

    svc = await get_skill_vector_store()
    await svc.upsert(
        point_id=candidate_id,
        vector=vector,
        payload=payload or {},
    )
    logger.info("Indexed candidate %s skills in Qdrant", candidate_id)


async def search_similar_candidates(
    skill_text: str,
    top_k: int = 20,
    score_threshold: float | None = None,
) -> list[dict]:
    """按技能文本搜索相似候选人

    Args:
        skill_text: 技能文本（如 "python backend distributed systems"）
        top_k: 返回数量
        score_threshold: 分数阈值

    Returns:
        [{"id": str, "score": float, ...payload}, ...]
    """
    llm = get_llm_client()
    vector = await llm.embed(skill_text)
    if not vector:
        logger.warning("Empty embedding for search query")
        return []

    svc = await get_skill_vector_store()
    return await svc.search(vector=vector, top_k=top_k, score_threshold=score_threshold)


async def delete_candidate_skills(candidate_id: str):
    """删除候选人的技能向量"""
    svc = await get_skill_vector_store()
    await svc.delete(point_id=candidate_id)
