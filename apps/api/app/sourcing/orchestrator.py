"""任务编排 — P0-P2 唯一入口（P1 完整版：增量采集 / 去重入库 / RecoveryExecutor / 指标埋点）"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arq import create_pool
from arq.connections import RedisSettings

from app.models.candidate import Candidate
from app.sourcing.config import sourcing_settings
from app.sourcing.dedup import generate_fingerprint, is_already_crawled, mark_crawled
from app.sourcing.models.crawl_log import CrawlLog, CrawlStatus
from app.sourcing.models.sourcing_task import SourcingTask, SourcingTaskStatus
from app.sourcing.platforms.base import CrawlResult, get_adapter, load_platform_config_from_db
from app.sourcing.ws_manager import ws_manager

logger = logging.getLogger(__name__)

# ── P1-12: Prometheus 指标 ──

crawl_total = Counter("sourcing_crawl_total", "总采集请求数", ["platform", "status"])
crawl_duration = Histogram(
    "sourcing_crawl_duration_seconds", "采集耗时(秒)", ["platform"],
    buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120),
)
proxy_pool_size = Gauge("sourcing_proxy_pool_size", "可用代理数", ["tier"])
active_accounts = Gauge("sourcing_account_active", "可用账号数", ["platform", "status"])
task_queue_depth = Gauge("sourcing_task_queue_depth", "排队任务数")

# ── P1-10: RecoveryExecutor ──


class RecoveryExecutor:
    """带恢复逻辑的采集执行器 — 错误分类 / 指数退避 / 代理切换 / 账号轮换"""

    MAX_RETRIES = 3
    BACKOFF_BASE = 10  # 退避基数(秒)
    ERROR_STRATEGIES: dict[str, str] = {
        "IP_BANNED": "switch_proxy",
        "ACCOUNT_BANNED": "switch_account",
        "CAPTCHA": "attempt_solve",
        "RATE_LIMITED": "backoff",
        "QUOTA_EXCEEDED": "switch_account",
        "TIMEOUT": "retry",
        "PARSE_ERROR": "skip",
    }

    def __init__(self, proxy_pool=None, account_manager=None):
        self.proxy_pool = proxy_pool
        self.account_manager = account_manager

    async def execute(
        self,
        platform: str,
        keyword: str,
        filters: dict[str, Any] | None = None,
        adapter_config: dict[str, Any] | None = None,
    ) -> CrawlResult:
        """带多层恢复的采集执行"""
        filters = filters or {}
        last_error: str | None = None
        captcha_triggered = False
        proxy_used: str | None = None

        platform_cfgs = await load_platform_config_from_db()
        base_cfg = platform_cfgs.get(platform, {})
        merged_cfg = {**base_cfg.get("config", {}), **(adapter_config or {})}

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                adapter_cls = get_adapter(platform)
                adapter = adapter_cls(config=merged_cfg, proxy_pool=self.proxy_pool)

                # 传入 account_manager
                if hasattr(adapter, "account_manager"):
                    adapter.account_manager = self.account_manager  # type: ignore[attr-defined]

                result = await adapter.search(keyword, **filters)

                if result.success:
                    if result.proxy_used and self.proxy_pool:
                        latency = result.rate_limit_info.get("latency_ms") if result.rate_limit_info else None
                        await self.proxy_pool.report_success(
                            result.proxy_used, platform, latency_ms=latency
                        )
                    return result

                # 失败 → 按错误类型恢复
                if result.captcha_triggered:
                    captcha_triggered = True
                    strategy = "attempt_solve"
                elif result.error_message:
                    strategy = self._classify_error(result.error_message)
                else:
                    strategy = "retry"

                await self._apply_strategy(strategy, platform, result, adapter)

                # 指数退避
                if strategy in ("backoff", "retry", "switch_proxy", "switch_account"):
                    delay = self.BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, 10)
                    logger.info("Retry %d/%d for %s after %.0fs (%s)", attempt, self.MAX_RETRIES, platform, delay, strategy)
                    await asyncio.sleep(delay)

                last_error = result.error_message
                proxy_used = result.proxy_used

            except NotImplementedError:
                return CrawlResult(success=False, error_message="not_implemented")
            except Exception as e:
                last_error = str(e)
                logger.exception("RecoveryExecutor attempt %d failed: %s", attempt, e)
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.BACKOFF_BASE * (2 ** (attempt - 1)))

        return CrawlResult(
            success=False,
            candidates=[],
            error_message=f"All retries exhausted: {last_error}",
            captcha_triggered=captcha_triggered,
            proxy_used=proxy_used,
        )

    def _classify_error(self, error_message: str) -> str:
        err = error_message.lower()
        if any(w in err for w in ("ip", "403", "forbidden", "受限", "被封")):
            return "IP_BANNED"
        if any(w in err for w in ("login", "未登录", "登录", "account", "auth")):
            return "ACCOUNT_BANNED"
        if any(w in err for w in ("429", "too many", "rate", "限流", "频繁")):
            return "RATE_LIMITED"
        if any(w in err for w in ("quota", "配额", "limited", "用完")):
            return "QUOTA_EXCEEDED"
        if any(w in err for w in ("timeout", "timed out")):
            return "TIMEOUT"
        if any(w in err for w in ("parse", "解析")):
            return "PARSE_ERROR"
        return "RETRY"

    async def _apply_strategy(self, strategy: str, platform: str, result: CrawlResult, adapter: Any):
        if strategy == "switch_proxy" and self.proxy_pool and result.proxy_used:
            await self.proxy_pool.report_failure(result.proxy_used, platform, "ip_banned")
        elif strategy == "switch_account" and self.account_manager:
            await self.account_manager.rotate(platform, "")
        elif strategy == "backoff":
            pass  # 调用方处理退避


# ── SourcingOrchestrator ──

class SourcingOrchestrator:
    """任务编排 — 协调采集、去重、入库流程"""

    def __init__(self, db: AsyncSession, redis, proxy_pool=None, account_manager=None):
        self.db = db
        self.redis = redis
        self.proxy_pool = proxy_pool
        self.account_manager = account_manager
        self._recovery = RecoveryExecutor(proxy_pool=proxy_pool, account_manager=account_manager)

    # ── P1-9: 创建 + 投递 ──

    async def create_and_dispatch(self, task_data: dict[str, object]) -> SourcingTask:
        """创建任务 + 推入 arq 队列"""
        task = SourcingTask(**task_data)
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        # 推入 arq
        try:
            pool = await create_pool(
                RedisSettings(host="localhost", port=6379, database=sourcing_settings.arq_redis_db)
            )
            await pool.enqueue_job("crawl_task", task_id=task.id)
        except Exception as e:
            logger.warning("Failed to enqueue task %s: %s", task.id, e)

        return task

    async def create_task(self, task_data: dict[str, object]) -> SourcingTask:
        """创建任务（不投递队列，兼容旧调用方）"""
        # 兼容前端未传 org_id/created_by 时的兜底
        safe_data = {k: v for k, v in task_data.items() if v is not None}
        safe_data.setdefault("org_id", "00000000-0000-0000-0000-000000000000")
        safe_data.setdefault("created_by", "system")
        task = SourcingTask(**safe_data)
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    # ── 查询 ──

    async def get_task(self, task_id: str) -> SourcingTask | None:
        result = await self.db.execute(
            select(SourcingTask).where(SourcingTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_task_list(
        self,
        status: str | None = None,
        platform: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[SourcingTask], int]:
        query = select(SourcingTask)
        count_query = select(SourcingTask.id)

        if status:
            query = query.where(SourcingTask.status == status)
            count_query = count_query.where(SourcingTask.status == status)
        if keyword:
            like = f"%{keyword}%"
            query = query.where(SourcingTask.keyword.ilike(like))
            count_query = count_query.where(SourcingTask.keyword.ilike(like))

        count_val = (await self.db.execute(count_query)).scalar()
        total = count_val if isinstance(count_val, int) else 0

        sort_col = getattr(SourcingTask, sort_by, SourcingTask.created_at)
        order_fn = sort_col.desc if sort_order == "desc" else sort_col.asc
        query = query.order_by(order_fn()).offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        tasks = list(result.scalars().all())
        return tasks, total

    # ── P1-11: execute_task（增量采集 + 去重 + 入库）──

    async def execute_task(self, task: SourcingTask):
        """执行采集任务 — arq worker 回调"""
        logger.info("Executing task %s: keyword=%s", task.id, task.keyword)
        start_time = time.monotonic()

        task.status = SourcingTaskStatus.RUNNING.value
        task.started_at = datetime.now(timezone.utc)
        await self.db.commit()

        platforms = task.platforms or []
        all_candidates_raw: list[dict[str, Any]] = []
        new_candidates: list[dict[str, Any]] = []
        progress: dict[str, Any] = {}
        has_failure = False

        await ws_manager.push_progress(task.id, "task_started", {
            "task_id": task.id,
            "keyword": task.keyword,
            "platforms": platforms,
            "status": task.status,
        })

        for idx, platform in enumerate(platforms):
            platform_start = time.monotonic()
            await ws_manager.push_progress(task.id, "platform_start", {
                "platform": platform,
                "index": idx,
                "total": len(platforms),
            })
            try:
                platform_cfgs = await load_platform_config_from_db()
                base_cfg = platform_cfgs.get(platform, {})
                adapter_cls = get_adapter(platform)
                adapter = adapter_cls(config=base_cfg.get("config", {}), proxy_pool=self.proxy_pool)

                # P1-10: 通过 RecoveryExecutor 执行
                log = CrawlLog(
                    task_id=task.id,
                    platform=platform,
                    status=CrawlStatus.RUNNING.value,
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                )
                self.db.add(log)

                result = await self._recovery.execute(
                    platform=platform,
                    keyword=task.keyword,
                    filters=task.filters,
                )

                duration = time.monotonic() - platform_start

                # 更新日志
                if result.success:
                    log.status = CrawlStatus.SUCCESS.value
                elif result.captcha_triggered:
                    log.status = CrawlStatus.CAPTCHA.value
                elif result.error_message:
                    log.status = CrawlStatus.FAILED.value
                log.candidates_found = len(result.candidates)
                log.error_message = result.error_message
                log.captcha_solved = result.captcha_triggered
                log.proxy_used = result.proxy_used
                log.duration_seconds = duration
                log.finished_at = datetime.now(timezone.utc)

                # Prometheus
                status_tag = "success" if result.success else "failed"
                crawl_total.labels(platform=platform, status=status_tag).inc()
                crawl_duration.labels(platform=platform).observe(duration)

                if result.success:
                    seen = set()
                    for c in result.candidates:
                        fp = self._make_fingerprint(c)
                        if not fp:
                            continue
                        already = await is_already_crawled(self.redis, fp, platform) if self.redis else False
                        if already:
                            continue
                        if fp in seen:
                            continue
                        seen.add(fp)
                        c["_fingerprint"] = fp
                        c["_platform"] = platform
                        new_candidates.append(c)

                    all_candidates_raw.extend(result.candidates)
                    progress[platform] = {
                        "status": "completed",
                        "found": len(result.candidates),
                        "new": len(new_candidates),
                    }
                else:
                    has_failure = True
                    progress[platform] = {
                        "status": "failed",
                        "found": 0,
                        "error": result.error_message,
                    }

                await ws_manager.push_progress(task.id, "platform_done", {
                    "platform": platform,
                    "index": idx,
                    **progress[platform],
                })

            except NotImplementedError:
                progress[platform] = {"status": "not_implemented", "found": 0}
                await ws_manager.push_progress(task.id, "platform_done", {
                    "platform": platform, "status": "not_implemented",
                })
            except Exception as e:
                logger.exception("Platform %s failed: %s", platform, e)
                has_failure = True
                progress[platform] = {"status": "error", "error": str(e)}
                await ws_manager.push_progress(task.id, "platform_done", {
                    "platform": platform, "status": "error", "error": str(e),
                })

        task.progress = progress
        task.total_found = len(all_candidates_raw)
        task.after_dedup = len(new_candidates)

        # P1-9: 保存到 Candidate 表
        saved_count = 0
        saved_ids: list[str] = []
        if new_candidates:
            saved_count, saved_ids = await self._save_results(task, new_candidates)
        task.new_this_run = saved_count

        # 标记任务完成
        if has_failure and saved_count > 0:
            task.status = SourcingTaskStatus.PARTIAL.value
        elif has_failure:
            task.status = SourcingTaskStatus.FAILED.value
        else:
            task.status = SourcingTaskStatus.COMPLETED.value

        task.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

        # P4-4: 采集完成后自动触发 AI 分析（新保存的候选人）
        if saved_ids and sourcing_settings.ai_analysis_enabled:
            try:
                arq_pool = await create_pool(
                    RedisSettings(host="localhost", port=6379, database=sourcing_settings.arq_redis_db)
                )
                await arq_pool.enqueue_job(
                    "analyze_candidates",
                    candidate_ids=saved_ids,
                    task_id=str(task.id),
                )
                logger.info("Auto-triggered analyze_candidates for task %s (%d candidates)", task.id, len(saved_ids))
                await arq_pool.close()
            except Exception as e:
                logger.warning("Failed to auto-trigger analyze_candidates: %s", e)

        await ws_manager.push_progress(task.id, "task_done", {
            "task_id": task.id,
            "status": task.status,
            "total_found": task.total_found,
            "after_dedup": task.after_dedup,
            "new_this_run": task.new_this_run,
            "progress": progress,
        })

        crawl_total.labels(platform="total", status=task.status).inc()
        logger.info(
            "Task %s completed: %d raw, %d after dedup, %d saved, status=%s",
            task.id, task.total_found, task.after_dedup, saved_count, task.status,
        )
        return task

    # ── P1-9: 保存结果到 Candidate 表 ──

    async def _save_results(self, task: SourcingTask, candidates: list[dict[str, Any]]) -> tuple[int, list[str]]:
        """去重后的候选人写入 Candidate 表
        
        Returns:
            (saved_count, [candidate_id, ...])
        """
        saved = 0
        saved_ids: list[str] = []
        for c in candidates:
            fp = c.get("_fingerprint", "")
            platform = c.get("_platform", "")

            # 检查 DB 是否已存在（双保险）
            existing = await self.db.execute(
                select(Candidate).where(Candidate.dedup_fingerprint == fp)
            )
            if existing.scalar_one_or_none():
                continue

            candidate = Candidate(
                name=c.get("name", ""),
                title=c.get("title", ""),
                company=c.get("company"),
                salary=c.get("salary"),
                phone=c.get("phone"),
                email=c.get("email"),
                location=c.get("location"),
                skills=c.get("skills"),
                # 寻源扩展字段
                sourcing_task_id=task.id,
                source_platforms=[platform],
                source_urls={platform: c.get("url", "")},
                raw_data={platform: {k: v for k, v in c.items() if not k.startswith("_")}},
                dedup_fingerprint=fp,
                last_crawled_at=datetime.now(timezone.utc),
            )
            self.db.add(candidate)
            saved += 1
            saved_ids.append(candidate.id)

            # Redis 标记已采
            if self.redis and fp and platform:
                await mark_crawled(self.redis, fp, platform)

        if saved > 0:
            await self.db.commit()
        return saved, saved_ids

    # ── P1-11: cancel_task ──

    async def cancel_task(self, task_id: str) -> bool:
        task = await self.get_task(task_id)
        if not task or task.status in ("completed", "failed", "cancelled"):
            return False
        task.status = SourcingTaskStatus.CANCELLED.value
        await self.db.commit()
        return True

    # ── 工具方法 ──

    @staticmethod
    def _make_fingerprint(candidate: dict[str, Any]) -> str:
        name = candidate.get("name") or candidate.get("username") or ""
        company = candidate.get("company") or ""
        title = candidate.get("title") or ""
        return generate_fingerprint(str(name), str(company), str(title))

    @staticmethod
    def update_prometheus_gauges(proxy_health: dict[str, int] | None = None):
        """外部定时调用更新 gauge 指标"""
        if proxy_health:
            for tier, count in proxy_health.items():
                proxy_pool_size.labels(tier=tier).set(count)
