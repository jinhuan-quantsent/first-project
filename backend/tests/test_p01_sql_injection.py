"""
P0-1 复检：迁移脚本 SQL 注入防护
验证 _validate_table_name() 白名单 & _sanitize_col_names() 正则过滤
"""
import pytest

from migrations.migrate_sqlite_to_supabase import (
    _validate_table_name,
    _sanitize_col_names,
    TABLES_TO_MIGRATE,
)


# ============================================================
# _validate_table_name 白名单校验
# ============================================================

class TestValidateTableName:
    """白名单校验：仅允许 TABLES_TO_MIGRATE 中存在的表名"""

    # --- 正向：合法表名通过 ---

    @pytest.mark.parametrize("table_name", TABLES_TO_MIGRATE)
    def test_valid_table_name_passes(self, table_name: str):
        """白名单中的表名应通过校验并原样返回"""
        result = _validate_table_name(table_name)
        assert result == table_name

    def test_factor_history_in_whitelist(self):
        """核心表 factor_history 必须在白名单中"""
        assert "factor_history" in TABLES_TO_MIGRATE

    # --- 反向：恶意表名被拒绝 ---

    def test_sql_injection_drop_table_rejected(self):
        """经典 SQL 注入 payload 应被白名单拒绝"""
        malicious = "factor_history'; DROP TABLE users; --"
        with pytest.raises(ValueError, match="非法表名"):
            _validate_table_name(malicious)

    def test_sql_injection_union_select_rejected(self):
        """UNION SELECT 注入应被拒绝"""
        malicious = "factor_history UNION SELECT * FROM users--"
        with pytest.raises(ValueError, match="非法表名"):
            _validate_table_name(malicious)

    def test_arbitrary_table_name_rejected(self):
        """不在白名单中的普通表名也应被拒绝"""
        with pytest.raises(ValueError, match="非法表名"):
            _validate_table_name("users")

    def test_empty_string_rejected(self):
        """空字符串应被拒绝"""
        with pytest.raises(ValueError, match="非法表名"):
            _validate_table_name("")

    def test_whitespace_rejected(self):
        """含空格的表名应被拒绝"""
        with pytest.raises(ValueError, match="非法表名"):
            _validate_table_name("factor history")

    def test_semicolon_injection_rejected(self):
        """含分号的表名应被拒绝"""
        with pytest.raises(ValueError, match="非法表名"):
            _validate_table_name("factor_history;")

    def test_comment_injection_rejected(self):
        """含 SQL 注释的表名应被拒绝"""
        with pytest.raises(ValueError, match="非法表名"):
            _validate_table_name("factor_history --")


# ============================================================
# _sanitize_col_names 正则过滤
# ============================================================

class TestSanitizeColNames:
    """正则过滤：仅允许 [a-zA-Z0-9_] 字符的列名"""

    # --- 正向：合法列名通过 ---

    @pytest.mark.parametrize("col", [
        "index_code",
        "factor_name",
        "trade_date",
        "raw_value",
        "id",
        "created_at",
        "updated_at",
        "col1",
        "COL_UPPER",
        "_underscore_prefix",
        "has_123_numbers",
    ])
    def test_valid_column_name_passes(self, col: str):
        """合法列名（仅含字母、数字、下划线）应通过"""
        result = _sanitize_col_names([col])
        assert result == [col]

    def test_multiple_valid_columns_pass(self):
        """多个合法列名同时通过"""
        cols = ["id", "index_code", "factor_name", "trade_date", "raw_value"]
        result = _sanitize_col_names(cols)
        assert result == cols

    def test_empty_list_passes(self):
        """空列表应返回空列表"""
        assert _sanitize_col_names([]) == []

    # --- 反向：恶意列名被拒绝 ---

    def test_sql_injection_drop_table_rejected(self):
        """经典 SQL 注入列名应被拒绝"""
        malicious = "id; DROP TABLE users; --"
        with pytest.raises(ValueError, match="非法列名"):
            _sanitize_col_names([malicious])

    def test_column_with_space_rejected(self):
        """含空格的列名应被拒绝"""
        with pytest.raises(ValueError, match="非法列名"):
            _sanitize_col_names(["col name"])

    def test_column_with_hyphen_rejected(self):
        """含连字符的列名应被拒绝"""
        with pytest.raises(ValueError, match="非法列名"):
            _sanitize_col_names(["col-name"])

    def test_column_with_dot_rejected(self):
        """含点的列名应被拒绝"""
        with pytest.raises(ValueError, match="非法列名"):
            _sanitize_col_names(["tbl.col"])

    def test_column_with_quote_rejected(self):
        """含引号的列名应被拒绝"""
        with pytest.raises(ValueError, match="非法列名"):
            _sanitize_col_names(["col'name"])

    def test_column_with_semicolon_rejected(self):
        """含分号的列名应被拒绝"""
        with pytest.raises(ValueError, match="非法列名"):
            _sanitize_col_names(["col;name"])

    def test_mixed_valid_and_invalid_rejected(self):
        """列表中包含一个非法列名，整个批次应被拒绝"""
        with pytest.raises(ValueError, match="非法列名"):
            _sanitize_col_names(["valid_col", "bad;col", "also_valid"])
