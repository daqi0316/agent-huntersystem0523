"""
对比测试 harness — 同一 URL 三引擎依次测试，记录成功率 / 耗时
"""
import asyncio
import time
from dataclasses import dataclass, field

from app.tools.browser_engine import EngineType, PageResult
from app.tools.browser_engine.engine.http_engine import HTTPEngine
from app.tools.browser_engine.engine.invisible_engine import InvisiblePlaywrightEngine
from app.tools.browser_engine.engine.browser_use_engine import BrowserUseEngine


@dataclass
class EngineTestResult:
    engine_name: str
    success: bool
    duration_ms: float
    html_length: int
    error: str | None = None


@dataclass
class ComparisonReport:
    url: str
    results: list[EngineTestResult] = field(default_factory=list)

    def print(self):
        print(f"\n{'='*60}")
        print(f"对比测试报告: {self.url}")
        print(f"{'='*60}")
        for r in self.results:
            status = "✅" if r.success else "❌"
            print(f"  {status} {r.engine_name:25s} | {r.duration_ms:6.0f}ms | {r.html_length:6d} chars")
            if r.error:
                print(f"     Error: {r.error[:100]}")
        print(f"{'='*60}\n")


async def run_single_engine(engine_cls, config: dict, url: str, name: str) -> EngineTestResult:
    """单个引擎测试"""
    engine = engine_cls(config)
    start = time.monotonic()
    try:
        result = await engine.fetch_page(url, timeout=15000)
        duration = (time.monotonic() - start) * 1000
        await engine.close()
        return EngineTestResult(
            engine_name=name,
            success=result.success,
            duration_ms=duration,
            html_length=len(result.html) if result.html else 0,
            error=result.error_message,
        )
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        await engine.close()
        return EngineTestResult(
            engine_name=name,
            success=False,
            duration_ms=duration,
            html_length=0,
            error=str(e),
        )


async def compare_engines(url: str, http_config: dict | None = None) -> ComparisonReport:
    """三引擎对比测试"""
    report = ComparisonReport(url=url)
    config = http_config or {"http": {}}

    # HTTP引擎
    result = await run_single_engine(HTTPEngine, config, url, "HTTP (httpx)")
    report.results.append(result)

    # invisible_playwright引擎（如果可用）
    result = await run_single_engine(
        InvisiblePlaywrightEngine, config, url, "InvisiblePlaywright",
    )
    report.results.append(result)

    # browser-use引擎（如果可用）
    result = await run_single_engine(
        BrowserUseEngine, config, url, "BrowserUse",
    )
    report.results.append(result)

    return report


async def main():
    """执行对比测试"""
    test_urls = [
        "https://example.com",
        "https://httpbin.org/get",
    ]

    for url in test_urls:
        report = await compare_engines(url)
        report.print()

    # 汇总
    print("提示: invisible_playwright 和 browser-use 需要浏览器环境才能成功。")


if __name__ == "__main__":
    asyncio.run(main())
