"""采集候选人 API (P0-9)"""
from __future__ import annotations

from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal
from app.sourcing.schemas.candidate import CandidateMergeRequest, SourcingCandidateDetailResponse

router = APIRouter(tags=["sourcing/candidates"])


@router.get("")
async def list_sourcing_candidates(
    task_id: str | None = None,
    platform: str | None = None,
    skill: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    from app.sourcing.schemas.candidate import SourcingCandidateResponse
    from app.models.candidate import Candidate

    async with AsyncSessionLocal() as db:
        query = select(Candidate).where(Candidate.sourcing_task_id.isnot(None))
        count_query = select(Candidate.id).where(Candidate.sourcing_task_id.isnot(None))

        if task_id:
            query = query.where(Candidate.sourcing_task_id == task_id)
            count_query = count_query.where(Candidate.sourcing_task_id == task_id)
        if skill:
            query = query.where(Candidate.skills.any(skill))  # pyright: ignore[reportArgumentType]
            count_query = count_query.where(Candidate.skills.any(skill))  # pyright: ignore[reportArgumentType]

        total = (await db.execute(count_query)).scalar() or 0
        query = query.order_by(Candidate.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = await db.execute(query)
        candidates = result.scalars().all()

    return {
        "success": True,
        "data": [SourcingCandidateResponse.model_validate(c).model_dump() for c in candidates],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/{candidate_id}")
async def get_sourcing_candidate(candidate_id: str):
    from app.sourcing.schemas.candidate import SourcingCandidateDetailResponse
    from app.models.candidate import Candidate

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
        candidate = result.scalar_one_or_none()

    if not candidate or not candidate.sourcing_task_id:
        raise HTTPException(status_code=404, detail="采集候选人不存在")
    return {
        "success": True,
        "data": SourcingCandidateDetailResponse.model_validate(candidate).model_dump(),
    }


@router.post("/{candidate_id}/analyze")
async def analyze_sourcing_candidate(candidate_id: str, jd_id: str | None = None):
    """AI 分析单个候选人：技能提取 + 职业轨迹 + 摘要（可选 JD 匹配）
    
    同步执行，返回分析结果。
    """
    from app.models.candidate import Candidate
    from app.llm import get_llm_client
    from app.sourcing.analyze_agent import analyze_candidate, match_candidate_to_jd
    from app.sourcing.vector_store import index_candidate_skills

    llm = get_llm_client()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
        candidate = result.scalar_one_or_none()

    if not candidate or not candidate.sourcing_task_id:
        raise HTTPException(status_code=404, detail="采集候选人不存在")

    candidate_dict = {
        "id": candidate.id, "name": candidate.name,
        "current_title": candidate.current_title,
        "current_company": candidate.current_company,
        "location": candidate.location, "salary": candidate.salary,
        "experience_years": candidate.experience_years,
        "education": candidate.education, "skills": candidate.skills,
        "summary": candidate.summary, "raw_data": candidate.raw_data,
    }

    analysis = await analyze_candidate(candidate_dict, llm=llm)

    match_result = None
    if jd_id:
        from app.models.job_position import JobPosition
        async with AsyncSessionLocal() as db2:
            jd_result = await db2.execute(select(JobPosition).where(JobPosition.id == jd_id))
            jd = jd_result.scalar_one_or_none()
        if jd:
            jd_text = (jd.description or "") + "\n" + (jd.requirements or "")
            match_result = await match_candidate_to_jd(candidate_dict, analysis, jd_text, llm=llm)

    async with AsyncSessionLocal() as db3:
        c = await db3.get(Candidate, candidate_id)
        if c:
            c.ai_analysis = analysis
            if match_result:
                c.match_scores = {jd_id: match_result} if jd_id else match_result
            await db3.commit()

    skill_text = ", ".join(analysis.get("skills_extracted") or candidate.skills or [])
    if skill_text:
        import asyncio
        asyncio.ensure_future(index_candidate_skills(
            candidate_id=candidate.id, skill_text=skill_text,
            payload={"name": candidate.name, "current_title": candidate.current_title,
                     "current_company": candidate.current_company, "skills": candidate.skills},
        ))

    return {
        "success": True,
        "data": {
            "analysis": analysis,
            "match_score": match_result,
        },
    }


@router.post("/batch-analyze")
async def batch_analyze_candidates(candidate_ids: list[str], jd_id: str | None = None):
    """批量 AI 分析候选人（入 arq 队列，异步执行）"""
    from arq import create_pool
    from app.sourcing.config import sourcing_settings
    pool = await create_pool(RedisSettings(host="localhost", port=6379, database=sourcing_settings.arq_redis_db))
    try:
        job = await pool.enqueue_job("analyze_candidates", candidate_ids=candidate_ids, jd_id=jd_id)
    finally:
        await pool.close()
    if not job:
        raise HTTPException(status_code=500, detail="批量分析入队失败")
    return {
        "success": True,
        "data": {"job_id": job.job_id, "count": len(candidate_ids), "queued": True},
    }


@router.post("/merge")
async def merge_candidates(body: CandidateMergeRequest):
    """合并多个候选人（多源去重后合并 raw_data / skills / source_urls）"""
    from app.models.candidate import Candidate

    all_ids = [body.primary_id, *body.merge_ids]
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Candidate).where(Candidate.id.in_(all_ids)))
        records = {r.id: r for r in result.scalars().all()}

        if body.primary_id not in records:
            raise HTTPException(status_code=404, detail="主候选人不存在")
        missing = [i for i in body.merge_ids if i not in records]
        if missing:
            raise HTTPException(status_code=404, detail=f"被合并候选人不存在: {missing}")

        primary = records[body.primary_id]

        merged_raw = dict(primary.raw_data or {})
        merged_skills = set(primary.skills or [])
        merged_platforms = set(primary.source_platforms or [])
        merged_urls = dict(primary.source_urls or {})

        for mid in body.merge_ids:
            rec = records[mid]
            # 合并 raw_data
            if rec.raw_data:
                for k, v in rec.raw_data.items():
                    merged_raw[k] = v
            # 合并 skills
            if rec.skills:
                merged_skills.update(rec.skills)
            # 合并 platforms
            if rec.source_platforms:
                merged_platforms.update(rec.source_platforms)
            # 合并 urls
            if rec.source_urls:
                merged_urls.update(rec.source_urls)

        primary.raw_data = merged_raw
        primary.skills = sorted(merged_skills)
        primary.source_platforms = sorted(merged_platforms)
        primary.source_urls = merged_urls

        for mid in body.merge_ids:
            await db.delete(records[mid])

        await db.commit()
        await db.refresh(primary)

    return {
        "success": True,
        "data": SourcingCandidateDetailResponse.model_validate(primary).model_dump(),
    }
