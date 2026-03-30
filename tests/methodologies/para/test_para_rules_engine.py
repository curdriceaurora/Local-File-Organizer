"""Tests for PARA rules engine — targeting uncovered branches.

Covers: RuleCondition validation, RuleAction validation, Rule validation,
EvaluationContext properties, RuleEngine methods.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.methodologies.para.rules.engine import (
    ActionType,
    ConditionType,
    EvaluationContext,
    LogicalOperator,
    Rule,
    RuleAction,
    RuleCondition,
    RuleEngine,
    RuleMatchResult,
)

pytestmark = pytest.mark.unit


class TestRuleConditionValidation:
    """Test __post_init__ validation on RuleCondition — lines 90-93."""

    def test_composite_without_subconditions_raises(self) -> None:
        with pytest.raises(ValueError, match="Composite conditions must have subconditions"):
            RuleCondition(type=ConditionType.COMPOSITE, subconditions=None)

    def test_composite_with_empty_subconditions_raises(self) -> None:
        with pytest.raises(ValueError, match="Composite conditions must have subconditions"):
            RuleCondition(type=ConditionType.COMPOSITE, subconditions=[])

    def test_non_composite_without_values_or_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="requires values or threshold"):
            RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=None, threshold=None)

    def test_non_composite_with_values(self) -> None:
        cond = RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["test"])
        assert cond.values == ["test"]

    def test_non_composite_with_threshold(self) -> None:
        cond = RuleCondition(type=ConditionType.FILE_SIZE, threshold=1024.0)
        assert cond.threshold == 1024.0

    def test_composite_with_valid_subconditions(self) -> None:
        sub = RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["x"])
        cond = RuleCondition(
            type=ConditionType.COMPOSITE,
            operator=LogicalOperator.AND,
            subconditions=[sub],
        )
        assert len(cond.subconditions) == 1


class TestRuleActionValidation:
    """Test __post_init__ validation on RuleAction — lines 127-129."""

    def test_categorize_without_category_raises(self) -> None:
        with pytest.raises(ValueError, match="requires a category"):
            RuleAction(type=ActionType.CATEGORIZE, category=None, confidence=0.5)

    def test_categorize_with_invalid_category_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid PARA category"):
            RuleAction(type=ActionType.CATEGORIZE, category="invalid", confidence=0.5)

    def test_categorize_without_confidence_raises(self) -> None:
        with pytest.raises(ValueError, match="requires a confidence score"):
            RuleAction(type=ActionType.CATEGORIZE, category="project", confidence=None)

    def test_categorize_confidence_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="Confidence must be between"):
            RuleAction(type=ActionType.CATEGORIZE, category="project", confidence=1.5)

    def test_suggest_without_category_raises(self) -> None:
        with pytest.raises(ValueError, match="requires a category"):
            RuleAction(type=ActionType.SUGGEST, category=None, confidence=0.5)

    def test_valid_categorize_action(self) -> None:
        action = RuleAction(type=ActionType.CATEGORIZE, category="project", confidence=0.8)
        assert action.category == "project"

    def test_flag_review_no_category_needed(self) -> None:
        action = RuleAction(type=ActionType.FLAG_REVIEW)
        assert action.category is None


class TestRuleValidation:
    """Test Rule.__post_init__ validation — lines 156-161."""

    def _make_condition(self) -> RuleCondition:
        return RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["test"])

    def _make_action(self) -> RuleAction:
        return RuleAction(type=ActionType.CATEGORIZE, category="project", confidence=0.8)

    def test_rule_no_conditions_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one condition"):
            Rule(
                name="r", description="d", priority=1, conditions=[], actions=[self._make_action()]
            )

    def test_rule_no_actions_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one action"):
            Rule(
                name="r",
                description="d",
                priority=1,
                conditions=[self._make_condition()],
                actions=[],
            )

    def test_rule_negative_priority_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            Rule(
                name="r",
                description="d",
                priority=-1,
                conditions=[self._make_condition()],
                actions=[self._make_action()],
            )

    def test_valid_rule(self) -> None:
        rule = Rule(
            name="test",
            description="A test rule",
            priority=5,
            conditions=[self._make_condition()],
            actions=[self._make_action()],
        )
        assert rule.name == "test"
        assert rule.enabled is True


class TestEvaluationContext:
    """Test EvaluationContext properties — lines 187, 192, 197-204."""

    def test_file_extension(self) -> None:
        ctx = EvaluationContext(file_path=Path("/doc/report.PDF"))
        assert ctx.file_extension == ".pdf"

    def test_file_name(self) -> None:
        ctx = EvaluationContext(file_path=Path("/doc/report.pdf"))
        assert ctx.file_name == "report.pdf"

    def test_file_age_days_no_stat(self) -> None:
        ctx = EvaluationContext(file_path=Path("/doc/x.txt"), file_stat=None)
        assert ctx.file_age_days is None

    def test_file_age_days_no_created(self) -> None:
        ctx = EvaluationContext(file_path=Path("/doc/x.txt"), file_stat={"size": 100})
        assert ctx.file_age_days is None

    def test_file_age_days_with_datetime(self) -> None:
        created = datetime(2020, 1, 1, tzinfo=UTC)
        ctx = EvaluationContext(file_path=Path("/doc/x.txt"), file_stat={"created": created})
        age = ctx.file_age_days
        assert age is not None
        assert age > 0

    def test_file_age_days_naive_datetime(self) -> None:
        created = datetime(2020, 1, 1)  # noqa: DTZ001
        ctx = EvaluationContext(file_path=Path("/doc/x.txt"), file_stat={"created": created})
        age = ctx.file_age_days
        assert age is not None
        assert age > 0

    def test_file_age_days_non_datetime(self) -> None:
        ctx = EvaluationContext(file_path=Path("/doc/x.txt"), file_stat={"created": "2020-01-01"})
        assert ctx.file_age_days is None


class TestRuleEngine:
    """Test RuleEngine methods — lines 483-488, 499-500, 508-509, 525-560, 571-584."""

    def _make_engine(
        self,
    ) -> tuple[RuleEngine, MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
        parser = MagicMock()
        evaluator = MagicMock()
        executor = MagicMock()
        resolver = MagicMock()
        scorer = MagicMock()
        engine = RuleEngine(parser, evaluator, executor, resolver, scorer)
        return engine, parser, evaluator, executor, resolver, scorer

    def _make_rule(self, name: str = "r", enabled: bool = True) -> Rule:
        return Rule(
            name=name,
            description="desc",
            priority=1,
            enabled=enabled,
            conditions=[RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["test"])],
            actions=[RuleAction(type=ActionType.CATEGORIZE, category="project", confidence=0.8)],
        )

    def test_load_rules(self) -> None:
        engine, parser, *_ = self._make_engine()
        parser.parse_file.return_value = [self._make_rule()]
        count = engine.load_rules(Path("/rules.yaml"))
        assert count == 1
        assert len(engine.rules) == 1

    def test_add_rule(self) -> None:
        engine, parser, *_ = self._make_engine()
        parser.validate_rule.return_value = True
        rule = self._make_rule()
        engine.add_rule(rule)
        assert len(engine.rules) == 1

    def test_add_rule_invalid(self) -> None:
        engine, parser, *_ = self._make_engine()
        parser.validate_rule.return_value = False
        rule = self._make_rule()
        engine.add_rule(rule)
        assert len(engine.rules) == 0

    def test_evaluate_file_no_rules(self) -> None:
        engine, *_ = self._make_engine()
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        result = engine.evaluate_file(ctx)
        assert result is None

    def test_evaluate_file_disabled_rule_skipped(self) -> None:
        engine, _, evaluator, *_ = self._make_engine()
        engine.rules = [self._make_rule(enabled=False)]
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        result = engine.evaluate_file(ctx)
        assert result is None
        evaluator.evaluate_condition.assert_not_called()

    def test_evaluate_file_single_match(self) -> None:
        engine, _, evaluator, _, resolver, _ = self._make_engine()
        evaluator.evaluate_condition.return_value = True
        engine.rules = [self._make_rule()]
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        result = engine.evaluate_file(ctx)
        assert result is not None
        assert result.matched is True
        assert result.category == "project"
        assert result.confidence == 0.8

    def test_evaluate_file_condition_fails(self) -> None:
        engine, _, evaluator, *_ = self._make_engine()
        evaluator.evaluate_condition.return_value = False
        engine.rules = [self._make_rule()]
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        result = engine.evaluate_file(ctx)
        assert result is None

    def test_evaluate_file_multiple_matches_resolves(self) -> None:
        engine, _, evaluator, _, resolver, _ = self._make_engine()
        evaluator.evaluate_condition.return_value = True
        r1 = self._make_rule("r1")
        r2 = self._make_rule("r2")
        engine.rules = [r1, r2]
        resolved = RuleMatchResult(rule=r1, matched=True, confidence=0.9, category="project")
        resolver.resolve.return_value = resolved
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        result = engine.evaluate_file(ctx)
        assert result is resolved
        resolver.resolve.assert_called_once()

    def test_get_category_scores(self) -> None:
        engine, _, evaluator, _, _, scorer = self._make_engine()
        evaluator.evaluate_condition.return_value = True
        engine.rules = [self._make_rule()]
        scorer.calculate_category_scores.return_value = {"project": 0.9}
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        scores = engine.get_category_scores(ctx)
        assert scores == {"project": 0.9}

    def test_get_category_scores_disabled_rule(self) -> None:
        engine, _, evaluator, _, _, scorer = self._make_engine()
        engine.rules = [self._make_rule(enabled=False)]
        scorer.calculate_category_scores.return_value = {}
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        engine.get_category_scores(ctx)
        evaluator.evaluate_condition.assert_not_called()

    def test_evaluate_file_with_flag_review_only_action(self) -> None:
        """Test branch 542->548: actions loop completes without finding CATEGORIZE/SUGGEST."""
        engine, _, evaluator, *_ = self._make_engine()
        evaluator.evaluate_condition.return_value = True
        rule = Rule(
            name="flag_only",
            description="Only flags for review",
            priority=1,
            conditions=[RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["test"])],
            actions=[RuleAction(type=ActionType.FLAG_REVIEW)],
        )
        engine.rules = [rule]
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        result = engine.evaluate_file(ctx)
        assert result is not None
        assert result.matched is True
        assert result.confidence is None
        assert result.category is None

    def test_evaluate_file_multiple_actions_with_flag_first(self) -> None:
        """Test branch 543->542: loop continues when action is not CATEGORIZE/SUGGEST."""
        engine, _, evaluator, *_ = self._make_engine()
        evaluator.evaluate_condition.return_value = True
        rule = Rule(
            name="multi_action",
            description="Multiple actions",
            priority=1,
            conditions=[RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["test"])],
            actions=[
                RuleAction(type=ActionType.FLAG_REVIEW),
                RuleAction(type=ActionType.CATEGORIZE, category="project", confidence=0.7),
            ],
        )
        engine.rules = [rule]
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        result = engine.evaluate_file(ctx)
        assert result is not None
        assert result.matched is True
        assert result.confidence == 0.7
        assert result.category == "project"

    def test_get_category_scores_with_mixed_conditions(self) -> None:
        """Test branch 581->573: continues when all_conditions_met is False."""
        engine, _, evaluator, _, _, scorer = self._make_engine()

        # Create two rules with different conditions
        r1_cond = RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["pass"])
        r1 = Rule(
            name="passing",
            description="desc",
            priority=1,
            conditions=[r1_cond],
            actions=[RuleAction(type=ActionType.CATEGORIZE, category="project", confidence=0.8)],
        )

        r2_cond = RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["fail"])
        r2 = Rule(
            name="failing",
            description="desc",
            priority=1,
            conditions=[r2_cond],
            actions=[RuleAction(type=ActionType.CATEGORIZE, category="area", confidence=0.7)],
        )

        engine.rules = [r1, r2]

        # Set up side effect: r1 conditions pass, r2 conditions fail
        call_count = 0

        def eval_side_effect(cond: RuleCondition, ctx: EvaluationContext) -> bool:
            nonlocal call_count
            call_count += 1
            return cond == r1_cond

        evaluator.evaluate_condition.side_effect = eval_side_effect
        scorer.calculate_category_scores.return_value = {"project": 0.8}
        ctx = EvaluationContext(file_path=Path("/test.txt"))
        scores = engine.get_category_scores(ctx)
        assert scores == {"project": 0.8}
        # Both rules' conditions are evaluated (r1 passes, r2 fails and continues loop)
        assert call_count == 2
