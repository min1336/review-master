"""요약 비즈니스 로직

조회/생성/승인 로직을 Mixin으로 분리하여 관심사를 분리한다.
- SummaryQueryMixin: 조회/수정 (10개 메서드)
- SummaryGenerationMixin: AI 요약 생성 (8개 메서드)
- SummaryApprovalMixin: 승인/거절 (6개 메서드)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from services.summary_approval_mixin import SummaryApprovalMixin
from services.summary_generation_mixin import SummaryGenerationMixin
from services.summary_query_mixin import SummaryQueryMixin

if TYPE_CHECKING:
    from infrastructure.athena_client import AthenaClient
    from repository.branch_tag_repository import BranchTagRepository
    from repository.review_repository import BranchReviewRepository
    from repository.review_repository import SentimentRepository
    from repository.summary_repository import SummaryRepository

logger = logging.getLogger(__name__)


class SummaryService(SummaryQueryMixin, SummaryGenerationMixin, SummaryApprovalMixin):
    """요약 비즈니스 로직 (Mixin 조합)"""

    def __init__(
        self,
        summary_repo: SummaryRepository,
        branch_tag_repo: BranchTagRepository,
        review_repo: BranchReviewRepository,
        sentiment_repo: SentimentRepository | None = None,
        athena_client: AthenaClient | None = None,
    ):
        self.summary_repo = summary_repo
        self.branch_tag_repo = branch_tag_repo
        self.review_repo = review_repo
        self.sentiment_repo = sentiment_repo
        self.athena_client = athena_client
