"""ParamExtractor unit tests — action inference + entity extraction from NL text."""

from app.agents.param_extractor import (
    extract_params,
    infer_action,
    extract_companies,
    extract_roles,
    extract_skills,
    extract_salary,
    extract_experience,
    extract_location,
    extract_candidate_name,
    extract_job_title,
)


class TestInferAction:
    """Action inference from NL text."""

    def test_sourcing_candidate_search(self):
        assert infer_action("搜一下小红书的Java候选人", "candidate_search") == "candidate_search"

    def test_sourcing_talent_map(self):
        assert infer_action("做一下抖音的竞品mapping", "sourcing") == "talent_map"

    def test_sourcing_outreach(self):
        assert infer_action("帮我写个触达话术", "outreach") == "outreach"

    def test_sourcing_jd_generation(self):
        assert infer_action("生成一个前端JD", "jd_generation") == "jd_generation"

    def test_sourcing_channel_strategy(self):
        assert infer_action("推荐渠道策略", "channel_strategy") == "channel_strategy"

    def test_screening_batch(self):
        assert infer_action("批量筛选三个候选人", "screening") == "batch"

    def test_screening_evaluate(self):
        assert infer_action("做多维评估", "screening") == "evaluate"

    def test_interview_evaluation_form(self):
        assert infer_action("生成评价表", "interview") == "evaluation_form"

    def test_interview_reminder(self):
        assert infer_action("发面试提醒", "interview") == "reminder"

    def test_interview_feedback_summary(self):
        assert infer_action("汇总反馈", "interview") == "summarize_feedback"

    def test_offering_benchmark(self):
        assert infer_action("查一下市场薪酬基准", "offering") == "benchmark"

    def test_offering_calculate(self):
        assert infer_action("算一下总包", "offering") == "calculate"

    def test_offering_offer_letter(self):
        assert infer_action("生成offer函", "offering") == "offer_letter"

    def test_offering_negotiation(self):
        assert infer_action("谈薪策略", "offering") == "negotiation"

    def test_onboarding_probation(self):
        assert infer_action("转正评估", "onboarding") == "probation_review"

    def test_analytics_funnel(self):
        assert infer_action("看招聘漏斗", "analytics") == "funnel"

    def test_analytics_channels(self):
        assert infer_action("渠道效果分析", "analytics") == "channels"

    def test_analytics_kpi(self):
        assert infer_action("招聘KPI", "analytics") == "kpi"

    def test_analytics_report(self):
        assert infer_action("生成全量报告", "report") == "report"

    def test_default_fallback_no_intent(self):
        assert infer_action("今天天气如何") == "chat"

    def test_default_fallback_with_intent(self):
        assert infer_action("随便看看", "screening") == "screen"


class TestExtractCompanies:
    """Company name extraction."""

    def test_single_company(self):
        assert extract_companies("小红书的候选人") == ["小红书"]

    def test_multi_company(self):
        result = extract_companies("字节和阿里的算法工程师")
        assert "字节" in result
        assert "阿里" in result

    def test_no_company(self):
        assert extract_companies("帮我找前端工程师") == []

    def test_english_company(self):
        assert extract_companies("Google的候选人") == ["Google"]


class TestExtractRoles:
    """Role/position extraction."""

    def test_chinese_role(self):
        assert "前端工程师" in extract_roles("找前端工程师")

    def test_english_role(self):
        assert "Java开发" in extract_roles("Java开发")

    def test_multi_role(self):
        result = extract_roles("找Java和Python后端")
        assert "Java" in result
        assert "Python" in result

    def test_no_role(self):
        assert extract_roles("今天天气怎么样") == []


class TestExtractSkills:
    """Skill keyword extraction."""

    def test_single_skill(self):
        assert "Kubernetes" in extract_skills("需要Kubernetes经验")

    def test_multi_skill(self):
        result = extract_skills("需要Docker和K8s经验")
        assert "Docker" in result
        assert "K8s" in result

    def test_no_skill(self):
        assert extract_skills("随便聊聊") == []


