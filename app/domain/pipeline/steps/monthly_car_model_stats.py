"""Step 9: monthly_car_model_tag_stats 저장 (차량x월x태그별 감정 통계)"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from repository.orm_models import (
    CarModelsMasterORM,
    CategoryORM,
    MonthlyCarModelTagStatsORM,
    TagORM,
)
from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MonthlyCarModelStatsUpdater:
    """monthly_car_model_tag_stats 테이블 적재"""

    async def update(
        self,
        session: AsyncSession,
        processed: list[ProcessedReviewDTO],
        store_subtags: bool = True,
    ) -> int:
        """(car_model, period, tag_name) 메모리 집계 -> car_model_id/tag_id 변환 -> upsert

        Args:
            store_subtags: True면 키워드를 서브태그로 역매핑하여 서브태그 수준 통계도 추가 저장
        """
        kw_to_subtag = self._build_kw_to_subtag() if store_subtags else {}

        # 1. 메모리 집계
        groups: dict[tuple[str, str, str], dict[str, int]] = {}

        for pr in processed:
            car_model = pr.review.car_model.strip()
            if not car_model:
                continue
            period = self._get_period(pr)
            if not period:
                continue

            for tag_name, sentiments in pr.tag_sentiments.items():
                if tag_name == "기타":
                    continue

                # 카테고리 수준 (기존 동작 유지)
                key = (car_model, period, tag_name)
                if key not in groups:
                    groups[key] = {"positive": 0, "negative": 0, "neutral": 0}
                g = groups[key]
                g["positive"] += len(sentiments.get("positive", []))
                g["negative"] += len(sentiments.get("negative", []))
                g["neutral"] += len(sentiments.get("neutral", []))

                # 서브태그 수준 (키워드 → 서브태그 역매핑)
                if store_subtags:
                    for sent_type in ("positive", "negative", "neutral"):
                        for kw in sentiments.get(sent_type, []):
                            subtag = self._resolve_subtag(kw, kw_to_subtag)
                            if subtag and subtag != tag_name:
                                st_key = (car_model, period, subtag)
                                if st_key not in groups:
                                    groups[st_key] = {
                                        "positive": 0, "negative": 0, "neutral": 0,
                                    }
                                groups[st_key][sent_type] += 1

        if not groups:
            return 0

        # 2. car_models_master에서 car_model_id 일괄 조회
        all_model_names = list({k[0] for k in groups})
        model_id_cache: dict[str, int] = {}
        try:
            result = await session.execute(
                select(CarModelsMasterORM.id, CarModelsMasterORM.model_name)
                .where(CarModelsMasterORM.model_name.in_(all_model_names))
            )
            for row in result.all():
                model_id_cache[row.model_name] = row.id
        except Exception as e:
            logger.warning(f"car_models_master 조회 실패: {e}")
            return 0

        # 3. tags에서 tag_id 일괄 조회
        all_tag_names = list({k[2] for k in groups})
        tag_id_cache: dict[str, int] = {}
        try:
            result = await session.execute(
                select(TagORM.id, TagORM.name)
                .where(TagORM.name.in_(all_tag_names))
            )
            for row in result.all():
                tag_id_cache[row.name] = row.id
        except Exception as e:
            logger.warning(f"tags 조회 실패: {e}")
            return 0

        # 3b. tags 테이블에 없는 서브태그 자동 생성
        if store_subtags:
            missing = set(all_tag_names) - set(tag_id_cache.keys())
            if missing:
                await self._ensure_subtag_entries(session, missing, tag_id_cache)

        # 4. 기존 데이터 SELECT -> 증분 합산 -> UPSERT
        saved = 0
        for (car_model, period, tag_name), counts in groups.items():
            car_model_id = model_id_cache.get(car_model)
            tag_id = tag_id_cache.get(tag_name)
            if not car_model_id or not tag_id:
                continue

            try:
                result = await session.execute(
                    select(MonthlyCarModelTagStatsORM)
                    .where(MonthlyCarModelTagStatsORM.car_model_id == car_model_id)
                    .where(MonthlyCarModelTagStatsORM.period == period)
                    .where(MonthlyCarModelTagStatsORM.tag_id == tag_id)
                )
                existing_row = result.scalar_one_or_none()
                old: dict = {}
                if existing_row:
                    old = {
                        c.key: getattr(existing_row, c.key)
                        for c in MonthlyCarModelTagStatsORM.__table__.columns
                    }

                new_pos = (old.get("positive_count", 0) or 0) + counts["positive"]
                new_neg = (old.get("negative_count", 0) or 0) + counts["negative"]
                new_neu = (old.get("neutral_count", 0) or 0) + counts["neutral"]

                values = {
                    "car_model_id": car_model_id,
                    "period": period,
                    "tag_id": tag_id,
                    "positive_count": new_pos,
                    "negative_count": new_neg,
                    "neutral_count": new_neu,
                }
                stmt = (
                    pg_insert(MonthlyCarModelTagStatsORM.__table__)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=["car_model_id", "period", "tag_id"],
                        set_={
                            "positive_count": values["positive_count"],
                            "negative_count": values["negative_count"],
                            "neutral_count": values["neutral_count"],
                        },
                    )
                )
                await session.execute(stmt)
                saved += 1
            except Exception as e:
                logger.warning(
                    f"monthly_car_model_tag_stats upsert 실패 "
                    f"(model={car_model}, period={period}, tag={tag_name}): {e}"
                )

        logger.info(f"monthly_car_model_tag_stats 저장 완료: {saved}건")
        return saved

    @staticmethod
    def _get_period(pr: ProcessedReviewDTO) -> str | None:
        """리뷰의 created_at에서 YYYY-MM 형식 period 추출"""
        if pr.review.created_at:
            return pr.review.created_at.strftime("%Y-%m")
        return None

    @staticmethod
    def _build_kw_to_subtag() -> dict[str, str]:
        """키워드 → 서브태그명 역매핑 빌드 (exact + stem)"""
        from domain.analysis.patterns import RULE_BASED_TAG_MAPPING, extract_stem

        mapping: dict[str, str] = {}
        for subtag_name, keywords in RULE_BASED_TAG_MAPPING.items():
            for kw in keywords:
                mapping[kw] = subtag_name
                stem = extract_stem(kw)
                if stem and stem not in mapping:
                    mapping[stem] = subtag_name
        return mapping

    @staticmethod
    def _resolve_subtag(kw: str, mapping: dict[str, str]) -> str | None:
        """키워드를 서브태그명으로 해석 (exact → stem → contains)"""
        from domain.analysis.patterns import extract_stem

        kw_lower = kw.lower().strip()
        if kw_lower in mapping:
            return mapping[kw_lower]
        stem = extract_stem(kw_lower)
        if stem and stem in mapping:
            return mapping[stem]
        for rule_kw, subtag in mapping.items():
            if rule_kw in kw_lower:
                return subtag
        return None

    @staticmethod
    async def _ensure_subtag_entries(
        session: "AsyncSession",
        missing_names: set[str],
        tag_id_cache: dict[str, int],
    ) -> None:
        """tags 테이블에 없는 서브태그 엔트리를 생성 (category_id 포함)"""
        from domain.analysis.patterns import TAG_REGISTRY

        subtag_to_cat: dict[str, str] = {}
        for cat_name, cat_meta in TAG_REGISTRY.items():
            for sub_name in cat_meta.tags:
                subtag_to_cat[sub_name] = cat_name

        needed_cats = {subtag_to_cat[n] for n in missing_names if n in subtag_to_cat}
        cat_name_to_id: dict[str, int] = {}
        if needed_cats:
            try:
                result = await session.execute(
                    select(CategoryORM.id, CategoryORM.name)
                    .where(CategoryORM.name.in_(list(needed_cats)))
                )
                for row in result.all():
                    cat_name_to_id[row.name] = row.id
            except Exception as e:
                logger.warning(f"categories 조회 실패: {e}")

        for name in missing_names:
            cat_name = subtag_to_cat.get(name)
            cat_id = cat_name_to_id.get(cat_name) if cat_name else None
            try:
                insert_vals: dict = {"name": name, "is_active": True}
                update_set: dict = {"is_active": True}
                if cat_id is not None:
                    insert_vals["category_id"] = cat_id
                    update_set["category_id"] = cat_id

                stmt = (
                    pg_insert(TagORM.__table__)
                    .values(**insert_vals)
                    .on_conflict_do_update(
                        index_elements=["name"],
                        set_=update_set,
                    )
                    .returning(TagORM.__table__.c.id)
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is not None:
                    tag_id_cache[name] = row
            except Exception as e:
                logger.warning(f"서브태그 생성 실패 (name={name}): {e}")
