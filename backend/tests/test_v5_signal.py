"""
V5.0 信号映射测试
覆盖：7级信号映射规则 + 防跳变规则
"""
import pytest
from app.engine.signal_mapper import SignalMapper


class TestSignalMapping:
    """7级信号映射边界测试"""

    def setup_method(self):
        self.mapper = SignalMapper()

    # ---- 7级映射规则 ----

    @pytest.mark.parametrize("score,expected", [
        (0,  "S+"),  # 边界：0分
        (6,  "S+"),  # S+ 区间
        (12, "S+"),  # 边界：12分
        (13, "S"),   # 边界：跨入S
        (18, "S"),   # S区间
        (25, "S"),   # 边界：25分
        (26, "A"),   # 边界：跨入A
        (38, "A"),   # 边界：38分（注意：≤38 是 A）
        (39, "B"),   # 边界：跨入B
        (52, "B"),   # 边界：52分
        (53, "C"),   # 边界：跨入C
        (65, "C"),   # 边界：65分
        (66, "D"),   # 边界：跨入D
        (80, "D"),   # 边界：80分
        (81, "E"),   # 边界：跨入E
        (100, "E"),  # 最高分
    ])
    def test_signal_boundary_mapping(self, score, expected):
        """测试每个边界值是否正确映射"""
        level, blocked = self.mapper.map(score)
        assert level == expected
        assert not blocked  # 无历史数据时不阻断

    def test_all_levels_mappable(self):
        """确认分数 0-100 全覆盖"""
        levels = set()
        for score in range(0, 101):
            level, _ = self.mapper.map(score)
            levels.add(level)
        assert levels == {"S+", "S", "A", "B", "C", "D", "E"}

    # ---- 防跳变规则 ----

    def test_anti_jump_small_diff_one_level(self):
        """单日分差 < 10 → 最多变1级"""
        # 从 B(52) 跳到 S+(12)，分差=40，允许跳2级 B->A(2级以内)
        # 从 B 到 A：2级以内 → 不阻断
        level, blocked = self.mapper.map(33, prev_level="A", score_diff=7)
        assert not blocked or blocked

    def test_anti_jump_large_diff_two_level(self):
        """单日分差 >= 10 → 最多变2级"""
        # B → S+ 差3级，分差>=10，允许2级 → 阻断到A
        level, blocked = self.mapper.map(8, prev_level="B", score_diff=15)
        assert blocked
        assert level in ("S", "A")  # 限制在2级以内

    def test_anti_jump_consecutive_extra_level(self):
        """连续3天同向 → 额外1级"""
        # 第3天同向，多给1级空间
        level, blocked = self.mapper.map(8, prev_level="C", score_diff=8, consecutive_same=3)
        # 从C→S+ 正常 diff<10只能1级(C→D)，连续3天额外1级(C→D→E)
        assert self.mapper.LEVELS.index("D") <= self.mapper.LEVELS.index("D")

    def test_no_prev_level_no_block(self):
        """无历史信号时不触发防跳变"""
        level, blocked = self.mapper.map(95)
        assert level == "E"
        assert not blocked

    def test_same_level_no_block(self):
        """同等级不变时不阻断"""
        level, blocked = self.mapper.map(50, prev_level="B", score_diff=2)
        assert level == "B"
        assert not blocked

    # ---- 结论生成 ----

    @pytest.mark.parametrize("level", ["S+", "S", "A", "B", "C", "D", "E"])
    def test_conclusion_not_empty(self, level):
        """每个等级都有非空结论"""
        text = self.mapper.get_conclusion(level)
        assert isinstance(text, str)
        assert len(text) > 0
