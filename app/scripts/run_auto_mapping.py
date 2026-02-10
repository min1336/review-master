"""키워드 자동 매핑 실행 스크립트

52개 태그 기반으로 branch_keywords를 keyword_mappings에 재분류합니다.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# app/ 디렉토리를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 500
MAX_BATCHES = 300  # 최대 150,000건


async def main():
    from repository.branch_tag_repository import BranchTagRepository
    from repository.session import get_client
    from repository.tag_repository import (
        CategoryRepository,
        MappingRepository,
        TagRepository,
    )
    from services.tag_service import TagService

    client = await get_client()

    tag_repo = TagRepository(client)
    branch_tag_repo = BranchTagRepository(client)
    category_repo = CategoryRepository(client)
    mapping_repo = MappingRepository(client)

    service = TagService(tag_repo, branch_tag_repo, category_repo, mapping_repo)

    total_mapped = 0
    total_skipped = 0
    total_errors = 0
    start = time.time()

    for batch_num in range(1, MAX_BATCHES + 1):
        result = await service.auto_map_keywords(limit=BATCH_SIZE)

        mapped = result["mapped"]
        skipped = result["skipped"]
        errors = len(result.get("errors", []))

        total_mapped += mapped
        total_skipped += skipped
        total_errors += errors

        elapsed = time.time() - start
        logger.info(
            "Batch %d: mapped=%d, skipped=%d, errors=%d | "
            "Total: mapped=%d, skipped=%d, errors=%d (%.1fs)",
            batch_num, mapped, skipped, errors,
            total_mapped, total_skipped, total_errors, elapsed,
        )

        # 더 이상 매핑할 키워드가 없으면 종료
        if mapped == 0 and skipped == 0:
            logger.info("No more unmapped keywords. Done.")
            break

    elapsed = time.time() - start
    logger.info(
        "=== COMPLETE === mapped=%d, skipped=%d, errors=%d in %.1fs",
        total_mapped, total_skipped, total_errors, elapsed,
    )


if __name__ == "__main__":
    asyncio.run(main())
