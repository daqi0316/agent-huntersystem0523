"""P6-12: CSM churn 监控 tests (constants + format_alert + endpoint 校验)。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestCSMConstants:
    def test_churn_7_days(self):
        from app.models.csm import CHURN_DAYS_NO_LOGIN
        assert CHURN_DAYS_NO_LOGIN == 7

    def test_low_health_threshold_30(self):
        from app.models.csm import LOW_HEALTH_THRESHOLD
        assert LOW_HEALTH_THRESHOLD == 30


class TestCSMTaskEnums:
    def test_five_task_types(self):
        from app.models.csm import CSMTaskType
        assert len(CSMTaskType) == 5

    def test_churn_risk_value(self):
        from app.models.csm import CSMTaskType
        assert CSMTaskType.CHURN_RISK.value == "churn_risk"

    def test_three_severities(self):
        from app.models.csm import CSMTaskSeverity
        assert len(CSMTaskSeverity) == 3

    def test_four_statuses(self):
        from app.models.csm import CSMTaskStatus
        assert len(CSMTaskStatus) == 4


class TestFormatCSMAlert:
    def test_empty_tasks(self):
        from app.services.csm import format_csm_alert
        text = format_csm_alert([])
        assert "无新 CSM 任务" in text

    def test_p1_task_included(self):
        from app.services.csm import format_csm_alert
        from app.models.csm import CSMTask, CSMTaskType, CSMTaskSeverity, CSMTaskStatus
        from datetime import datetime, timezone

        task = MagicMock()
        task.severity = CSMTaskSeverity.P1
        task.type = CSMTaskType.LOW_HEALTH
        task.title = "客户健康度 25 (高风险)"

        text = format_csm_alert([task])
        assert "P1" in text
        assert "客户健康度 25" in text

    def test_groups_by_severity(self):
        from app.services.csm import format_csm_alert
        from app.models.csm import CSMTask, CSMTaskType, CSMTaskSeverity, CSMTaskStatus

        tasks = []
        for sev, ttype in [
            (CSMTaskSeverity.P2, CSMTaskType.CHURN_RISK),
            (CSMTaskSeverity.P1, CSMTaskSeverity.P1),
            (CSMTaskSeverity.P2, CSMTaskType.TRIAL_EXPIRING),
        ]:
            t = MagicMock()
            t.severity = sev
            t.type = ttype
            t.title = f"Test {sev.value}"
            tasks.append(t)

        text = format_csm_alert(tasks)
        assert "P1" in text
        assert "P2" in text
        assert text.count("Test") == 3
