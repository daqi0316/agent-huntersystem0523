"""Tests for Phase 2 Feature Agents: Sourcing, Offering, Onboarding, Analytics."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.sourcing_agent import SourcingAgent, SOURCE_CHANNELS
from app.agents.offering_agent import OfferingAgent, NEGOTIATION_SCENARIOS
from app.agents.onboarding_agent import OnboardingAgent, ONBOARDING_MILESTONES
from app.agents.analytics_agent import AnalyticsAgent, ANOMALY_THRESHOLDS


# ══════════════════════════════════════════════════════════════
# SourcingAgent
# ══════════════════════════════════════════════════════════════

class TestSourcingAgent:
    @pytest.fixture
    def agent(self):
        return SourcingAgent()

    def test_init(self, agent):
        assert agent.name == "sourcing"

    @pytest.mark.asyncio
    async def test_build_talent_map(self, agent):
        result = await agent.build_talent_map(
            target_companies=["字节跳动", "腾讯"],
            target_roles=["Python 工程师", "后端开发"],
        )
        assert result["total_targets"] == 2
        assert len(result["talent_map"]) == 2
        assert result["talent_map"][0]["company"] == "字节跳动"

    @pytest.mark.asyncio
    async def test_build_talent_map_empty(self, agent):
        result = await agent.build_talent_map([], [])
        assert result["total_targets"] == 0

    @pytest.mark.asyncio
    async def test_recommend_channels(self, agent):
        result = await agent.recommend_channels(budget=50000, priority_roles=["后端开发"])
        assert result["total_budget"] == 50000
        assert len(result["recommendations"]) == len(SOURCE_CHANNELS)
        total_pct = sum(r["budget_pct"] for r in result["recommendations"])
        assert abs(total_pct - 100) < 0.5

    @pytest.mark.asyncio
    async def test_recommend_channels_zero_budget(self, agent):
        result = await agent.recommend_channels(budget=0, priority_roles=[])
        assert result["total_budget"] == 0

    @pytest.mark.asyncio
    async def test_generate_outreach(self, agent):
        result = await agent.generate_outreach(
            candidate_name="张三",
            company="字节跳动",
            role="Python 工程师",
            personal_note="开源贡献者",
        )
        assert result["candidate"] == "张三"
        assert len(result["templates"]) == 1
        template = result["templates"][0]
        assert "张三" in template["template"]
        assert "字节跳动" in template["template"]

    @pytest.mark.asyncio
    async def test_generate_jd_fallback(self, agent):
        """JDGen service is unavailable in test, returns stub."""
        with patch("app.services.jd_generator.JDGeneratorService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.generate_jd = AsyncMock(side_effect=RuntimeError("Service unavailable"))
            mock_svc_cls.return_value = mock_svc
            result = await agent.generate_jd(title="Python 工程师", requirements="3 年经验")
        assert result["fallback"] is True

    @pytest.mark.asyncio
    async def test_run_talent_map(self, agent):
        result = await agent.run({
            "agent_type": "talent_map",
            "target_companies": ["阿里"],
            "target_roles": ["后端"],
        })
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_channel_strategy(self, agent):
        result = await agent.run({
            "agent_type": "channel_strategy",
            "budget": 30000,
        })
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_outreach(self, agent):
        result = await agent.run({
            "agent_type": "outreach",
            "candidate_name": "李四",
            "company": "腾讯",
            "role": "前端",
        })
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_unknown_action(self, agent):
        result = await agent.run({"agent_type": "unknown_action"})
        assert result["status"] == "completed"
        assert "error" in result["result"]


# ══════════════════════════════════════════════════════════════
# OfferingAgent
# ══════════════════════════════════════════════════════════════

class TestOfferingAgent:
    @pytest.fixture
    def agent(self):
        return OfferingAgent()

    def test_init(self, agent):
        assert agent.name == "offering"

    def test_get_salary_benchmark(self, agent):
        result = agent.get_salary_benchmark(role="Python 工程师", location="北京")
        assert result["role"] == "Python 工程师"
        assert result["location"] == "北京"
        assert "p50" in result

    def test_calculate_total_package(self, agent):
        result = agent.calculate_total_package(
            base=300000, bonus_pct=15, equity_yearly=50000, benefits=10000,
        )
        assert result["base"] == 300000
        assert result["bonus"] == 45000
        assert result["equity_yearly"] == 50000
        assert result["total_package"] == 405000

    def test_calculate_total_package_defaults(self, agent):
        result = agent.calculate_total_package(base=200000)
        assert result["total_package"] > 200000

    @pytest.mark.asyncio
    async def test_generate_offer_letter(self, agent):
        package = agent.calculate_total_package(base=300000)
        letter = await agent.generate_offer_letter(
            candidate_name="张三",
            title="Python 工程师",
            company="TechCo",
            package=package,
            start_date="2026-07-01",
        )
        assert letter["candidate_name"] == "张三"
        assert letter["status"] == "draft"
        assert "¥" in letter["offer_letter"]
        assert "TechCo" in letter["offer_letter"]

    @pytest.mark.asyncio
    async def test_recommend_negotiation_strategy(self, agent):
        result = await agent.recommend_negotiation_strategy(
            scenario="competing_offer",
            current_package={"total_package": 300000},
        )
        assert result["scenario"] == "竞品 Offer"
        assert result["max_adjustment_pct"] == 15
        assert result["adjusted_total"] == 345000

    @pytest.mark.asyncio
    async def test_recommend_negotiation_unknown_scenario_defaults(self, agent):
        result = await agent.recommend_negotiation_strategy(scenario="unknown")
        assert result["scenario"] == "已有意向"  # default fallback

    def test_assess_risk_low(self, agent):
        result = agent.assess_risk("张三", {"total_package": 200000, "bonus_pct": 10})
        assert result["risk_level"] == "low"

    def test_assess_risk_medium(self, agent):
        result = agent.assess_risk("张三", {"total_package": 600000, "bonus_pct": 25}, scenario="competing_offer")
        assert result["risk_level"] == "medium"

    def test_assess_risk_high(self, agent):
        result = agent.assess_risk("张三", {"total_package": 1500000, "bonus_pct": 35}, scenario="competing_offer")
        assert result["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_run_calculate(self, agent):
        result = await agent.run({"action": "calculate", "base": 300000})
        assert result["status"] == "completed"
        assert result["result"]["total_package"] > 0

    @pytest.mark.asyncio
    async def test_run_benchmark(self, agent):
        result = await agent.run({"action": "benchmark", "role": "工程师"})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_offer_letter(self, agent):
        result = await agent.run({
            "action": "offer_letter",
            "candidate_name": "李四",
            "title": "工程师",
            "company": "TestCo",
            "package": {"base": 300000, "total_package": 400000},
            "start_date": "2026-08-01",
        })
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_negotiation(self, agent):
        result = await agent.run({"action": "negotiation", "scenario": "key_talent"})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_risk_assessment(self, agent):
        result = await agent.run({
            "action": "risk_assessment",
            "candidate_name": "王五",
            "package": {"total_package": 500000, "bonus_pct": 15},
        })
        assert result["status"] == "completed"

    def test_negotiation_scenarios_complete(self):
        assert "competing_offer" in NEGOTIATION_SCENARIOS
        assert "expectation_too_high" in NEGOTIATION_SCENARIOS
        assert "hesitating" in NEGOTIATION_SCENARIOS
        assert "interested" in NEGOTIATION_SCENARIOS
        assert "key_talent" in NEGOTIATION_SCENARIOS


# ══════════════════════════════════════════════════════════════
# OnboardingAgent
# ══════════════════════════════════════════════════════════════

class TestOnboardingAgent:
    @pytest.fixture
    def agent(self):
        return OnboardingAgent()

    def test_init(self, agent):
        assert agent.name == "onboarding"

    @pytest.mark.asyncio
    async def test_generate_plan(self, agent):
        plan = await agent.generate_plan("张三", "Python 工程师", "技术部")
        assert plan["candidate_name"] == "张三"
        assert plan["title"] == "Python 工程师"
        assert plan["department"] == "技术部"
        assert len(plan["onboarding_plan"]["milestones"]) == 8
        assert len(plan["check_in_schedule"]) == 5

    @pytest.mark.asyncio
    async def test_generate_plan_milestone_order(self, agent):
        plan = await agent.generate_plan("A", "B", "C")
        milestones = plan["onboarding_plan"]["milestones"]
        ids = [m["id"] for m in milestones]
        assert ids == ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"]

    @pytest.mark.asyncio
    async def test_update_milestone(self, agent):
        plan = await agent.generate_plan("张三", "工程师", "技术部")
        updated = agent.update_milestone(plan, "M1", "completed", note="已发送邮件")
        assert updated["updated"] is True
        assert updated["new_status"] == "completed"
        # verify the plan was mutated
        m1 = [m for m in plan["onboarding_plan"]["milestones"] if m["id"] == "M1"][0]
        assert m1["status"] == "completed"
        assert m1["note"] == "已发送邮件"

    @pytest.mark.asyncio
    async def test_update_milestone_not_found(self, agent):
        plan = await agent.generate_plan("张三", "工程师", "技术部")
        updated = agent.update_milestone(plan, "M99", "completed")
        assert updated["updated"] is False

    @pytest.mark.asyncio
    async def test_probation_review_on_track(self, agent):
        result = await agent.probation_review("张三", score=8.5, feedback="表现优秀")
        assert result["probation_review"]["status"] == "on_track"
        assert result["probation_review"]["score"] == 8.5

    @pytest.mark.asyncio
    async def test_probation_review_at_risk(self, agent):
        result = await agent.probation_review("张三", score=6.0)
        assert result["probation_review"]["status"] == "at_risk"

    @pytest.mark.asyncio
    async def test_probation_review_concerned(self, agent):
        result = await agent.probation_review("张三", score=4.0)
        assert result["probation_review"]["status"] == "concerned"

    @pytest.mark.asyncio
    async def test_run_plan(self, agent):
        result = await agent.run({
            "action": "plan",
            "candidate_name": "张三",
            "title": "工程师",
            "department": "技术部",
        })
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_update_milestone(self, agent):
        plan = await agent.generate_plan("张三", "工程师", "技术部")
        result = await agent.run({
            "action": "update_milestone",
            "plan": plan,
            "milestone_id": "M1",
            "status": "completed",
        })
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_probation_review(self, agent):
        result = await agent.run({"action": "probation_review", "score": 9.0})
        assert result["status"] == "completed"

    def test_milestones_complete(self):
        assert len(ONBOARDING_MILESTONES) == 8


# ══════════════════════════════════════════════════════════════
# AnalyticsAgent
# ══════════════════════════════════════════════════════════════

class TestAnalyticsAgent:
    @pytest.fixture
    def agent(self):
        return AnalyticsAgent()

    def test_init(self, agent):
        assert agent.name == "analytics"

    def test_build_funnel(self, agent):
        result = agent.build_funnel(applied=100, screened=60, interviewed=30, offered=10, hired=5)
        funnel = result["funnel"]
        assert funnel["applied"] == 100
        assert funnel["conversion_rates"]["screen_rate"] == 60.0
        assert funnel["conversion_rates"]["interview_rate"] == 50.0
        assert funnel["conversion_rates"]["offer_rate"] == pytest.approx(33.3, rel=0.1)
        assert funnel["conversion_rates"]["hire_rate"] == 50.0

    def test_build_funnel_zero_denominator(self, agent):
        result = agent.build_funnel(applied=0, screened=0, interviewed=0, offered=0, hired=0)
        rates = result["funnel"]["conversion_rates"]
        for v in rates.values():
            assert v == 0.0

    def test_analyze_channels(self, agent):
        channels = [
            {"name": "LinkedIn", "applications": 50, "cost": 4000, "conversions": 5},
            {"name": "BOSS", "applications": 100, "cost": 3000, "conversions": 15},
        ]
        result = agent.analyze_channels(channels)
        assert len(result["channels"]) == 2
        # sorted by cost per applicant ascending
        assert result["channels"][0]["name"] == "BOSS"

    def test_analyze_channels_empty(self, agent):
        result = agent.analyze_channels([])
        assert result["channels"] == []

    def test_calculate_kpi(self, agent):
        result = agent.calculate_kpi(
            time_to_fill_days=45, offers_sent=10, offers_accepted=7,
            hires=5, total_cost=50000, interviewed=20, offered=10,
        )
        kpi = result["kpi"]
        assert kpi["time_to_fill_days"] == 45.0
        assert kpi["offer_acceptance_rate"] == 70.0
        assert kpi["cost_per_hire"] == 10000.0
        assert kpi["interview_to_offer_ratio"] == 50.0

    def test_calculate_kpi_zero_divisions(self, agent):
        result = agent.calculate_kpi()
        kpi = result["kpi"]
        assert kpi["offer_acceptance_rate"] == 0.0
        assert kpi["cost_per_hire"] == 0.0

    def test_detect_anomalies(self, agent):
        data = [
            {"name": "BOSS", "screen_rate": 50, "interview_rate": 30, "offer_rate": 20,
             "screen_rate_prev": 80, "interview_rate_prev": 40, "offer_rate_prev": 25},
        ]
        result = agent.detect_anomalies(data)
        assert len(result["anomalies"]) >= 1
        anomaly = result["anomalies"][0]
        assert anomaly["alert"] is True

    def test_detect_anomalies_clear(self, agent):
        data = [
            {"name": "BOSS", "screen_rate": 75, "interview_rate": 35, "offer_rate": 20,
             "screen_rate_prev": 70, "interview_rate_prev": 30, "offer_rate_prev": 18},
        ]
        result = agent.detect_anomalies(data)
        assert len(result["anomalies"]) == 0

    @pytest.mark.asyncio
    async def test_generate_report(self, agent):
        result = await agent.generate_report(
            funnel_data={"applied": 100, "screened": 60, "interviewed": 30, "offered": 10, "hired": 5},
            channel_data=[{"name": "LinkedIn", "applications": 50, "cost": 4000, "conversions": 5}],
            kpi_data={"time_to_fill_days": 45, "offers_sent": 10, "offers_accepted": 7,
                      "hires": 5, "total_cost": 50000, "interviewed": 20, "offered": 10},
        )
        assert "funnel" in result
        assert "channels" in result
        assert "kpi" in result
        assert "anomalies" in result
        assert "report_summary" in result
        assert "100" in result["report_summary"]

    @pytest.mark.asyncio
    async def test_run_funnel(self, agent):
        result = await agent.run({"action": "funnel", "applied": 100, "screened": 50})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_channels(self, agent):
        result = await agent.run({"action": "channels", "channels": []})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_kpi(self, agent):
        result = await agent.run({"action": "kpi", "hires": 5, "total_cost": 50000})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_anomalies(self, agent):
        result = await agent.run({"action": "anomalies", "period_data": []})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_report(self, agent):
        result = await agent.run({
            "action": "report",
            "funnel_data": {"applied": 100, "screened": 50},
            "channel_data": [],
            "kpi_data": {},
        })
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_unknown_action(self, agent):
        result = await agent.run({"action": "unknown"})
        assert result["status"] == "completed"
        assert "error" in result["result"]

    def test_anomaly_thresholds(self):
        assert "screen_rate" in ANOMALY_THRESHOLDS
        assert "interview_rate" in ANOMALY_THRESHOLDS
        assert "offer_rate" in ANOMALY_THRESHOLDS
