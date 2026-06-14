"""
Tests for sentiment aggregation engine (aggregator.py)

Tests:
- Composite score calculation (weighted average)
- Top3 factor selection (risk-first principle)
- Sentiment label mapping (7 tiers)
- Operation advice generation
- Divergence calculation
- Single index sentiment calculation
- Multi-index composite sentiment
- Conclusion generation

⚠️ V5.0: aggregator.py was deleted in T4, replaced by confidence.py + signal_mapper.py.
These tests are preserved for reference but skipped.
"""
import pytest
pytest.importorskip("app.engine.aggregator", reason="V5.0: aggregator.py deleted in T4, replaced by confidence.py + signal_mapper.py")

from app.engine.scoring import FactorScore, score_rsi, score_volatility
from app.engine.aggregator import (
    DEFAULT_WEIGHTS,
    INDEX_MARKET_WEIGHTS,
    CompositeResult,
    calculate_composite_score,
    select_top3_factors,
    get_sentiment_label,
    SENTIMENT_LABEL_CN,
    get_operation_advice,
    calculate_index_sentiment,
    calculate_composite_sentiment,
    calculate_divergence,
    generate_conclusion,
)


# ============================================================
# Helper: Create a standard 7-factor score dict
# ============================================================
def make_factor_scores(scores: dict[str, float]) -> dict[str, FactorScore]:
    """Create factor score dict from {name: score} mapping."""
    result = {}
    for name, score in scores.items():
        if score < 25:
            label = "extreme_fear"
            is_extreme = True
            extreme_type = "oversold"
        elif score < 40:
            label = "fear"
            is_extreme = False
            extreme_type = ""
        elif score < 60:
            label = "neutral"
            is_extreme = False
            extreme_type = ""
        elif score < 75:
            label = "greed"
            is_extreme = False
            extreme_type = ""
        else:
            label = "extreme_greed"
            is_extreme = True
            extreme_type = "overbought"
        result[name] = FactorScore(
            factor_name=name,
            raw_value=0.0,
            score=score,
            label=label,
            is_extreme=is_extreme,
            extreme_type=extreme_type,
        )
    return result


def make_neutral_factors() -> dict[str, FactorScore]:
    """Create a neutral 7-factor score dict (all 50)."""
    return make_factor_scores({
        "波动率": 50.0,
        "换手率": 50.0,
        "涨跌比": 50.0,
        "新高占比": 50.0,
        "融资融券": 50.0,
        "股债比": 50.0,
        "RSI": 50.0,
    })


