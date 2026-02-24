"""키워드 자동 매핑 실행 스크립트

52개 태그 기반으로 branch_keywords를 keyword_mappings에 재분류합니다.
MappingRepository.get_unmapped_keywords()를 사용하여 미매핑 키워드를 조회합니다.
"""

from __future__ import annotations

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
MAX_BATCHES = 50  # 최대 25,000건 (unique ~9,910)


async def main():
    from core.config import get_settings
    from domain.analysis import HybridClassifier
    from domain.analysis.patterns import CATEGORY_DEFAULT_TAG
    from repository.database import get_session_factory, init_db
    from repository.tag_repository import MappingRepository, TagRepository

    settings = get_settings()
    init_db(settings.get_database_url())
    factory = get_session_factory()

    session = factory()
    try:
        tag_repo = TagRepository(session)
        mapping_repo = MappingRepository(session)

        # 1. DB 태그 → 이름:id 룩업
        all_tags = await tag_repo.get_all_with_filters(is_active=True)
        tag_name_to_id: dict[str, int] = {t.name: t.id for t in all_tags}
        logger.info("Tags loaded: %d", len(tag_name_to_id))

        # 2. HybridClassifier 초기화 (한 번만)
        logger.info("Initializing HybridClassifier...")
        classifier = await asyncio.to_thread(lambda: HybridClassifier(lazy_load=False))
        logger.info("Classifier ready.")

        total_mapped = 0
        total_skipped = 0
        total_errors = 0
        start = time.time()

        for batch_num in range(1, MAX_BATCHES + 1):
            # 3. 미매핑 키워드 조회
            unmapped = await mapping_repo.get_unmapped_keywords(limit=BATCH_SIZE)
            if not unmapped:
                logger.info("No more unmapped keywords.")
                break

            keywords = [row["keyword"] for row in unmapped]

            # 4. 배치 분류 (CPU-bound)
            classifications = await asyncio.to_thread(
                classifier.classify_keywords, keywords
            )

            # 5. 매핑 생성
            mapped = 0
            skipped = 0
            errors = 0
            for row, (tag_group, _score, _sentiment) in zip(
                unmapped, classifications, strict=False
            ):
                kw = row["keyword"]
                try:
                    if tag_group == "기타":
                        skipped += 1
                        continue

                    tag_id = tag_name_to_id.get(tag_group)
                    if not tag_id:
                        default_tag = CATEGORY_DEFAULT_TAG.get(tag_group)
                        if default_tag:
                            tag_id = tag_name_to_id.get(default_tag)

                    if tag_id:
                        await mapping_repo.upsert_mapping(kw, tag_id, is_auto=True)
                        mapped += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors += 1
                    logger.warning("Error mapping '%s': %s", kw, e)

            await session.commit()

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

        elapsed = time.time() - start
        logger.info(
            "=== COMPLETE === mapped=%d, skipped=%d, errors=%d in %.1fs",
            total_mapped, total_skipped, total_errors, elapsed,
        )
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
