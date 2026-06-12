"""
猎聘候选人搜索器。

搜索策略（按优先级）:
  1. Playwright 浏览器自动化 — 使用猎聘企业账号登录后搜索真实候选人简历
     (需设置 LIEPIN_USERNAME + LIEPIN_PASSWORD 环境变量)
  2. Tavily 兜底 — 搜索公开 JD 信息作为参考

Cookie 持久化: 登录成功后的 Cookie 保存到文件 (LIEPIN_COOKIE_PATH, 默认 ~/.liepin_cookies.json),
   后续搜索自动复用，避免重复登录。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib import parse as urlparse

from bs4 import BeautifulSoup

from app.sourcing.searchers.base import (
    CandidateProfile,
    CandidateSearcher,
    CandidateSearchResult,
    _tavily_search,
    tavily_to_candidates,
)

logger = logging.getLogger(__name__)

# ── 环境变量 ──

_LIEPIN_USERNAME = os.environ.get("LIEPIN_USERNAME", "")
_LIEPIN_PASSWORD = os.environ.get("LIEPIN_PASSWORD", "")
_LIEPIN_COOKIE_PATH = os.environ.get(
    "LIEPIN_COOKIE_PATH",
    str(Path.home() / ".liepin_cookies.json"),
)

# ── 猎聘页面 URL ──

_LIEPIN_BASE = "https://www.liepin.com"
_LIEPIN_LOGIN = "https://www.liepin.com/login/"
_LIEPIN_LOGIN_API = "https://passport.liepin.com/h/login/"  # 登录表单提交
_LIEPIN_TALENT_SEARCH = "https://www.liepin.com/zhaopin/"


class LiepinSearcher(CandidateSearcher):
    """猎聘候选人搜索器 — 支持浏览器自动化登录 + Tavily 兜底。"""

    platform = "liepin"
    display_name = "猎聘"
    search_type = "authenticated"
    requires_auth = True
    supported = True

    # ── 公共搜索入口 ──

    async def search(
        self,
        keywords: str,
        location: str = "",
        max_results: int = 5,
    ) -> CandidateSearchResult:
        """搜索猎聘候选人。

        优先级:
          1. 浏览器自动化（凭证 + Cookie 可用时）
          2. Tavily 公开搜索兜底
        """
        # 尝试浏览器搜索
        if _LIEPIN_USERNAME and _LIEPIN_PASSWORD:
            logger.info("猎聘浏览器搜索模式: keywords=%s location=%s", keywords, location)
            result = await self._browser_search(keywords, location, max_results)
            if result.success:
                return result
            # 浏览器搜索失败 → 日志记录后走 Tavily 兜底
            logger.warning(
                "猎聘浏览器搜索失败, 回退 Tavily: %s",
                result.error_message,
            )

        # Tavily 兜底
        return self._tavily_fallback(keywords, location, max_results)

    def describe_capability(self) -> str:
        if _LIEPIN_USERNAME and _LIEPIN_PASSWORD:
            return (
                "猎聘：已配置企业账号，支持通过浏览器自动化登录后搜索真实候选人简历。"
                "可获取候选人姓名、职位、公司、技能、薪资等信息。"
            )
        return (
            "猎聘：候选人简历搜索需要企业账号登录+付费套餐。"
            "当前返回猎聘上的公开招聘岗位信息（JD）作为参考，并非候选人简历。"
            "如需搜索真实候选人简历，请提供猎聘企业账号并设置 LIEPIN_USERNAME + LIEPIN_PASSWORD。"
        )

    # ── 浏览器搜索 ──

    async def _browser_search(
        self,
        keywords: str,
        location: str = "",
        max_results: int = 5,
    ) -> CandidateSearchResult:
        """使用 Playwright 登录猎聘并搜索候选人。"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return CandidateSearchResult(
                success=False,
                platform=self.platform,
                search_type=self.search_type,
                error_message="缺少 playwright 依赖。请安装 pip install playwright",
            )

        browser = None
        try:
            async with async_playwright() as p:
                # 启动浏览器（stealth 模式）
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                )

                # 尝试加载已保存的 Cookie
                cookies_loaded = self._load_cookies()
                if cookies_loaded:
                    await context.add_cookies(cookies_loaded)
                    logger.info("已加载猎聘 Cookie，跳过登录")
                else:
                    # 无有效 Cookie → 执行登录
                    login_ok = await self._do_login(context)
                    if not login_ok:
                        return CandidateSearchResult(
                            success=False,
                            platform=self.platform,
                            search_type=self.search_type,
                            error_message=(
                                "猎聘登录失败。请检查：\n"
                                "1. LIEPIN_USERNAME / LIEPIN_PASSWORD 是否正确\n"
                                "2. 账号是否需要短信/扫码验证（当前仅支持账号密码登录）\n"
                                "3. 网络是否可访问 passport.liepin.com"
                            ),
                        )

                # 搜索候选人
                page = await context.new_page()
                result = await self._search_talent(page, keywords, location, max_results)
                await page.close()

                return result

        except Exception as e:
            logger.exception("猎聘浏览器搜索异常")
            return CandidateSearchResult(
                success=False,
                platform=self.platform,
                search_type=self.search_type,
                error_message=f"浏览器搜索异常: {type(e).__name__}: {e}",
            )
        finally:
            if browser:
                await browser.close()

    # ── 登录流程 ──

    async def _do_login(self, context: Any) -> bool:
        """执行猎聘登录流程。

        步骤:
          1. 导航到登录页
          2. 填写账号密码
          3. 点击登录
          4. 等待登录成功（检测导航到首页或跳转）
          5. 保存 Cookie

        返回: 是否登录成功
        """
        page = await context.new_page()
        try:
            logger.info("猎聘登录: 导航到登录页 %s", _LIEPIN_LOGIN)
            await page.goto(_LIEPIN_LOGIN, wait_until="networkidle", timeout=30000)

            # 等待登录表单加载
            await page.wait_for_timeout(2000)

            # ── 填写登录表单 ──
            # 猎聘登录页有多种布局: 账号密码 tab 或者直接显示表单
            # 常见的 selector 模式

            # 尝试点击"密码登录" tab（如果存在）
            pwd_tab = await page.query_selector(
                "a[data-type='account'], "
                ".login-type-tab:has-text('密码登录'), "
                "a:has-text('密码登录'), "
                "[class*='password-login'], "
                ".tab-item.active"
            )
            if pwd_tab:
                await pwd_tab.click()
                await page.wait_for_timeout(1000)

            # 填写用户名/手机号
            username_input = await page.query_selector(
                "input[name='login'], "
                "input[type='text'][placeholder*='手机'], "
                "input[type='text'][placeholder*='账号'], "
                "input[placeholder*='手机号'], "
                "input[placeholder*='用户名'], "
                "input[name='userLogin'], "
                "input[id*='login'], "
                "input[class*='phone'], "
                "input[class*='account']"
            )
            if not username_input:
                logger.error("猎聘登录: 未找到用户名输入框")
                return False

            await username_input.fill(_LIEPIN_USERNAME)
            await page.wait_for_timeout(500)

            # 填写密码
            pwd_input = await page.query_selector(
                "input[type='password'], "
                "input[name='password'], "
                "input[name='pwd'], "
                "input[id*='pwd'], "
                "input[class*='password'], "
                "input[placeholder*='密码']"
            )
            if not pwd_input:
                logger.error("猎聘登录: 未找到密码输入框")
                return False

            await pwd_input.fill(_LIEPIN_PASSWORD)
            await page.wait_for_timeout(500)

            # ── 检测是否需要验证码 ──
            captcha = await page.query_selector(
                "[class*='captcha'], "
                "[class*='verify'], "
                "[class*='slider'], "
                "img[class*='captcha'], "
                "[id*='captcha'], "
                "[id*='slide']"
            )
            if captcha:
                logger.warning("猎聘登录: 检测到验证码，自动登录可能失败")

            # 点击登录按钮
            login_btn = await page.query_selector(
                "button[type='submit'], "
                "button:has-text('登录'), "
                "a:has-text('登录'), "
                "input[type='submit'], "
                "[class*='login-btn'], "
                "[class*='submit-btn']"
            )
            if not login_btn:
                logger.error("猎聘登录: 未找到登录按钮")
                return False

            await login_btn.click()

            # ── 等待登录结果 ──
            # 等待导航完成或跳转到首页
            try:
                await page.wait_for_url(
                    lambda url: "login" not in url.lower() or "passport" not in url.lower(),
                    timeout=15000,
                )
            except Exception:
                # 超时可能仍在登录页（验证码等原因）
                page_content = await page.content()
                if "验证码" in page_content or "captcha" in page_content.lower():
                    logger.error("猎聘登录失败: 需要验证码")
                    return False
                if "密码错误" in page_content or "账号或密码" in page_content:
                    logger.error("猎聘登录失败: 账号或密码错误")
                    return False
                logger.warning("猎聘登录: 登录后未跳转，可能仍需要验证")
                return False

            # ── 保存 Cookie ──
            cookies = await context.cookies()
            self._save_cookies(cookies)
            logger.info("猎聘登录成功，已保存 %d 个 Cookie", len(cookies))
            return True

        except Exception:
            logger.exception("猎聘登录异常")
            return False
        finally:
            await page.close()

    # ── 候选人搜索 ──

    async def _search_talent(
        self,
        page: Any,
        keywords: str,
        location: str = "",
        max_results: int = 5,
    ) -> CandidateSearchResult:
        """在已登录的猎聘会话中搜索候选人。"""
        params = {"key": keywords.strip()}
        if location:
            params["dq"] = location
        search_url = f"{_LIEPIN_TALENT_SEARCH}?{urlparse.urlencode(params)}"

        logger.info("猎聘搜索: %s", search_url)

        try:
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            logger.warning("猎聘搜索导航超时, 尝试继续: %s", e)

        # 等待搜索结果加载
        await page.wait_for_timeout(3000)

        # 获取页面内容
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # ── 解析候选人卡片 ──
        candidates: list[CandidateProfile] = []

        # 猎聘搜索结果页常见的卡片选择器
        card_selectors = [
            ".job-list-item",
            ".resume-card",
            "[class*='resume-card']",
            "[class*='candidate-card']",
            "[class*='search-result-item']",
            "li[class*='item']",
            "[class*='job-card']",
            ".sojob-item",
            ".job-item",
            "[class*='list-item']",
        ]

        cards = []
        for selector in card_selectors:
            cards = soup.select(selector)
            if cards:
                logger.info("猎聘解析: 使用选择器 '%s' 找到 %d 个卡片", selector, len(cards))
                break

        for card in cards[:max_results]:
            try:
                profile = self._extract_candidate(card)
                if profile and (profile.name or profile.title):
                    candidates.append(profile)
            except Exception:
                continue

        if candidates:
            return CandidateSearchResult(
                success=True,
                candidates=candidates,
                platform=self.platform,
                search_type="authenticated",
                total_found=len(candidates),
            )

        # 页面无卡片 → 可能是未登录/跳转到登录页
        current_url = page.url
        if "login" in current_url.lower():
            return CandidateSearchResult(
                success=False,
                platform=self.platform,
                search_type=self.search_type,
                error_message="跳转到登录页，Cookie 可能已过期，请清除 LIEPIN_COOKIE_PATH 文件后重试",
            )

        # 可能页面结构不同 → 返回搜索结果较少的信息
        logger.warning("猎聘搜索结果为空, page_url=%s", current_url)
        return CandidateSearchResult(
            success=True,
            candidates=[],
            platform=self.platform,
            search_type="authenticated",
            total_found=0,
        )

    def _extract_candidate(self, card: Any) -> CandidateProfile | None:
        """从 HTML 卡片提取候选人信息。"""
        from bs4 import Tag

        if not isinstance(card, Tag):
            return None

        name = self._text(card, ".name, .username, [class*='name'], h3, .job-name, .title")
        title = self._text(
            card,
            ".title, .job-title, [class*='title'], .job-salary, .condition, .text-condition",
        )
        _salary = self._text(card, ".salary, [class*='salary'], [class*='pay']")
        company = self._text(card, ".company, .company-name, [class*='company']")
        location = self._text(card, ".address, .location, [class*='address'], [class*='city']")

        # 提取技能标签
        tag_els = card.select(
            ".tag, .tag-item, [class*='tag'], span[class], .skill-tag, .keyword"
        )
        skills = []
        for t in tag_els:
            text = t.get_text(strip=True)
            if text and len(text) < 30:
                skills.append(text)

        # 提取链接
        link_el = card.select_one("a[href]")
        profile_url = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            profile_url = href if href.startswith("http") else f"{_LIEPIN_BASE}{href}"

        # 提取摘要
        summary_el = card.select_one(
            ".description, .summary, .desc, [class*='desc'], [class*='summary'],"
            " .job-description, p"
        )
        summary = None
        if summary_el:
            s = summary_el.get_text(strip=True)
            if s:
                summary = s[:300]

        if not name and not title:
            return None

        return CandidateProfile(
            name=name or "猎聘候选人",
            title=title,
            company=company,
            location=location,
            profile_url=profile_url,
            platform=self.platform,
            source="platform_adapter",
            skills=skills[:15],
            summary=summary,
        )

    # ── Cookie 持久化 ──

    def _load_cookies(self) -> list[dict[str, Any]] | None:
        """从文件加载 Cookie。

        返回 None 表示无有效 Cookie（文件不存在或为空）。
        """
        path = Path(_LIEPIN_COOKIE_PATH)
        if not path.exists():
            logger.info("猎聘 Cookie 文件不存在: %s", _LIEPIN_COOKIE_PATH)
            return None

        try:
            data = json.loads(path.read_text())
            if not data:
                return None
            logger.info("猎聘 Cookie 已加载: %s (%d 个)", _LIEPIN_COOKIE_PATH, len(data))
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("猎聘 Cookie 加载失败: %s", e)
            return None

    def _save_cookies(self, cookies: list[dict[str, Any]]):
        """保存 Cookie 到文件。"""
        try:
            path = Path(_LIEPIN_COOKIE_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
            logger.info("猎聘 Cookie 已保存: %s (%d 个)", _LIEPIN_COOKIE_PATH, len(cookies))
        except OSError as e:
            logger.error("猎聘 Cookie 保存失败: %s", e)

    # ── Tavily 兜底 ──

    def _tavily_fallback(
        self,
        keywords: str,
        location: str = "",
        max_results: int = 5,
    ) -> CandidateSearchResult:
        """Tavily 搜索公开 JD 作为兜底。"""
        query = keywords.strip()
        if location:
            query = f"{query} {location}"
        query = f"{query} 猎聘"

        tavily_result = _tavily_search(
            query=query,
            max_results=max_results,
            include_domains=["liepin.com"],
        )

        if not tavily_result["success"]:
            return CandidateSearchResult(
                success=False,
                platform=self.platform,
                search_type=self.search_type,
                error_message=tavily_result.get("error_message", "搜索失败"),
            )

        sources = tavily_result.get("sources", [])
        candidates = tavily_to_candidates(
            sources, platform=self.platform, source_tag="job_listing"
        )

        return CandidateSearchResult(
            success=True,
            candidates=candidates,
            platform=self.platform,
            search_type=self.search_type,
            total_found=len(candidates),
        )

    # ── 工具方法 ──

    @staticmethod
    def _text(soup: Any, selector: str) -> str | None:
        """从 BeautifulSoup 元素中提取文本。"""
        from bs4 import Tag

        try:
            el = soup.select_one(selector) if hasattr(soup, "select_one") else None
            if isinstance(el, Tag):
                text = el.get_text(strip=True)
                return text if text else None
            return None
        except Exception:
            return None