# ============================================================
# Weight configuration tests
# ============================================================
class TestWeights:
    """Test weight configuration"""

    def test_default_weights_sum_to_one(self):
        """DEFAULT_WEIGHTS should sum to approximately 1.0"""
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0"

    def test_all_7_factors_have_weights(self):
        """All 7 factors must have weights defined"""
        expected_factors = {"波动率", "换手率", "涨跌比", "新高占比", "融资融券", "股债比", "RSI"}
        assert set(DEFAULT_WEIGHTS.keys()) == expected_factors

    def test_index_market_weights_sum_to_one(self):
        """INDEX_MARKET_WEIGHTS should sum to approximately 1.0"""
        total = sum(INDEX_MARKET_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_index_market_weights_have_4_indexes(self):
        """4 major indexes must have weights"""
        assert len(INDEX_MARKET_WEIGHTS) == 4


# ============================================================
# Composite score calculation tests
# ============================================================
class TestCalculateCompositeScore:
    """Test calculate_composite_score function"""

    def test_all_neutral_returns_50(self):
        """All factors at 50 should give composite 50"""
        factors = make_neutral_factors()
        result = calculate_composite_score(factors)
        assert result == 50.0

    def test_weighted_average_correct(self):
        """Verify weighted average calculation"""
        factors = make_factor_scores({
            "波动率": 100.0,
            "换手率": 0.0,
            "涨跌比": 50.0,
            "新高占比": 50.0,
            "融资融券": 50.0,
            "股债比": 50.0,
            "RSI": 50.0,
        })
        result = calculate_composite_score(factors)
        # Expected: (100*0.15 + 0*0.10 + 50*0.15 + 50*0.12 + 50*0.18 + 50*0.15 + 50*0.15) / 1.0
        # = (15 + 0 + 7.5 + 6 + 9 + 7.5 + 7.5) = 52.5
        expected = (100 * 0.15 + 0 * 0.10 + 50 * 0.15 + 50 * 0.12 + 50 * 0.18 + 50 * 0.15 + 50 * 0.15)
        assert result == pytest.approx(expected, 0.1)

    def test_custom_weights(self):
        """Custom weights should override defaults"""
        factors = make_factor_scores({
            "波动率": 100.0,
            "换手率": 0.0,
            "涨跌比": 0.0,
            "新高占比": 0.0,
            "融资融券": 0.0,
            "股债比": 0.0,
            "RSI": 0.0,
        })
        custom_weights = {
            "波动率": 1.0,
            "换手率": 0.0,
            "涨跌比": 0.0,
            "新高占比": 0.0,
            "融资融券": 0.0,
            "股债比": 0.0,
            "RSI": 0.0,
        }
        result = calculate_composite_score(factors, custom_weights)
        assert result == 100.0

    def test_empty_factors_returns_50(self):
        """Empty factor dict returns 50"""
        result = calculate_composite_score({})
        assert result == 50.0

    def test_missing_factor_uses_default_weight(self):
        """Missing weight in weights dict uses 0.1 default"""
        factors = make_factor_scores({
            "波动率": 100.0,
        })
        # weight not in custom weights → uses 0.1 from weights.get(name, 0.1)
        result = calculate_composite_score(factors, {"波动率": 0.5})
        # 100 * 0.5 / 0.5 = 100.0
        assert result == 100.0

    def test_uneven_weights_normalized(self):
        """Total weight normalizes the result"""
        factors = make_factor_scores({
            "波动率": 80.0,
            "RSI": 20.0,
        })
        weights = {"波动率": 0.5, "RSI": 0.5}
        result = calculate_composite_score(factors, weights)
        assert result == 50.0  # (80*0.5 + 20*0.5) / 1.0 = 50

    def test_extreme_all_fear(self):
        """All factors at 0 should give 0"""
        factors = make_factor_scores({
            "波动率": 0.0,
            "换手率": 0.0,
            "涨跌比": 0.0,
            "新高占比": 0.0,
            "融资融券": 0.0,
            "股债比": 0.0,
            "RSI": 0.0,
        })
        result = calculate_composite_score(factors)
        assert result == 0.0

    def test_extreme_all_greed(self):
        """All factors at 100 should give 100"""
        factors = make_factor_scores({
            "波动率": 100.0,
            "换手率": 100.0,
            "涨跌比": 100.0,
            "新高占比": 100.0,
            "融资融券": 100.0,
            "股债比": 100.0,
            "RSI": 100.0,
        })
        result = calculate_composite_score(factors)
        assert result == 100.0


# ============================================================
# Top3 factor selection tests
# ============================================================
class TestSelectTop3Factors:
    """Test select_top3_factors function — risk-first principle"""

    def test_returns_exactly_3(self):
        """Should return exactly 3 factors when 7 are given"""
        factors = make_neutral_factors()
        result = select_top3_factors(factors)
        assert len(result) == 3

    def test_extreme_factors_prioritized(self):
        """Extreme factors should be prioritized over non-extreme"""
        factors = make_factor_scores({
            "波动率": 50.0,    # neutral
            "换手率": 55.0,    # neutral
            "涨跌比": 52.0,    # neutral
            "新高占比": 48.0,   # neutral
            "融资融券": 10.0,   # extreme_fear
            "股债比": 90.0,    # extreme_greed
            "RSI": 51.0,      # neutral
        })
        result = select_top3_factors(factors)
        # Extreme factors should appear in top 3
        extreme_names = {f.factor_name for f in result if f.is_extreme}
        assert "融资融券" in extreme_names or "股债比" in extreme_names

    def test_low_score_prioritized_over_high(self):
        """Risk bias: lower scores (fear) prioritized over high scores (greed) at same deviation"""
        factors = make_factor_scores({
            "波动率": 80.0,    # deviation 30
            "换手率": 20.0,    # deviation 30 (same), but lower score → risk priority
            "涨跌比": 50.0,
            "新高占比": 50.0,
            "融资融券": 50.0,
            "股债比": 50.0,
            "RSI": 50.0,
        })
        result = select_top3_factors(factors)
        # Both have deviation 30 from 50. The lower score (20) should rank higher.
        first = result[0]
        # The first should be either the low score (risk bias) or both extreme factors tie
        # At same deviation, risk_bias 1.1 vs 0.9 means 20 gets -33 vs 80 gets -27
        # So 20 (score 20, deviation 30, risk_bias 1.1) → sort_key = (1, -33, 20)
        # 80 (score 80, deviation 30, risk_bias 0.9) → sort_key = (1, -27, 80)
        # Lower sort_key first: (1, -33, 20) < (1, -27, 80) → 20 wins
        assert first.score == 20.0

    def test_higher_deviation_prioritized(self):
        """Larger deviation from 50 should be prioritized"""
        factors = make_factor_scores({
            "波动率": 75.0,    # deviation 25
            "换手率": 15.0,    # deviation 35 — bigger
            "涨跌比": 50.0,
            "新高占比": 50.0,
            "融资融券": 50.0,
            "股债比": 50.0,
            "RSI": 50.0,
        })
        result = select_top3_factors(factors)
        assert result[0].factor_name == "换手率"  # deviation 35 > 25

    def test_extreme_always_first(self):
        """An extreme factor should always come before non-extreme, regardless of deviation"""
        factors = make_factor_scores({
            "波动率": 55.0,     # deviation 5, non-extreme
            "换手率": 10.0,     # extreme_fear, deviation 40
            "涨跌比": 50.0,
            "新高占比": 50.0,
            "融资融券": 50.0,
            "股债比": 50.0,
            "RSI": 50.0,
        })
        result = select_top3_factors(factors)
        assert result[0].factor_name == "换手率"  # extreme
        assert result[0].is_extreme is True

    def test_top3_from_fewer_factors(self):
        """If fewer than 3 factors, return all available"""
        factors = make_factor_scores({
            "波动率": 50.0,
            "RSI": 30.0,
        })
        result = select_top3_factors(factors)
        assert len(result) == 2


# ============================================================
# Sentiment label mapping tests
# ============================================================
class TestSentimentLabel:
    """Test get_sentiment_label function — 7-tier mapping"""

    def test_label_extreme_fear(self):
        """score < 20 → extreme_fear"""
        assert get_sentiment_label(0) == "extreme_fear"
        assert get_sentiment_label(10) == "extreme_fear"
        assert get_sentiment_label(19.9) == "extreme_fear"

    def test_label_fear(self):
        """20 <= score < 40 → fear"""
        assert get_sentiment_label(20) == "fear"
        assert get_sentiment_label(30) == "fear"
        assert get_sentiment_label(39.9) == "fear"

    def test_label_neutral(self):
        """40 <= score < 60 → neutral"""
        assert get_sentiment_label(40) == "neutral"
        assert get_sentiment_label(50) == "neutral"
        assert get_sentiment_label(59.9) == "neutral"

    def test_label_greed(self):
        """60 <= score < 80 → greed"""
        assert get_sentiment_label(60) == "greed"
        assert get_sentiment_label(70) == "greed"
        assert get_sentiment_label(79.9) == "greed"

    def test_label_extreme_greed(self):
        """score >= 80 → extreme_greed"""
        assert get_sentiment_label(80) == "extreme_greed"
        assert get_sentiment_label(90) == "extreme_greed"
        assert get_sentiment_label(100) == "extreme_greed"

    def test_all_7_labels_returned(self):
        """All 7 possible labels can be returned"""
        labels = set()
        for score in [5, 30, 50, 70, 95]:
            labels.add(get_sentiment_label(score))
        # We get 5 labels but "neutral" is used for 2 adjacent ranges
        assert len(labels) >= 5

    def test_sentiment_label_cn_mapping(self):
        """Chinese label mapping should have all English labels"""
        assert "extreme_fear" in SENTIMENT_LABEL_CN
        assert "fear" in SENTIMENT_LABEL_CN
        assert "neutral" in SENTIMENT_LABEL_CN
        assert "greed" in SENTIMENT_LABEL_CN
        assert "extreme_greed" in SENTIMENT_LABEL_CN
        assert SENTIMENT_LABEL_CN["extreme_fear"] == "极度恐慌"
        assert SENTIMENT_LABEL_CN["fear"] == "恐慌"
        assert SENTIMENT_LABEL_CN["neutral"] == "中性"
        assert SENTIMENT_LABEL_CN["greed"] == "乐观"
        assert SENTIMENT_LABEL_CN["extreme_greed"] == "极度乐观"


# ============================================================
# Operation advice tests
# ============================================================
class TestOperationAdvice:
    """Test get_operation_advice function"""

    def test_advice_extreme_fear_bottom(self):
        """score < 15: 极度恐慌 → 分批建仓"""
        advice = get_operation_advice(10)
        assert "极度恐慌" in advice
        assert "分批建仓" in advice

    def test_advice_fear(self):
        """15 <= score < 25: 恐慌"""
        advice = get_operation_advice(20)
        assert "恐慌" in advice
        assert "试探性买入" in advice

    def test_advice_partial_fear(self):
        """25 <= score < 35: 偏恐慌"""
        advice = get_operation_advice(30)
        assert "偏恐慌" in advice
        assert "观望" in advice

    def test_advice_weak(self):
        """35 <= score < 45: 偏弱"""
        advice = get_operation_advice(40)
        assert "偏弱" in advice

    def test_advice_neutral(self):
        """45 <= score < 55: 中性"""
        advice = get_operation_advice(50)
        assert "中性" in advice
        assert "均衡" in advice or "中性仓位" in advice

    def test_advice_optimistic(self):
        """55 <= score < 65: 偏乐观"""
        advice = get_operation_advice(60)
        assert "偏乐观" in advice or "情绪偏暖" in advice

    def test_advice_greed(self):
        """65 <= score < 75: 乐观"""
        advice = get_operation_advice(70)
        assert "乐观" in advice
        assert "追高" in advice

    def test_advice_partial_hot(self):
        """75 <= score < 85: 偏热"""
        advice = get_operation_advice(80)
        assert "偏热" in advice
        assert "减仓" in advice

    def test_advice_extreme_greed(self):
        """score >= 85: 极度乐观"""
        advice = get_operation_advice(90)
        assert "极度乐观" in advice
        assert "减仓" in advice
        assert "30%" in advice

    def test_advice_returns_string(self):
        """All scores should return non-empty string"""
        for score in [0, 15, 30, 50, 70, 90, 100]:
            advice = get_operation_advice(score)
            assert isinstance(advice, str)
            assert len(advice) > 10


# ============================================================
# Divergence calculation tests
# ============================================================
class TestDivergence:
    """Test calculate_divergence function"""

    def test_divergence_single_index_zero(self):
        """Single index should have zero divergence"""
        result = CompositeResult(
            index_code="SH000001",
            index_name="上证综指",
            composite_score=50.0,
        )
        div = calculate_divergence({"SH000001": result})
        assert div == 0.0

    def test_divergence_two_identical(self):
        """Two indexes with same score → zero divergence"""
        r1 = CompositeResult(index_code="A", index_name="A", composite_score=50.0)
        r2 = CompositeResult(index_code="B", index_name="B", composite_score=50.0)
        div = calculate_divergence({"A": r1, "B": r2})
        assert div == 0.0

    def test_divergence_two_different(self):
        """Two indexes with different scores → positive divergence"""
        r1 = CompositeResult(index_code="A", index_name="A", composite_score=40.0)
        r2 = CompositeResult(index_code="B", index_name="B", composite_score=60.0)
        div = calculate_divergence({"A": r1, "B": r2})
        # mean=50, variance=((40-50)^2+(60-50)^2)/2 = 100, std=10, div=min(40,100)=40
        assert div == 40.0

    def test_divergence_high_spread(self):
        """Large spread should produce high divergence (capped at 100)"""
        r1 = CompositeResult(index_code="A", index_name="A", composite_score=0.0)
        r2 = CompositeResult(index_code="B", index_name="B", composite_score=100.0)
        div = calculate_divergence({"A": r1, "B": r2})
        # mean=50, variance=((0-50)^2+(100-50)^2)/2 = 2500, std=50, div=min(200,100)=100
        assert div == 100.0

    def test_divergence_empty(self):
        """Empty dict should return 0"""
        div = calculate_divergence({})
        assert div == 0.0


# ============================================================
# Single index sentiment calculation tests
# ============================================================
class TestCalculateIndexSentiment:
    """Test calculate_index_sentiment function"""

    def test_basic_calculation(self):
        """Basic single index calculation"""
        factors = make_neutral_factors()
        result = calculate_index_sentiment("SH000001", "上证综指", factors)
        assert result.index_code == "SH000001"
        assert result.index_name == "上证综指"
        assert result.composite_score == 50.0
        assert result.sentiment_label == "neutral"
        assert len(result.top3_factors) == 3
        assert len(result.conclusion) > 0
        assert len(result.operation_advice) > 0

    def test_trend_up_with_previous_score(self):
        """Trend should be 'up' when score increases significantly"""
        factors = make_factor_scores({
            "波动率": 80.0,
            "换手率": 80.0,
            "涨跌比": 80.0,
            "新高占比": 80.0,
            "融资融券": 80.0,
            "股债比": 80.0,
            "RSI": 80.0,
        })
        result = calculate_index_sentiment("SH000001", "上证综指", factors, previous_score=30.0)
        # composite = 80, delta = 50 > 5 → up
        assert result.trend_direction == "up"
        assert result.trend_strength > 0

    def test_trend_down_with_previous_score(self):
        """Trend should be 'down' when score decreases significantly"""
        factors = make_factor_scores({
            "波动率": 20.0,
            "换手率": 20.0,
            "涨跌比": 20.0,
            "新高占比": 20.0,
            "融资融券": 20.0,
            "股债比": 20.0,
            "RSI": 20.0,
        })
        result = calculate_index_sentiment("SH000001", "上证综指", factors, previous_score=70.0)
        assert result.trend_direction == "down"

    def test_trend_stable_small_change(self):
        """Trend should be 'stable' when change is small"""
        factors = make_neutral_factors()
        result = calculate_index_sentiment("SH000001", "上证综指", factors, previous_score=52.0)
        assert result.trend_direction == "stable"

    def test_no_previous_score_stable(self):
        """No previous score → trend is stable with 0 strength"""
        factors = make_neutral_factors()
        result = calculate_index_sentiment("SH000001", "上证综指", factors)
        assert result.trend_direction == "stable"
        assert result.trend_strength == 0.0

    def test_extreme_detection(self):
        """is_extreme should be True when any factor is extreme"""
        factors = make_factor_scores({
            "波动率": 50.0,
            "换手率": 50.0,
            "涨跌比": 50.0,
            "新高占比": 50.0,
            "融资融券": 10.0,  # extreme_fear
            "股债比": 50.0,
            "RSI": 50.0,
        })
        result = calculate_index_sentiment("SH000001", "上证综指", factors)
        assert result.is_extreme is True
        assert len(result.abnormal_signals) > 0

    def test_no_extreme_detection(self):
        """is_extreme should be False when no factor is extreme"""
        factors = make_neutral_factors()
        result = calculate_index_sentiment("SH000001", "上证综指", factors)
        assert result.is_extreme is False
        assert len(result.abnormal_signals) == 0


# ============================================================
# Multi-index composite sentiment tests
# ============================================================
class TestCalculateCompositeSentiment:
    """Test calculate_composite_sentiment function"""

    def test_basic_composite(self):
        """Basic multi-index composite calculation"""
        r1 = CompositeResult(
            index_code="SH000001", index_name="上证综指",
            composite_score=50.0,
            factor_scores=make_neutral_factors(),
        )
        r2 = CompositeResult(
            index_code="SH000300", index_name="沪深300",
            composite_score=60.0,
            factor_scores=make_neutral_factors(),
        )
        result = calculate_composite_sentiment({"SH000001": r1, "SH000300": r2})
        assert result.index_code == "COMPOSITE"
        assert result.index_name == "综合情绪"
        assert result.divergence_index >= 0
        assert len(result.top3_factors) == 3
        assert len(result.conclusion) > 0
        assert len(result.operation_advice) > 0

    def test_composite_with_custom_weights(self):
        """Custom index weights"""
        r1 = CompositeResult(
            index_code="SH000001", index_name="上证综指",
            composite_score=100.0,
            factor_scores=make_neutral_factors(),
        )
        r2 = CompositeResult(
            index_code="SH000300", index_name="沪深300",
            composite_score=0.0,
            factor_scores=make_neutral_factors(),
        )
        custom_weights = {"SH000001": 1.0, "SH000300": 0.0}
        result = calculate_composite_sentiment(
            {"SH000001": r1, "SH000300": r2},
            weights=custom_weights,
        )
        assert result.composite_score == 100.0


# ============================================================
# Conclusion generation tests
# ============================================================
class TestGenerateConclusion:
    """Test generate_conclusion function"""

    def test_conclusion_extreme_fear(self):
        conclusion = generate_conclusion(15, "extreme_fear", "stable")
        assert "极度恐慌" in conclusion
        assert "15" in conclusion

    def test_conclusion_fear(self):
        conclusion = generate_conclusion(30, "fear", "down")
        assert "情绪转弱" in conclusion
        assert "恐慌" in conclusion

    def test_conclusion_neutral(self):
        conclusion = generate_conclusion(50, "neutral", "stable")
        assert "中性" in conclusion
        assert "50" in conclusion

    def test_conclusion_greed(self):
        conclusion = generate_conclusion(70, "greed", "up")
        assert "情绪回暖" in conclusion
        assert "乐观" in conclusion

    def test_conclusion_extreme_greed(self):
        conclusion = generate_conclusion(90, "extreme_greed", "stable")
        assert "极度乐观" in conclusion
        assert "回调" in conclusion

    def test_conclusion_trend_prefix(self):
        """Up trend should have '情绪回暖，' prefix; down should have '情绪转弱，'"""
        up_conclusion = generate_conclusion(50, "neutral", "up")
        assert up_conclusion.startswith("情绪回暖，")

        down_conclusion = generate_conclusion(50, "neutral", "down")
        assert down_conclusion.startswith("情绪转弱，")

        stable_conclusion = generate_conclusion(50, "neutral", "stable")
        assert stable_conclusion.startswith("市场情绪中性")
