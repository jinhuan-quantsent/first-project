"""
Health Service - V5.0 健康检查
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class HealthService:
    """
    V5.0 健康检查 Service
    """

    def check(self) -> dict:
        """
        健康检查：返回 V5.0 服务状态
        """
        return {
            "code": 0,
            "data": {
                "status": "healthy",
                "service": "fund-sentiment-v5",
                "version": "5.0",
                "checked_at": datetime.now().isoformat(),
            },
            "message": "ok",
        }