class TestExtractSalary:
    """Salary extraction."""

    def test_salary_k(self):
        result = extract_salary("薪资30k")
        assert result is not None
        assert result["min_k"] == 30

    def test_salary_range(self):
        result = extract_salary("薪资30k-50k")
        assert result is not None
        assert result["min_k"] == 30
        assert result["max_k"] == 50

    def test_no_salary(self):
        assert extract_salary("帮我找前端工程师") is None


class TestExtractExperience:
    """Experience years extraction."""

    def test_experience_years(self):
        result = extract_experience("3年以上经验")
        assert result is not None
        assert result["min_years"] == 3

    def test_experience_range(self):
        result = extract_experience("3-5年经验")
        assert result is not None
        assert result["min_years"] == 3
        assert result["max_years"] == 5

    def test_no_experience(self):
        assert extract_experience("随便看看") is None


class TestExtractLocation:
    """City/location extraction."""

    def test_beijing(self):
        assert extract_location("北京的前端工程师") == "北京"

    def test_shanghai(self):
        assert extract_location("上海的Java开发") == "上海"

    def test_shenzhen(self):
        assert extract_location("深圳的候选人") == "深圳"

    def test_no_location(self):
        assert extract_location("帮我找前端工程师") is None


class TestExtractCandidateName:
    """Candidate name extraction."""

    def test_with_offer_keyword(self):
        assert extract_candidate_name("给张三发offer") == "张三"

    def test_with_interview_keyword(self):
        assert extract_candidate_name("给李四安排面试") == "李四"

    def test_no_name(self):
        assert extract_candidate_name("帮我看看候选人") is None


class TestExtractJobTitle:
    """Job title extraction."""

    def test_with_prefix(self):
        assert extract_job_title("招聘Java高级工程师") == "Java高级工程师"

    def test_fallback_to_roles(self):
        result = extract_job_title("找前端工程师", ["前端工程师"])
        assert result == "前端工程师"

    def test_no_title(self):
        assert extract_job_title("今天天气怎么样") is None


class TestExtractParamsIntegration:
    """Full param extraction end-to-end."""

    def test_jd_generation_with_company_and_role(self):
        r = extract_params("帮小红书生成一个Java后端的JD", "jd_generation")
        assert r["action"] == "jd_generation"
        assert "小红书" in r.get("target_companies", [])
        assert "Java" in r.get("target_roles", [])

    def test_candidate_search_with_constraints(self):
        r = extract_params("找北京的前端工程师，3年以上经验，薪资30k左右", "candidate_search")
        assert r["action"] == "candidate_search"
        assert r["location"] == "北京"
        assert "前端工程师" in r.get("target_roles", [])
        assert r.get("experience_min") == 3
        assert r.get("salary_min") == 30

    def test_channel_strategy_with_budget(self):
        r = extract_params("推荐渠道策略，预算2万", "channel_strategy")
        assert r["action"] == "channel_strategy"
        assert r["budget"] == 2.0

    def test_offering_with_name(self):
        r = extract_params("给张三发offer，Java工程师", "offering")
        assert r["action"] == "calculate"
        assert r["candidate_name"] == "张三"
        assert r["role"] == "Java工程师"

    def test_outreach_with_company(self):
        r = extract_params("联系在腾讯做前端的候选人", "outreach")
        assert r["action"] == "outreach"
        assert "腾讯" in r.get("target_companies", [])
        assert "前端" in r.get("target_roles", [])

    def test_interview_with_name(self):
        r = extract_params("给李四安排面试，Java高级工程师", "interview")
        assert r["action"] == "schedule"
        assert r["candidate_name"] == "李四"

    def test_analytics_report(self):
        r = extract_params("生成招聘报告", "report")
        assert r["action"] == "report"

    def test_empty_text(self):
        assert extract_params("", "chat") == {}

    def test_multiple_companies(self):
        r = extract_params("看看字节和阿里的算法工程师", "candidate_search")
        assert "字节" in r.get("target_companies", [])
        assert "阿里" in r.get("target_companies", [])

    def test_no_matching_keywords(self):
        r = extract_params("你好，今天天气怎么样", "chat")
        assert r.get("action") == "chat"

    def test_screening_without_keywords(self):
        r = extract_params("帮我筛选简历", "screening")
        assert r.get("action") == "screen"
