# Current Work Context

## Goal
- 重构寻源招聘工具，从搜索 JD 改为真正搜索候选人简历
- 新增 GitHub 平台搜索器
- 优化 LinkedIn 搜索精度
- 架构工程化、深度化、模块化、可扩展

## Progress

### Done
- `app/sourcing/searchers/` 模块全套创建（6 个搜索器）：
  - `base.py`: CandidateSearcher 抽象基类 + CandidateProfile/CandidateSearchResult 数据模型 + `_tavily_search()`/`tavily_to_candidates()` 通用函数
  - `linkedin.py`: LinkedInSearcher — 搜索 linkedin.com/in/ 公开个人主页
  - `github.py`: GitHubSearcher — 搜索 github.com/<username> 个人主页（技术岗位补充寻源）
  - `liepin.py`: LiepinSearcher — 标记 requires_auth=True，返回 JD 参考信息
  - `boss.py`: BossZhipinSearcher — 同上
  - `maimai.py`: MaimaiSearcher — 同上
  - `web.py`: WebSearchFallback — 通用互联网候选人搜索兜底
  - `registry.py`: pkgutil 自动发现 + `get_searcher()`/`search_candidates()`/`list_searchers()` 路由入口
- LinkedIn 搜索优化：查询构建增强、内容解析（位置/技能/公司）、标题解析增强、4x buffer
- 重构 `platform_search.py`：委托 CandidateSearcher 执行搜索，三层降级
- tool description + system prompt 更新
- 健康检查 11/11 通过

## Key Decisions
- LinkedIn 可公开搜索候选人简历，用 `include_domains=["linkedin.com"]` + `/in/` URL 过滤
- GitHub profile 页 SEO 文本少，Tavily 搜索结果有限（多为 repo 页），适合技术岗位补充寻源
- 猎聘/Boss/脉脉候选人库需企业账号登录，当前返回 JD 参考
- 搜索器与 platforms/ 适配器并存：searchers 是上层路由逻辑，platforms 是底层浏览器引擎
- 36kr（36氪）是科技新闻平台，无候选人 profile 结构，不适合寻源

## Relevant Files
- `app/sourcing/searchers/base.py`: 数据模型 + 抽象基类 + Tavily 查询封装
- `app/sourcing/searchers/linkedin.py`: LinkedIn 公开个人主页搜索（最佳效果）
- `app/sourcing/searchers/github.py`: GitHub 开发者 profile 搜索（补充寻源）
- `app/sourcing/searchers/liepin.py` / `boss.py` / `maimai.py`: 需认证平台
- `app/sourcing/searchers/web.py`: 通用搜索兜底
- `app/sourcing/searchers/registry.py`: 自动注册 + 路由
- `app/sourcing/tools/platform_search.py`: 重构为使用 CandidateSearcher 架构
- `app/agents/prompts/system.md`: system prompt 更新
