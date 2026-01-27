from __future__ import annotations

import asyncio
from datetime import datetime

from schemas.dto import (
    BranchDetailDTO,
    BranchReviewsDTO,
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


class SummaryService:
    """요약 비즈니스 로직"""

    def __init__(self, summary_repo, branch_tag_repo, review_repo):
        self.summary_repo = summary_repo
        self.branch_tag_repo = branch_tag_repo
        self.review_repo = review_repo

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
        """AI 요약 재생성"""
        from infrastructure.llm import get_provider
        from infrastructure.llm.prompts import SummaryPromptBuilder

        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        branch_name = summary_data.get("branch_name", f"지점 {branch_id}")
        review_count = summary_data.get("review_count", 0)
        keywords = summary_data.get("keywords") or []

        period_labels = {
            "all": "전체 기간",
            "1y": "최근 1년",
            "6m": "최근 6개월",
            "3m": "최근 3개월",
            "1m": "최근 1개월",
        }
        period_label = period_labels.get(period, "전체 기간")

        system_prompt, user_prompt = SummaryPromptBuilder.create_summary_prompt(
            keywords=keywords[:10] if keywords else ["리뷰"],
            review_count=review_count,
            representative_reviews=[],
            branch_name=branch_name,
        )

        user_prompt = f"[분석 기간: {period_label}]\n\n" + user_prompt

        llm_provider = get_provider()
        response = await asyncio.to_thread(
            llm_provider.generate,
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=300,
            temperature=0.7,
        )

        generated_summary = (
            response.content if hasattr(response, "content") else str(response)
        )

        existing_pending = summary_data.get("pending_summaries") or {}
        existing_pending[period] = generated_summary

        await self.summary_repo.upsert_by_branch_id(
            {"branch_id": branch_id, "pending_summaries": existing_pending}
        )

        return generated_summary

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
