"""arq 队列集成 — Redis 持久化异步任务 + cron 定时任务"""
from __future__ import annotations

import logging

from arq import cron
from arq.connections import RedisSettings

from app.sourcing.config import sourcing_settings

logger = logging.getLogger(__name__)


async def crawl_task(ctx, task_id: str):
    """采集任务 - arq 保证持久化"""
    orchestrator = ctx["orchestrator"]
    task = await orchestrator.get_task(task_id)
    if not task:
        return {"skipped": True, "reason": "task_not_found"}
    if task.status != "pending":
        return {"skipped": True, "reason": f"status_is_{task.status}"}
    await orchestrator.execute_task(task)
    return {"completed": True, "task_id": task_id}


async def analyze_candidates(ctx, candidate_ids: list[str], jd_id: str | None = None):
    """AI 分析任务（P4）— 技能提取/标准化 + 职业轨迹 + 摘要生成 + 可选 JD 匹配"""
    logger.info("Analyze candidates: %d candidates, jd=%s", len(candidate_ids), jd_id)

    from app.core.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.models.candidate import Candidate
    from app.llm import get_llm_client
    from app.sourcing.analyze_agent import analyze_candidate, match_candidate_to_jd
    from app.sourcing.vector_store import index_candidate_skills, ensure_skill_collection

    llm = get_llm_client()
    jd_text = None
    jd_requirements = None

    if jd_id:
        try:
            from app.models.job_position import JobPosition
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(JobPosition).where(JobPosition.id == jd_id))
                jd = result.scalar_one_or_none()
                if jd:
                    jd_text = jd.description
                    jd_requirements = jd.requirements
        except Exception as e:
            logger.warning("Failed to load JD %s: %s", jd_id, e)

    try:
        await ensure_skill_collection()
    except Exception as e:
        logger.warning("Failed to ensure skill collection: %s", e)

    analyzed = 0
    matched = 0
    errors = 0

    for cid in candidate_ids:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Candidate).where(Candidate.id == cid))
                candidate = result.scalar_one_or_none()
                if not candidate:
                    continue

                candidate_dict = {
                    "id": candidate.id,
                    "name": candidate.name,
                    "current_title": candidate.current_title,
                    "current_company": candidate.current_company,
                    "location": candidate.location,
                    "salary": candidate.salary,
                    "experience_years": candidate.experience_years,
                    "education": candidate.education,
                    "skills": candidate.skills,
                    "summary": candidate.summary,
                    "raw_data": candidate.raw_data,
                }

                analysis = await analyze_candidate(candidate_dict, llm=llm)
                candidate.ai_analysis = analysis

                if jd_text:
                    match_result = await match_candidate_to_jd(
                        candidate_dict, analysis, jd_text, jd_requirements, llm=llm,
                    )
                    candidate.match_scores = {jd_id: match_result} if jd_id else match_result

                skill_text = ", ".join(analysis.get("skills_extracted") or candidate.skills or [])
                if skill_text:
                    try:
                        await index_candidate_skills(
                            candidate_id=candidate.id,
                            skill_text=skill_text,
                            payload={
                                "name": candidate.name,
                                "current_title": candidate.current_title,
                                "current_company": candidate.current_company,
                                "skills": candidate.skills,
                            },
                        )
                    except Exception as e:
                        logger.warning("Failed to index skills for %s: %s", cid, e)

                await db.commit()
                analyzed += 1
                if jd_text:
                    matched += 1

        except Exception as e:
            logger.exception("Failed to analyze candidate %s: %s", cid, e)
            errors += 1

    logger.info("Analyze candidates done: %d analyzed, %d matched, %d errors", analyzed, matched, errors)
    return {"analyzed": analyzed, "matched": matched, "errors": errors}


# P3-3: 定时健康探测
async def health_probe_cron(ctx):
    """每 30 分钟探测所有平台 + 代理池健康"""
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.sourcing.health_probe import probe_platform_health
    from app.sourcing.proxy_pool import ProxyPool

    try:
        async with AsyncSessionLocal() as db:
            results = await probe_platform_health(db)
            failed = [k for k, v in results.items() if v.get("status") == "down"]
            if failed:
                logger.warning("Health probe: platforms down: %s", failed)

        from app.core.redis import get_redis
        redis = await get_redis()
        pool = ProxyPool(redis=redis)
        health = await pool.run_health_check()
        logger.info("Proxy health check: %d alive, %d removed", health.get("alive", 0), health.get("removed", 0))

        from app.sourcing.orchestrator import proxy_pool_size
        proxy_counts = await pool.health_check()
        for tier_key, count in proxy_counts.items():
            proxy_pool_size.labels(tier=tier_key).set(count)

    except Exception as e:
        logger.exception("Health probe cron failed: %s", e)


# P3-2: 账号预热
async def account_warming_cron(ctx):
    """每 6 小时执行一次账号预热"""
    try:
        from app.core.database import AsyncSessionLocal
        from app.core.redis import get_redis
        async with AsyncSessionLocal() as db:
            redis = await get_redis()
            from app.sourcing.account_warming import run_account_warming
            await run_account_warming(db, redis)
    except Exception as e:
        logger.exception("Account warming cron failed: %s", e)


class WorkerSettings:
    functions = [crawl_task, analyze_candidates, health_probe_cron, account_warming_cron]
    cron_jobs = [
        cron(health_probe_cron, minute={0, 30}, description="平台健康探测 30min"),
        cron(account_warming_cron, hour={0, 6, 12, 18}, minute=0, description="账号预热 6h"),
    ]
    redis_settings = RedisSettings(host="localhost", port=6379, database=sourcing_settings.arq_redis_db)
    keep_result = 86400
    keep_result_failed = 86400
    max_tries = sourcing_settings.arq_max_tries
    max_retry_delay = 300
    job_timeout = sourcing_settings.arq_job_timeout
    concurrency = sourcing_settings.arq_concurrency
