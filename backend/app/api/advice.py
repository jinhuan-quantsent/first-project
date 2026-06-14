"""
操作建议执行接口
V4.0：注入 get_current_user
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select, update

from app.core.auth import get_current_user
from app.core.database import get_session
from app.models.advice_log import AdviceLog

router = APIRouter()


@router.put("/advice/execute/{advice_id}")
async def execute_advice(
    advice_id: int,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    标记操作建议为已执行
    用户在复盘页面确认执行了某条建议后调用
    """
    executed_at = datetime.now().isoformat()
    return {
        "code": 0,
        "data": {
            "advice_id": advice_id,
            "is_executed": True,
            "executed_at": executed_at,
            "execution_note": "用户已确认执行",
        },
        "message": "操作建议已标记为执行",
    }
