"""
情绪引擎模块 — V5.0
导出新引擎（factor_engine/ + quantile + sigmoid + aggregator_v5 + signal + confidence + position）
"""
from app.engine.quantile import QuantileNorm
from app.engine.sigmoid import SigmoidMapper
from app.engine.aggregator_v5 import AggregatorV5
from app.engine.signal_mapper import SignalMapper
from app.engine.confidence import ConfidenceEngine
from app.engine.position_v5 import PositionEngineV5
from app.engine.backtest import BacktestEngine, BacktestConfig, BacktestResult

# factor_engine 子包（11因子）
from app.engine.factor_engine import (
    BaseFactor,
    FactorRawValue,
    FactorSigmoidResult,
    CompositeScore,
    FACTOR_NAMES,
    FACTOR_CLASSES,
    get_factor_instance,
    get_all_factors,
    VolFactor,
    AdrFactor,
    ErpFactor,
    FlowFactor,
    EtfFactor,
    NhnlFactor,
    TurnFactor,
    PosFactor,
    NbfFactor,
    PcrFactor,
    NewfFactor,
)

__all__ = [
    # 三层管道
    "QuantileNorm",
    "SigmoidMapper",
    "AggregatorV5",
    # V5 引擎组件
    "SignalMapper",
    "ConfidenceEngine",
    "PositionEngineV5",
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    # 因子引擎基类 + 数据结构
    "BaseFactor",
    "FactorRawValue",
    "FactorSigmoidResult",
    "CompositeScore",
    # 因子注册
    "FACTOR_NAMES",
    "FACTOR_CLASSES",
    "get_factor_instance",
    "get_all_factors",
    # 11 因子类
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
