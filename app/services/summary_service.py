from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from schemas.dto import (
    BranchCarModelsDTO,
    BranchDetailDTO,
    BranchReviewsDTO,
    CarModelDTO,
    CarModelTagDTO,
    PendingSummaryResultDTO,
    RatingDistributionDTO,
    RatingStatsDTO,
    RegionStatsDTO,
    ReviewOutputDTO,
    SummariesOutputDTO,
    SummaryStatsDTO,
    SummaryWithTagsDTO,
    TagSentimentCountDTO,
)

logger = logging.getLogger(__name__)


class SummaryService:
    """요약 비즈니스 로직"""

    # 기간별 설정 (우선순위 순서)
    PERIOD_CONFIGS = [
        {"key": "3m", "field": "summary_3m", "months": 3, "label": "최근 3개월"},
        {"key": "6m", "field": "summary_6m", "months": 6, "label": "최근 6개월"},
        {"key": "1y", "field": "summary_1y", "months": 12, "label": "최근 1년"},
    ]
    MIN_REVIEWS_FOR_SUMMARY = 30

    def __init__(self, summary_repo, branch_tag_repo, review_repo, sentiment_repo=None):
        self.summary_repo = summary_repo
        self.branch_tag_repo = branch_tag_repo
        self.review_repo = review_repo
        self.sentiment_repo = sentiment_repo

    async def get_summaries(
        self,
        status: str | None = None,
        region: str | None = None,
        keyword: str | None = None,
        min_rating: float | None = None,
        max_rating: float | None = None,
        min_reviews: int = 30,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "branch_id",
        order: str = "asc",
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
    ) -> list[dict]:
        """
        요약 목록 조회 (날짜 범위 필터링 지원)
        """
        import logging

        # 날짜 필터가 있으면 해당 기간에 리뷰가 있는 지점만 조회
        branch_ids_filter = None
        if review_date_from or review_date_to:
            branch_ids_filter = await self.summary_repo.get_branch_ids_by_date_range(
                review_date_from=review_date_from, review_date_to=review_date_to
            )

            if not branch_ids_filter:
                logging.info(
                    f"날짜 필터 결과 없음: {review_date_from} ~ {review_date_to}"
                )
                return []

        if keyword or min_rating or max_rating:
            summaries = await self.summary_repo.search(
                keyword=keyword,
                region=region,
                min_rating=min_rating,
                max_rating=max_rating,
                min_reviews=min_reviews,
                limit=limit,
            )
            if branch_ids_filter is not None:
                summaries = [s for s in summaries if s.branch_id in branch_ids_filter]
        else:
            summaries = await self.summary_repo.get_all_with_filters(
                status=status,
                region=region,
                min_reviews=min_reviews,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                order=order,
            )
            if branch_ids_filter is not None:
                summaries = [s for s in summaries if s.branch_id in branch_ids_filter]

        return [s.model_dump() if hasattr(s, "model_dump") else s for s in summaries]

    async def get_summary(self, branch_id: int) -> dict | None:
        """단일 요약 조회"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        return summary.model_dump() if summary else None

    async def get_summary_with_tags(self, branch_id: int) -> SummaryWithTagsDTO:
        """요약과 태그 함께 조회"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        tags = await self.branch_tag_repo.get_by_branch(branch_id)

        return SummaryWithTagsDTO(
            summary=summary.model_dump() if summary else None,
            tags=[t.model_dump() for t in tags],
        )

    async def update_summary(self, branch_id: int, data: dict) -> dict | None:
        """요약 수정"""
        data["branch_id"] = branch_id
        result = await self.summary_repo.upsert_by_branch_id(data)
        return result.model_dump() if result else None

    async def update_status(self, branch_id: int, status: str) -> dict | None:
        """상태 변경"""
        result = await self.summary_repo.update_status(branch_id, status)
        return result.model_dump() if result else None

    async def get_stats(self) -> SummaryStatsDTO:
        """통계 조회"""
        return await self.summary_repo.get_stats()

    async def get_region_stats(self) -> list[RegionStatsDTO]:
        """지역별 통계"""
        data = await self.summary_repo.get_region_data()

        if not data:
            return []

        region_stats = {}
        for row in data:
            region = row.get("region") or "미분류"
            city = region.split()[0] if region and region.strip() else "미분류"

            if city not in region_stats:
                region_stats[city] = {
                    "region": city,
                    "count": 0,
                    "total_reviews": 0,
                    "rating_sum": 0,
                    "rating_count": 0,
                }

            region_stats[city]["count"] += 1
            region_stats[city]["total_reviews"] += row.get("review_count") or 0

            if row.get("avg_rating"):
                region_stats[city]["rating_sum"] += float(row["avg_rating"])
                region_stats[city]["rating_count"] += 1

        stats_list = []
        for city, stats in region_stats.items():
            avg_rating = 0
            if stats["rating_count"] > 0:
                avg_rating = round(stats["rating_sum"] / stats["rating_count"], 2)

            stats_list.append(
                RegionStatsDTO(
                    region=city,
                    count=stats["count"],
                    avg_rating=avg_rating,
                    total_reviews=stats["total_reviews"],
                )
            )

        stats_list.sort(key=lambda x: x.count, reverse=True)
        return stats_list

    async def get_rating_stats(self) -> RatingStatsDTO:
        """평점 분포 통계"""
        ratings = await self.summary_repo.get_all_ratings()

        if not ratings:
            return RatingStatsDTO(
                min=0,
                max=0,
                avg=0,
                total=0,
                distribution=RatingDistributionDTO(),
            )

        distribution = RatingDistributionDTO()

        for r in ratings:
            if r >= 4.5:
                distribution.range_4_5_to_5_0 += 1
            elif r >= 4.0:
                distribution.range_4_0_to_4_5 += 1
            elif r >= 3.5:
                distribution.range_3_5_to_4_0 += 1
            elif r >= 3.0:
                distribution.range_3_0_to_3_5 += 1
            else:
                distribution.range_below_3_0 += 1

        return RatingStatsDTO(
            min=min(ratings),
            max=max(ratings),
            avg=round(sum(ratings) / len(ratings), 2),
            total=len(ratings),
            distribution=distribution,
        )

    async def regenerate_summary(self, branch_id: int, period: str = "all") -> str:
        """
        AI 요약 재생성 (generate_summary_with_data 사용)

        Args:
            branch_id: 지점 ID
            period: 기간 (all, 1y, 6m, 3m, 1m) - 힌트용, 실제는 자동 결정

        Returns:
            str: 생성된 요약 텍스트
        """
        result = await self.generate_summary_with_data(branch_id)
        return result.get("summary", "")

    async def generate_summary_with_data(
        self,
        branch_id: int,
        save_to_db: bool = True,
    ) -> dict:
        """
        태그+감정+리뷰 데이터를 활용한 AI 요약 생성

        기간 로직:
        - 3개월 리뷰 >= 30개 → 3개월 요약
        - 3개월 리뷰 < 30개 → 6개월로 확장
        - 6개월 리뷰 < 30개 → 1년으로 확장
        - 1년 리뷰 < 30개 → 실패 (리뷰 부족 메시지)

        Args:
            branch_id: 지점 ID
            save_to_db: DB에 저장할지 여부 (기본 True)

        Returns:
            dict: {
                "success": bool,
                "summary": str,
                "period": str (3m/6m/1y),
                "period_label": str,
                "start_date": str,
                "end_date": str,
                "review_count": int,
                "error": str (실패 시)
            }
        """
        from infrastructure.llm import get_provider
        from infrastructure.llm.prompts import RichSummaryPromptBuilder
        from repository.session import get_client

        # 1. 지점 기본 정보 조회
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            return {
                "success": False,
                "summary": "",
                "error": f"지점 {branch_id}을(를) 찾을 수 없습니다",
            }

        summary_data = summary.model_dump()
        branch_name = summary_data.get("branch_name", f"지점 {branch_id}")

        # 2. 기간별 리뷰 수 확인 및 적절한 기간 선택
        client = await get_client()
        end_date = datetime.now()
        selected_period = None
        review_count = 0
        start_date = None

        for period_config in self.PERIOD_CONFIGS:
            months = period_config["months"]
            start_date = end_date - timedelta(days=months * 30)

            # 해당 기간의 리뷰 수 조회
            count_result = await (
                client.table("branch_reviews")
                .select("id", count="exact")
                .eq("branch_id", branch_id)
                .gte("review_date", start_date.isoformat())
                .execute()
            )
            review_count = count_result.count or 0

            if review_count >= self.MIN_REVIEWS_FOR_SUMMARY:
                selected_period = period_config
                break

        # 3. 리뷰가 충분하지 않은 경우
        if not selected_period:
            insufficient_msg = RichSummaryPromptBuilder.get_insufficient_reviews_message(
                branch_name, review_count
            )
            return {
                "success": False,
                "summary": insufficient_msg,
                "period": None,
                "period_label": None,
                "review_count": review_count,
                "error": "리뷰가 충분하지 않습니다",
            }

        period_key = selected_period["key"]
        period_field = selected_period["field"]
        period_label = selected_period["label"]

        # 4. 태그별 감정 데이터 조회 (branch_tags)
        tag_sentiments = []
        try:
            tags_result = await (
                client.table("branch_tags")
                .select("tag_id, count, weighted_score, tags(id, name)")
                .eq("branch_id", branch_id)
                .order("count", desc=True)
                .limit(10)
                .execute()
            )

            # 태그별 감정 개수 조회를 위해 branch_reviews에서 집계
            # 실제 감정은 태그 매핑 테이블에서 가져와야 하지만,
            # 현재 구조에서는 branch_tags에 count만 있으므로
            # recent_reviews의 sentiment와 연계하여 계산
            for tag_row in tags_result.data:
                tag_info = tag_row.get("tags") or {}
                tag_name = tag_info.get("name", "")
                if tag_name:
                    tag_sentiments.append({
                        "name": tag_name,
                        "positive": tag_row.get("count", 0),  # 임시로 count 사용
                        "negative": 0,
                        "neutral": 0,
                        "total": tag_row.get("count", 0),
                    })
        except Exception as e:
            logger.warning(f"태그 조회 실패 (branch_id={branch_id}): {e}")

        # 5. 감정 통계 조회 (branch_sentiment_stats)
        sentiment_stats = {"positive": 0, "negative": 0, "neutral": 0, "total": 0}
        if self.sentiment_repo:
            try:
                stats = await self.sentiment_repo.get_stats(branch_id)
                sentiment_stats = {
                    "positive": stats.positive,
                    "negative": stats.negative,
                    "neutral": stats.neutral,
                    "total": stats.total,
                }
            except Exception as e:
                logger.warning(f"감정 통계 조회 실패 (branch_id={branch_id}): {e}")

        # 6. 최근 리뷰 30개 조회 (recent_reviews)
        sample_reviews = []
        try:
            reviews_result = await (
                client.table("recent_reviews")
                .select("content")
                .eq("branch_id", branch_id)
                .order("created_at", desc=True)
                .limit(30)
                .execute()
            )
            sample_reviews = [
                r.get("content", "")[:200]
                for r in reviews_result.data
                if r.get("content")
            ]
        except Exception as e:
            logger.warning(f"최근 리뷰 조회 실패 (branch_id={branch_id}): {e}")

        # 7. 프롬프트 생성
        start_date_str = start_date.strftime("%Y년 %m월 %d일")
        end_date_str = end_date.strftime("%Y년 %m월 %d일")

        system_prompt, user_prompt = RichSummaryPromptBuilder.create_prompt(
            branch_name=branch_name,
            start_date=start_date_str,
            end_date=end_date_str,
            total_reviews=review_count,
            tag_sentiments=tag_sentiments,
            sentiment_stats=sentiment_stats,
            sample_reviews=sample_reviews[:5],
        )

        # 8. LLM 호출
        try:
            llm_provider = get_provider()
            response = await asyncio.to_thread(
                llm_provider.generate,
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=400,
                temperature=0.7,
            )
            generated_summary = (
                response.content if hasattr(response, "content") else str(response)
            )
        except Exception as e:
            logger.error(f"LLM 호출 실패 (branch_id={branch_id}): {e}")
            return {
                "success": False,
                "summary": "",
                "period": period_key,
                "error": f"AI 요약 생성 실패: {e}",
            }

        # 9. DB 저장 (자동 게시)
        if save_to_db:
            try:
                await self.summary_repo.upsert_by_branch_id({
                    "branch_id": branch_id,
                    period_field: generated_summary,
                })
                logger.info(
                    f"요약 저장 완료: branch_id={branch_id}, period={period_key}"
                )
            except Exception as e:
                logger.error(f"요약 저장 실패 (branch_id={branch_id}): {e}")

        return {
            "success": True,
            "summary": generated_summary,
            "period": period_key,
            "period_label": period_label,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "review_count": review_count,
        }

    async def generate_pending_summary(
        self,
        branch_id: int,
        period: str = "1m",
    ) -> dict:
        """
        AI 요약을 생성하여 pending_summaries에 저장 (승인 대기 상태)

        스케줄러에서 자동으로 호출되며, 운영자 승인 후 실제 요약으로 적용됩니다.

        Args:
            branch_id: 지점 ID
            period: 기간 키 (1m, 3m, 6m, 1y, all)

        Returns:
            dict: {
                "success": bool,
                "summary": str,
                "period": str,
                "error": str (실패 시)
            }
        """
        # 기존 generate_summary_with_data 로직 재사용 (save_to_db=False)
        result = await self.generate_summary_with_data(branch_id, save_to_db=False)

        if not result.get("success"):
            return result

        generated_summary = result.get("summary", "")
        generated_period = result.get("period", period)

        # pending_summaries에 저장
        try:
            # 현재 pending_summaries 조회
            summary = await self.summary_repo.get_by_branch_id(branch_id)
            if not summary:
                return {
                    "success": False,
                    "summary": "",
                    "period": generated_period,
                    "error": f"지점 {branch_id}을(를) 찾을 수 없습니다",
                }

            current_pending = summary.pending_summaries or {}

            # 새 pending 요약 추가
            current_pending[generated_period] = generated_summary

            # DB 업데이트
            await self.summary_repo.set_pending_summary(branch_id, current_pending)

            logger.info(
                f"Pending 요약 생성 완료: branch_id={branch_id}, period={generated_period}"
            )

            return {
                "success": True,
                "summary": generated_summary,
                "period": generated_period,
                "period_label": result.get("period_label"),
                "review_count": result.get("review_count"),
            }
        except Exception as e:
            logger.error(f"Pending 요약 저장 실패 (branch_id={branch_id}): {e}")
            return {
                "success": False,
                "summary": generated_summary,
                "period": generated_period,
                "error": f"Pending 저장 실패: {e}",
            }

    async def apply_pending_summary(
        self, branch_id: int, period: str
    ) -> PendingSummaryResultDTO:
        """대기 중인 요약을 적용 (pending → main)"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        pending = summary_data.get("pending_summaries") or {}

        if period not in pending:
            raise ValueError(f"대기 중인 {period} 요약이 없습니다")

        field_map = {
            "all": "summary_all",
            "1y": "summary_1y",
            "6m": "summary_6m",
            "3m": "summary_3m",
            "1m": "summary_1m",
        }

        new_summary = pending.pop(period)

        await self.summary_repo.upsert_by_branch_id(
            {
                "branch_id": branch_id,
                field_map[period]: new_summary,
                "pending_summaries": pending,
            }
        )

        return PendingSummaryResultDTO(period=period, applied=new_summary)

    async def discard_pending_summary(
        self, branch_id: int, period: str
    ) -> PendingSummaryResultDTO:
        """대기 중인 요약 취소 (삭제)"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        pending = summary_data.get("pending_summaries") or {}

        if period in pending:
            del pending[period]
            await self.summary_repo.upsert_by_branch_id(
                {"branch_id": branch_id, "pending_summaries": pending}
            )

        return PendingSummaryResultDTO(period=period, discarded=period)

    async def get_branch_detail(
        self, branch_id: int, include_summaries: bool = True, max_reviews: int = 500
    ) -> BranchDetailDTO | None:
        """지점 상세 분석 (JSON 반환)"""
        from domain.analysis import KeywordExtractor, RuleBasedABSA

        # 1. 기본 정보 조회
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            return None

        summary_data = summary.model_dump()
        branch_name = summary_data.get("branch_name", f"지점 {branch_id}")
        location = summary_data.get("region", "")

        reviews_result = await self.review_repo.get_by_branch(
            branch_id=branch_id, limit=max_reviews
        )
        reviews_data = reviews_result.reviews
        review_count = reviews_result.total

        if not reviews_data:
            return BranchDetailDTO(
                branch_id=branch_id,
                branch_name=branch_name,
                location=location,
                review_count=0,
                tags=[],
                summaries=SummariesOutputDTO(),
                reviews=[],
            )

        review_texts = [r.get("content", "") or "" for r in reviews_data]

        def extract_keywords():
            extractor = KeywordExtractor()
            return extractor.extract_batch(review_texts)

        all_keywords = await asyncio.to_thread(extract_keywords)

        def classify_reviews():
            classifier = RuleBasedABSA()
            results = []
            tag_totals = {}

            for keywords, review_text in zip(all_keywords, review_texts, strict=False):
                result = classifier.classify_review(review_text, keywords[:10])

                tag_parts = []
                for tag, sentiments in result.items():
                    pos = len(sentiments.get("positive", []))
                    neg = len(sentiments.get("negative", []))
                    neu = len(sentiments.get("neutral", []))

                    if tag not in tag_totals:
                        tag_totals[tag] = {
                            "positive": 0,
                            "negative": 0,
                            "neutral": 0,
                            "total": 0,
                        }
                    tag_totals[tag]["positive"] += pos
                    tag_totals[tag]["negative"] += neg
                    tag_totals[tag]["neutral"] += neu
                    tag_totals[tag]["total"] += pos + neg + neu

                    if pos > neg:
                        tag_parts.append(f"{tag}(+)")
                    elif neg > pos:
                        tag_parts.append(f"{tag}(-)")

                results.append(", ".join(tag_parts))

            return results, tag_totals

        tag_sentiments, tag_totals = await asyncio.to_thread(classify_reviews)

        sorted_tags = sorted(
            tag_totals.items(), key=lambda x: x[1]["total"], reverse=True
        )
        tags_list = [
            TagSentimentCountDTO(
                name=tag,
                total=counts["total"],
                positive=counts["positive"],
                negative=counts["negative"],
                neutral=counts["neutral"],
            )
            for tag, counts in sorted_tags
        ]

        reviews_output = []
        for i, review in enumerate(reviews_data):
            reviews_output.append(
                ReviewOutputDTO(
                    id=review.get("review_id"),
                    date=review.get("review_date"),
                    content=review.get("content", "")[:500],
                    keywords=all_keywords[i][:10] if i < len(all_keywords) else [],
                    tag_sentiments=tag_sentiments[i]
                    if i < len(tag_sentiments)
                    else "",
                )
            )

        summaries_output = SummariesOutputDTO()
        if include_summaries:
            summaries_output = SummariesOutputDTO(
                summary_1m=summary_data.get("summary_1m", "") or "",
                summary_3m=summary_data.get("summary_3m", "") or "",
                summary_6m=summary_data.get("summary_6m", "") or "",
                summary_1y=summary_data.get("summary_1y", "") or "",
                summary_all=summary_data.get("summary_all", "") or "",
            )

        return BranchDetailDTO(
            branch_id=branch_id,
            branch_name=branch_name,
            location=location,
            review_count=review_count,
            tags=tags_list,
            summaries=summaries_output,
            reviews=reviews_output,
        )

    async def get_branch_reviews(
        self,
        branch_id: int,
        car_model: str | None = None,
        sentiment: str | None = None,
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> BranchReviewsDTO:
        """지점별 원본 리뷰 목록 조회 (필터링 지원)"""
        return await self.review_repo.get_by_branch(
            branch_id=branch_id,
            car_model=car_model,
            sentiment=sentiment,
            review_date_from=review_date_from,
            review_date_to=review_date_to,
            limit=limit,
            offset=offset,
        )

    async def get_car_model_tags(
        self,
        branch_id: int,
        car_model: str | None = None,
    ) -> BranchCarModelsDTO:
        """
        지점별 차량 모델 태그 분석

        Args:
            branch_id: 지점 ID
            car_model: 특정 차량 모델만 조회 (None이면 전체)

        Returns:
            BranchCarModelsDTO: 차량별 태그 통계
        """
        from repository.session import get_client

        client = await get_client()

        # car_model_tags 테이블에서 조회
        query = (
            client.table("car_model_tags")
            .select("*, tags(id, name)")
            .eq("branch_id", branch_id)
        )

        if car_model:
            query = query.eq("car_model", car_model)

        try:
            result = await query.execute()
        except Exception as e:
            # 테이블이 없으면 빈 결과 반환
            if "Could not find" in str(e):
                return BranchCarModelsDTO(
                    branch_id=branch_id,
                    car_models=[],
                    error="car_model_tags 테이블이 없습니다. SQL을 먼저 실행하세요.",
                )
            raise

        if not result.data:
            return BranchCarModelsDTO(branch_id=branch_id, car_models=[])

        # 차량별로 그룹화
        car_data: dict[str, dict] = {}

        for row in result.data:
            car = row["car_model"]
            tag_info = row.get("tags") or {}
            tag_name = tag_info.get("name", "기타")

            if car not in car_data:
                car_data[car] = {"name": car, "tags": {}, "review_count": 0}

            if tag_name not in car_data[car]["tags"]:
                car_data[car]["tags"][tag_name] = {
                    "name": tag_name,
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0,
                    "total": 0,
                }

            car_data[car]["tags"][tag_name]["positive"] += row.get("positive_count", 0)
            car_data[car]["tags"][tag_name]["negative"] += row.get("negative_count", 0)
            car_data[car]["tags"][tag_name]["neutral"] += row.get("neutral_count", 0)
            car_data[car]["tags"][tag_name]["total"] += row.get("total_count", 0)

        # 리뷰 수 조회 (branch_reviews 테이블)
        for car in car_data:
            try:
                count_result = (
                    await client.table("branch_reviews")
                    .select("id", count="exact")
                    .eq("branch_id", branch_id)
                    .eq("car_model", car)
                    .execute()
                )
                car_data[car]["review_count"] = count_result.count or 0
            except Exception:
                car_data[car]["review_count"] = 0

        # DTO로 변환
        car_models_dto: list[CarModelDTO] = []
        for car, data in sorted(car_data.items()):
            # 태그 DTO 생성 (total 기준 정렬)
            tags_dto = sorted(
                [
                    CarModelTagDTO(
                        name=tag_data["name"],
                        positive=tag_data["positive"],
                        negative=tag_data["negative"],
                        neutral=tag_data["neutral"],
                        total=tag_data["total"],
                    )
                    for tag_data in data["tags"].values()
                ],
                key=lambda x: x.total,
                reverse=True,
            )

            car_models_dto.append(
                CarModelDTO(
                    name=data["name"],
                    review_count=data.get("review_count", 0),
                    tags=tags_dto,
                )
            )

        return BranchCarModelsDTO(branch_id=branch_id, car_models=car_models_dto)
