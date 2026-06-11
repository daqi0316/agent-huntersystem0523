"""BOSS直聘适配器 — Playwright CDP 实现"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any

import httpx

from app.sourcing.account_manager import decrypt_cookie
from app.sourcing.config import sourcing_settings
from app.sourcing.platforms.base import PlatformAdapter, CrawlResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.zhipin.com"
_SEARCH_URL = f"{_BASE_URL}/web/geek/job"
_CAPTCHA_INDICATORS = [
    "captcha",
    "verify",
    "geetest",
    "slide",
    "nc_slider",
    "验证码",
    "安全验证",
]
_LOGIN_REDIRECT_INDICATORS = [
    "/web/user/?ka=header-login",
    "login",
    "passport",
]


class BossZhipinAdapter(PlatformAdapter):
    """BOSS直聘适配器 — Playwright CDP + Cookie 持久化 + 反爬对抗"""

    name = "boss_zhipin"
    display_name = "BOSS直聘"
    category = "job_board"
    anti_crawl_level = 4
    requires_login = True
    use_stealth = True

    def __init__(self, config: dict[str, Any] | None = None, proxy_pool=None, account_manager=None):
        super().__init__(config, proxy_pool)
        self.account_manager = account_manager
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # ── P1-3: 浏览器管理 ──

    async def ensure_browser(self):
        """启动或连接 Playwright 浏览器"""
        if self._page is not None:
            return

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # 代理
        proxy_str = None
        if self.proxy_pool:
            proxy_str = await self.proxy_pool.get_proxy(self.name, self.anti_crawl_level)

        launch_options: dict[str, Any] = {
            "headless": sourcing_settings.playwright_headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        }
        if sourcing_settings.playwright_browser_path:
            launch_options["executable_path"] = sourcing_settings.playwright_browser_path
        if proxy_str:
            launch_options["proxy"] = {"server": proxy_str}

        cdp_port = sourcing_settings.playwright_cdp_port
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{cdp_port}"
            )
            self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
            logger.info("Connected to CDP Chrome on port %d", cdp_port)
        except Exception:
            self._browser = await self._playwright.chromium.launch(**launch_options)
            self._context = await self._browser.new_context(
                user_agent=self._random_ua(),
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            logger.info("Launched new browser (headless=%s)", launch_options["headless"])

        await self._inject_stealth()
        self._page = await self._context.new_page()

    async def close_browser(self):
        """清理浏览器资源"""
        try:
            if self._page:
                await self._page.close()
        except Exception:
            pass
        try:
            if self._context and not getattr(self._context, "_closed", False):
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def _inject_stealth(self):
        """注入反检测脚本"""
        assert self._context is not None
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en'],
            });
            // 覆盖 chrome 属性
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {},
            };
            // 覆盖 permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => (
                params.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(params)
            );
        """)

    # ── P1-4: Cookie 注入 ──

    async def inject_cookies(self, account_id: str | None = None):
        """从 AccountManager 获取 Cookie → 注入浏览器上下文"""
        if not self.account_manager or not self._context:
            logger.warning("No account_manager or context, skipping cookie injection")
            return

        # 获取账号
        account = await self.account_manager.acquire(self.name)
        if not account or not account.encrypted_cookies:
            logger.warning("No account or cookie available for boss_zhipin")
            return

        try:
            cookie_json = decrypt_cookie(account.encrypted_cookies)
            cookies = json.loads(cookie_json)
            if isinstance(cookies, list):
                # Playwright cookie 格式
                for c in cookies:
                    if "domain" not in c and "url" not in c:
                        c["url"] = _BASE_URL
                await self._context.add_cookies(cookies)
                logger.info("Injected cookies for account %s (%s)", account.display_name, account.id)

                # 校验 Cookie 有效性
                valid = await self._verify_login()
                if not valid:
                    logger.warning("Cookie for %s expired, rotating", account.display_name)
                    if self.account_manager:
                        await self.account_manager.rotate(self.name, account.id)
                return account.id

        except Exception as e:
            logger.error("Failed to inject cookies: %s", e)
            if self.account_manager:
                await self.account_manager.rotate(self.name, account.id)
        return None

    async def _verify_login(self) -> bool:
        """校验登录态：访问 BOSS首页，检查是否有登录态标识"""
        if not self._page:
            return False
        try:
            await self._page.goto(_BASE_URL, wait_until="domcontentloaded", timeout=15000)
            await self._human_delay(1, 2)

            # 检查是否有登录态
            login_indicators = ['a[ka="header-login"]', '.login-btn', 'a[href*="passport"]']
            for sel in login_indicators:
                try:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        return False
                except Exception:
                    continue
            return True
        except Exception as e:
            logger.debug("Login verification failed: %s", e)
            return False

    # ── P1-5: 搜索 + 翻页 ──

    async def search(self, keyword: str, **filters) -> CrawlResult:
        """搜索关键词 → 翻页采集候选人列表"""
        await self.ensure_browser()

        # Cookie 注入
        account_id = await self.inject_cookies()
        if not account_id:
            logger.warning("No valid cookie, attempting anonymous search")

        # 构建 URL
        city = filters.get("city", "100010000")  # 默认全国
        url = f"{_SEARCH_URL}?city={city}&query={keyword}"
        for k, v in filters.items():
            if k not in ("city", "page") and v is not None:
                url += f"&{k}={v}"

        all_candidates: list[dict[str, Any]] = []
        max_pages = filters.get("max_pages", 5)
        captcha_triggered = False
        proxy_used = None
        error_message = None

        for page_num in range(1, max_pages + 1):
            page_url = url + (f"&page={page_num}" if page_num > 1 else "")

            try:
                result = await self._crawl_page(page_url, keyword, page_num)
            except Exception as e:
                error_message = f"Page {page_num}: {e}"
                logger.exception("Crawl failed on page %d", page_num)
                break

            if result.captcha_triggered:
                captcha_triggered = True
                error_message = f"Captcha triggered on page {page_num}"
                # 尝试打码
                if await self._solve_captcha():
                    continue  # 打码成功，重试当前页
                break

            if result.candidates:
                all_candidates.extend(result.candidates)
                logger.info("Page %d: found %d candidates", page_num, len(result.candidates))
            else:
                logger.info("Page %d: no more candidates", page_num)
                break

            proxy_used = result.proxy_used

            # 页间间隔（反爬）
            if page_num < max_pages:
                await self._human_delay(3, 8)

        # 上报用量
        if account_id and self.account_manager:
            await self.account_manager.report_usage(account_id, len(all_candidates))

        success = bool(all_candidates) and not captcha_triggered
        return CrawlResult(
            success=success,
            candidates=all_candidates,
            error_message=error_message,
            captcha_triggered=captcha_triggered,
            proxy_used=proxy_used,
        )

    async def _crawl_page(self, url: str, keyword: str, page_num: int) -> CrawlResult:
        """采集单页"""
        if not self._page:
            return CrawlResult(success=False, error_message="Browser not initialized")

        # 导航
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 等待列表加载
        try:
            await self._page.wait_for_selector(
                ".job-card-wrapper, .job-list li, [class*='job-card']",
                timeout=10000,
            )
        except Exception:
            pass

        await self._human_delay(2, 4)

        # 模拟人类滚动
        await self._human_scroll()

        # 检测验证码
        if await self._detect_captcha():
            return CrawlResult(success=False, captcha_triggered=True)

        # 检查登录态
        page_url = self._page.url
        for indicator in _LOGIN_REDIRECT_INDICATORS:
            if indicator in page_url:
                return CrawlResult(success=False, error_message="Login redirect detected")

        # 解析 HTML
        html = await self._page.content()
        candidates = await self.parse_list(html)

        return CrawlResult(
            success=True,
            candidates=candidates,
        )

    # ── P1-6: 详情页解析 ──

    async def get_detail(self, url: str) -> CrawlResult:
        """采集候选人详情页"""
        await self.ensure_browser()
        await self.inject_cookies()

        if not self._page:
            return CrawlResult(success=False, error_message="Browser not initialized")

        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay(2, 4)
            await self._human_scroll()

            if await self._detect_captcha():
                return CrawlResult(success=False, captcha_triggered=True, error_message="Captcha triggered")

            html = await self._page.content()
            detail = await self.parse_detail(html)
            return CrawlResult(success=True, candidates=[detail] if detail else [])

        except Exception as e:
            logger.exception("Failed to get detail: %s", url)
            return CrawlResult(success=False, error_message=str(e))

    # ── 列表页解析 ──

    async def parse_list(self, html: str) -> list[dict[str, Any]]:
        """从 HTML 解析候选人列表"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        candidates: list[dict[str, Any]] = []

        # BOSS直聘列表页候选人卡片选择器（多个版本兼容）
        cards = (
            soup.select(".job-card-wrapper")
            or soup.select(".job-list li")
            or soup.select("[class*='job-card']")
        )

        for card in cards:
            try:
                candidate = self._extract_card(card)
                if candidate.get("name") or candidate.get("title"):
                    candidates.append(candidate)
            except Exception as e:
                logger.debug("Skipping card parse error: %s", e)
                continue

        return candidates

    def _extract_card(self, card: Any) -> dict[str, Any]:
        """从单张卡片提取字段"""
        name = self._text(card, ".username, .name, [class*='name']")
        title = self._text(card, ".job-title, .title, [class*='title']")
        salary = self._text(card, ".salary, [class*='salary']")
        company = self._text(card, ".company-name, .company, [class*='company']")
        tags = [t.strip() for t in card.select(".tag-item, .tag, [class*='tag']") if t.strip()]
        link_el = card.select_one("a[href*='geek']") or card.select_one("a[href]")
        url = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            url = href if href.startswith("http") else f"{_BASE_URL}{href}"

        return {
            "name": name,
            "title": title,
            "salary": salary,
            "company": company,
            "tags": tags,
            "url": url,
            "platform": "boss_zhipin",
        }

    # ── 详情页解析 ──

    async def parse_detail(self, html: str) -> dict[str, Any]:
        """从 HTML 解析候选人详情"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        name = self._text(soup, ".name, .username, [class*='name']")
        title = self._text(soup, ".title, .job-title, [class*='title']")
        salary = self._text(soup, ".salary, [class*='salary']")
        company = self._text(soup, ".company, .company-name, [class*='company']")

        # 技能标签
        skill_els = soup.select(".skill-tag, .tag-item, [class*='skill']")
        skills = [t.get_text(strip=True) for t in skill_els if t and t.get_text(strip=True)]

        # 工作经历
        experiences = []
        exp_section = soup.select_one(".experience, .work-experience, [class*='experience']")
        if exp_section:
            exp_items = exp_section.select("li, .item, .time-line-item")
            for item in exp_items:
                experiences.append(item.get_text(strip=True))

        # 教育背景
        education = None
        edu_section = soup.select_one(".education, [class*='education']")
        if edu_section:
            education = edu_section.get_text(strip=True)

        # 个人介绍
        description = None
        desc_section = soup.select_one(".description, .personal-desc, .introduction, [class*='desc']")
        if desc_section:
            description = desc_section.get_text(strip=True)

        return {
            "name": name,
            "title": title,
            "salary": salary,
            "company": company,
            "skills": skills,
            "experiences": experiences,
            "education": education,
            "description": description,
            "platform": "boss_zhipin",
        }

    # ── P1-7: 验证码检测 + 打码 ──

    async def _detect_captcha(self) -> bool:
        """检测页面是否触发验证码"""
        if not self._page:
            return False
        try:
            page_url = self._page.url.lower()
            page_title = await self._page.title()

            for indicator in _CAPTCHA_INDICATORS:
                if indicator in page_url or indicator in page_title.lower():
                    logger.warning("Captcha detected: %s in URL/title", indicator)
                    return True

            # 检查页面元素
            captcha_selectors = [
                "iframe[src*='captcha']",
                "iframe[src*='geetest']",
                "iframe[src*='verify']",
                ".geetest_holder",
                "#captcha",
                ".captcha-box",
                "[class*='geetest']",
                "[class*='slide']",
                ".nc-container",
                "img[src*='captcha']",
            ]
            for sel in captcha_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        logger.warning("Captcha detected: element %s visible", sel)
                        return True
                except Exception:
                    continue

            return False
        except Exception as e:
            logger.debug("Captcha detection error: %s", e)
            return False

    async def _solve_captcha(self) -> bool:
        """尝试自动打码"""
        if sourcing_settings.captcha_service == "none":
            logger.warning("No captcha service configured, skipping")
            return False

        if sourcing_settings.captcha_service == "2captcha":
            return await self._solve_via_2captcha()

        logger.warning("Unknown captcha service: %s", sourcing_settings.captcha_service)
        return False

    async def _solve_via_2captcha(self) -> bool:
        """通过 2Captcha API 打码"""
        api_key = sourcing_settings.captcha_api_key
        if not api_key:
            return False

        if not self._page:
            return False

        try:
            site_key = await self._extract_site_key()
            if not site_key:
                logger.warning("No site key found for captcha")
                return False

            page_url = self._page.url
            async with httpx.AsyncClient(timeout=30) as client:
                # 提交打码
                resp = await client.post(
                    "https://2captcha.com/in.php",
                    data={"key": api_key, "method": "geetest", "gt": site_key, "pageurl": page_url},
                )
                text = resp.text
                if not text.startswith("OK|"):
                    logger.warning("2captcha submit failed: %s", text)
                    return False

                captcha_id = text.split("|")[1]

                # 轮询结果
                for _ in range(30):
                    await asyncio.sleep(5)
                    res = await client.get(
                        "https://2captcha.com/res.php",
                        params={"key": api_key, "action": "get", "id": captcha_id},
                    )
                    if res.text.startswith("OK|"):
                        logger.info("Captcha solved via 2Captcha")
                        return True
                    if res.text == "ERROR_CAPTCHA_UNSOLVABLE":
                        break

            return False
        except Exception as e:
            logger.error("2captcha error: %s", e)
            return False

    async def _extract_site_key(self) -> str | None:
        """从页面提取极验 site key"""
        if not self._page:
            return None
        try:
            site_key = await self._page.evaluate("""
                () => {
                    const el = document.querySelector('.geetest_holder');
                    if (el) return el.getAttribute('data-gt');
                    const script = document.querySelector('script[src*="geetest"]');
                    if (script) return script.src.match(/gt=([^&]+)/)?.[1];
                    return null;
                }
            """)
            return site_key
        except Exception:
            return None

    # ── 工具方法 ──

    async def _human_delay(self, min_sec: float = 1, max_sec: float = 3):
        """模拟人类操作的随机延迟"""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def _human_scroll(self):
        """模拟人类分段滚动"""
        if not self._page:
            return
        try:
            viewport_height = await self._page.evaluate("window.innerHeight")
            total_height = await self._page.evaluate("document.body.scrollHeight")
            steps = random.randint(3, 6)
            for i in range(1, steps + 1):
                scroll_to = int(total_height * i / steps)
                if scroll_to > total_height:
                    scroll_to = total_height
                await self._page.evaluate(f"window.scrollTo({{ top: {scroll_to}, behavior: 'smooth' }})")
                await self._human_delay(0.3, 0.8)
            # 偶尔回滚一点
            if random.random() < 0.3:
                await self._page.evaluate(f"window.scrollTo({{ top: {int(total_height * 0.7)}, behavior: 'smooth' }})")
                await self._human_delay(0.5, 1)
        except Exception:
            pass

    @staticmethod
    def _random_ua() -> str:
        uas = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        ]
        return random.choice(uas)

    @staticmethod
    def _text(soup: Any, selector: str) -> str | None:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            return text if text else None
        return None
