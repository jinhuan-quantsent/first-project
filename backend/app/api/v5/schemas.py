"""
V5 Schemas - 共享的 Pydantic 模型
"""
from pydantic import BaseModel


class PositionAdviceRequest(BaseModel):
    """仓位建议请求"""
    fund_code: str
    current_position_pct: float


class PositionExecuteRequest(BaseModel):
    """仓位执行请求"""
    fund_code: str
    target_position_pct: float
    signal_level: str
    confidence_stars: int
