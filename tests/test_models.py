"""Tests for the models and enums."""

from __future__ import annotations

import pytest

from valuesentinel.models import (
    COOLDOWN_SECONDS,
    CooldownPeriod,
    METRIC_DISPLAY_NAMES,
    MetricType,
    ConditionType,
    AlertStatus,
    AlertPriority,
)


class TestEnums:
    def test_all_metrics_have_display_names(self):
        for metric in MetricType:
            assert metric in METRIC_DISPLAY_NAMES

    def test_all_cooldowns_have_seconds(self):
        for cd in CooldownPeriod:
            assert cd in COOLDOWN_SECONDS
            assert COOLDOWN_SECONDS[cd] > 0

    def test_cooldown_ordering(self):
        vals = [COOLDOWN_SECONDS[cd] for cd in CooldownPeriod]
        assert vals == sorted(vals), "Cooldown values should be in ascending order"

    def test_condition_types(self):
        assert len(ConditionType) == 6
        assert ConditionType.HISTORICAL_LOW.value == "historical_low"
        assert ConditionType.HISTORICAL_HIGH.value == "historical_high"

    def test_alert_statuses(self):
        assert AlertStatus.ACTIVE.value == "active"
        assert AlertStatus.PAUSED.value == "paused"
        assert AlertStatus.STOPPED.value == "stopped"

    def test_priorities(self):
        assert len(AlertPriority) == 3
