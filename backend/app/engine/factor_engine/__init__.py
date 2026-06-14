"""
因子引擎包 — V5.0
注册 11 个因子，提供统一入口
"""
from app.engine.factor_engine.base import (
    BaseFactor,
    FactorRawValue,
    FactorQuantileResult,
    FactorSigmoidResult,
    DivergenceInfo,
    CompositeScore,
)
from app.engine.factor_engine.vol import VolFactor
from app.engine.factor_engine.adr import AdrFactor
from app.engine.factor_engine.erp import ErpFactor
from app.engine.factor_engine.flow import FlowFactor
from app.engine.factor_engine.etf import EtfFactor
from app.engine.factor_engine.nhnl import NhnlFactor
from app.engine.factor_engine.turn import TurnFactor
from app.engine.factor_engine.pos import PosFactor
from app.engine.factor_engine.nbf import NbfFactor
from app.engine.factor_engine.pcr import PcrFactor
from app.engine.factor_engine.newf import NewfFactor

# 11 因子名称列表（按架构附录顺序）
FACTOR_NAMES: list[str] = [
    "VOL", "ADR", "ERP", "FLOW", "ETF",
    "NHNL", "TURN", "POS", "NBF", "PCR", "NEWF",
]

# 因子类映射
FACTOR_CLASSES: dict[str, type[BaseFactor]] = {
    "VOL": VolFactor,
    "ADR": AdrFactor,
    "ERP": ErpFactor,
    "FLOW": FlowFactor,
    "ETF": EtfFactor,
    "NHNL": NhnlFactor,
    "TURN": TurnFactor,
    "POS": PosFactor,
    "NBF": NbfFactor,
    "PCR": PcrFactor,
    "NEWF": NewfFactor,
}


def get_factor_instance(factor_name: str) -> BaseFactor | None:
    """根据因子名称获取实例"""
    cls = FACTOR_CLASSES.get(factor_name)
    if cls:
        return cls()
    return None


def get_all_factors() -> list[BaseFactor]:
    """获取全部 11 个因子实例"""
    return [cls() for cls in FACTOR_CLASSES.values()]


__all__ = [
    "BaseFactor",
    "FactorRawValue",
    "FactorQuantileResult",
    "FactorSigmoidResult",
    "DivergenceInfo",
    "CompositeScore",
    "FACTOR_NAMES",
    "FACTOR_CLASSES",
    "get_factor_instance",
    "get_all_factors",
    "VolFactor",
    "AdrFactor",
    "ErpFactor",
    "FlowFactor",
    "EtfFactor",
    "NhnlFactor",
    "TurnFactor",
    "PosFactor",
    "NbfFactor",
    "PcrFactor",
    "NewfFactor",
]
