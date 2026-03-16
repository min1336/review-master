"""
일별 branch_tags weighted_score 감쇠 적용

배치 파이프라인 이후 또는 스케줄러에서 호출합니다.
모든 branch_tags의 weighted_score에 DAILY_DECAY를 곱하여
오래된 태그 점수를 자연 감쇠시킵니다.
"""

from __future__ import annotations

import logging
from math import exp
from typing import TYPE_CHECKING

from sqlalchemy import text

from core.utils import DECAY_LAMBDA

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DAILY_DECAY: float = exp(-DECAY_LAMBDA)  # ~ 0.99005 (일 약 1% 감쇠)
MIN_WEIGHTED_SCORE: float = 0.01          # 완전 소멸 방지 최솟값


class DecayJob:
    """branch_tags.weighted_score 일별 감쇠 적용"""

    async def run(self, session: AsyncSession) -> int:
        """
        모든 branch_tags (period_type='all')의 weighted_score에
        일별 감쇠를 적용합니다.

        Returns:
            처리된 행 수
        """
        try:
            result = await session.execute(
                text("SELECT apply_tag_decay(:decay_factor, :min_score)"),
                {"decay_factor": DAILY_DECAY, "min_score": MIN_WEIGHTED_SCORE},
            )
            row = result.scalar()
            count = row if isinstance(row, int) else 0
            logger.info("DecayJob 완료: %d행 처리 (decay=%.5f)", count, DAILY_DECAY)
            return count
        except Exception as e:
            logger.warning("DecayJob 실패 (무시하고 계속): %s", e)
            return 0
