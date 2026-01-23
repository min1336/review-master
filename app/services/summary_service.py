"""
요약 Service - 비즈니스 로직
"""
import asyncio
import re
from typing import Optional, List
from datetime import datetime, timedelta
from collections import Counter

from crud import UnitOfWork


class SummaryService:
    """요약 비즈니스 로직"""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def get_summaries(
        self,
        status: Optional[str] = None,
        region: Optional[str] = None,
        keyword: Optional[str] = None,
        min_rating: Optional[float] = None,
        max_rating: Optional[float] = None,
        min_reviews: int = 30,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = 'branch_id',
        order: str = 'asc'
    ) -> List[dict]:
        """요약 목록 조회"""
        if keyword or min_rating or max_rating:
            summaries = await self.uow.summaries.search(
                keyword=keyword,
                region=region,
                min_rating=min_rating,
                max_rating=max_rating,
                min_reviews=min_reviews,
                limit=limit
            )
        else:
            summaries = await self.uow.summaries.get_all_with_filters(
                status=status,
                region=region,
                min_reviews=min_reviews,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                order=order
            )

        # Pydantic 모델을 dict로 변환
        return [s.model_dump() if hasattr(s, 'model_dump') else s for s in summaries]

    async def get_summary(self, branch_id: int) -> Optional[dict]:
        """단일 요약 조회"""
        summary = await self.uow.summaries.get_by_branch_id(branch_id)
        return summary.model_dump() if summary else None

    async def get_summary_with_tags(self, branch_id: int) -> dict:
        """요약과 태그 함께 조회"""
        summary = await self.uow.summaries.get_by_branch_id(branch_id)
        tags = await self.uow.branch_tags.get_by_branch(branch_id)

        return {
            "summary": summary.model_dump() if summary else None,
            "tags": [t.model_dump() for t in tags]
        }

    async def update_summary(self, branch_id: int, data: dict) -> dict:
        """요약 수정"""
        data['branch_id'] = branch_id
        result = await self.uow.summaries.upsert_by_branch_id(data)
        return result.model_dump() if result else None

    async def update_status(self, branch_id: int, status: str) -> dict:
        """상태 변경"""
        result = await self.uow.summaries.update_status(branch_id, status)
        return result.model_dump() if result else None

    async def get_stats(self) -> dict:
        """통계 조회"""
        return await self.uow.summaries.get_stats()

    async def get_region_stats(self) -> List[dict]:
        """지역별 통계"""
        # 직접 쿼리 필요
        result = await self.uow.summaries._client.table('branch_summaries').select(
            'region, avg_rating, review_count'
        ).execute()

        if not result.data:
            return []

        region_stats = {}
        for row in result.data:
            region = row.get('region') or '미분류'
            city = region.split()[0] if region and region.strip() else '미분류'

            if city not in region_stats:
                region_stats[city] = {
                    'region': city, 'count': 0, 'total_reviews': 0,
                    'rating_sum': 0, 'rating_count': 0
                }

            region_stats[city]['count'] += 1
            region_stats[city]['total_reviews'] += row.get('review_count') or 0

            if row.get('avg_rating'):
                region_stats[city]['rating_sum'] += float(row['avg_rating'])
                region_stats[city]['rating_count'] += 1

        stats_list = []
        for city, stats in region_stats.items():
            avg_rating = 0
            if stats['rating_count'] > 0:
                avg_rating = round(stats['rating_sum'] / stats['rating_count'], 2)

            stats_list.append({
                'region': city,
                'count': stats['count'],
                'avg_rating': avg_rating,
                'total_reviews': stats['total_reviews']
            })

        stats_list.sort(key=lambda x: x['count'], reverse=True)
        return stats_list

    async def get_rating_stats(self) -> dict:
        """평점 분포 통계"""
        result = await self.uow.summaries._client.table('branch_summaries').select('avg_rating').execute()

        ratings = [r['avg_rating'] for r in result.data if r.get('avg_rating')]

        if not ratings:
            return {
                'min': 0, 'max': 0, 'avg': 0,
                'distribution': {}, 'total': 0
            }

        distribution = {
            '4.5-5.0': 0, '4.0-4.5': 0, '3.5-4.0': 0,
            '3.0-3.5': 0, '<3.0': 0
        }

        for r in ratings:
            if r >= 4.5:
                distribution['4.5-5.0'] += 1
            elif r >= 4.0:
                distribution['4.0-4.5'] += 1
            elif r >= 3.5:
                distribution['3.5-4.0'] += 1
            elif r >= 3.0:
                distribution['3.0-3.5'] += 1
            else:
                distribution['<3.0'] += 1

        return {
            'min': min(ratings),
            'max': max(ratings),
            'avg': round(sum(ratings) / len(ratings), 2),
            'distribution': distribution,
            'total': len(ratings)
        }

    async def regenerate_summary(self, branch_id: int, period: str = 'all') -> str:
        """AI 요약 재생성"""
        from infrastructure.llm import get_provider
        from infrastructure.llm.prompts import PromptTemplates

        summary = await self.uow.summaries.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        branch_name = summary_data.get('branch_name', f'지점 {branch_id}')
        review_count = summary_data.get('review_count', 0)
        keywords = summary_data.get('keywords') or []

        period_labels = {
            'all': '전체 기간', '1y': '최근 1년', '6m': '최근 6개월',
            '3m': '최근 3개월', '1m': '최근 1개월'
        }
        period_label = period_labels.get(period, '전체 기간')

        # 프롬프트 생성
        system_prompt, user_prompt = SummaryPromptBuilder.create_summary_prompt(
            keywords=keywords[:10] if keywords else ['리뷰'],
            review_count=review_count,
            representative_reviews=[],
            branch_name=branch_name
        )

        user_prompt = f"[분석 기간: {period_label}]\n\n" + user_prompt

        # LLM 호출 (blocking → thread)
        llm_provider = get_provider()
        response = await asyncio.to_thread(
            llm_provider.generate,
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=300,
            temperature=0.7
        )

        generated_summary = response.content if hasattr(response, 'content') else str(response)

        # pending_summaries에 저장 (바로 덮어쓰지 않음)
        existing_pending = summary_data.get('pending_summaries') or {}
        existing_pending[period] = generated_summary

        await self.uow.summaries.upsert_by_branch_id({
            'branch_id': branch_id,
            'pending_summaries': existing_pending
        })

        return generated_summary

    async def apply_pending_summary(self, branch_id: int, period: str) -> dict:
        """대기 중인 요약을 적용 (pending → main)"""
        summary = await self.uow.summaries.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        pending = summary_data.get('pending_summaries') or {}

        if period not in pending:
            raise ValueError(f"대기 중인 {period} 요약이 없습니다")

        # pending → main 필드로 이동
        field_map = {
            'all': 'summary_all', '1y': 'summary_1y', '6m': 'summary_6m',
            '3m': 'summary_3m', '1m': 'summary_1m'
        }

        new_summary = pending.pop(period)

        await self.uow.summaries.upsert_by_branch_id({
            'branch_id': branch_id,
            field_map[period]: new_summary,
            'pending_summaries': pending  # 적용한 항목 제거
        })

        return {'applied': new_summary, 'period': period}

    async def discard_pending_summary(self, branch_id: int, period: str) -> dict:
        """대기 중인 요약 취소 (삭제)"""
        summary = await self.uow.summaries.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        pending = summary_data.get('pending_summaries') or {}

        if period in pending:
            del pending[period]
            await self.uow.summaries.upsert_by_branch_id({
                'branch_id': branch_id,
                'pending_summaries': pending
            })

        return {'discarded': period}

    async def get_branch_detail(
        self,
        branch_id: int,
        include_summaries: bool = True,
        max_reviews: int = 500
    ) -> dict:
        """
        지점 상세 분석 (JSON 반환)

        - 리뷰별 키워드 추출
        - 태그+감정 분류
        - 기간별 AI 요약 (선택)
        """
        from services.analysis import KeywordExtractor, RuleBasedABSA

        # 1. 기본 정보 조회
        summary = await self.uow.summaries.get_by_branch_id(branch_id)
        if not summary:
            return None

        summary_data = summary.model_dump()
        branch_name = summary_data.get('branch_name', f'지점 {branch_id}')
        location = summary_data.get('region', '')

        # 2. 리뷰 데이터 조회
        reviews_result = await self.uow.branch_reviews.get_by_branch(
            branch_id=branch_id,
            limit=max_reviews
        )
        reviews_data = reviews_result.get('reviews', [])
        review_count = reviews_result.get('total', 0)

        if not reviews_data:
            return {
                'branch_id': branch_id,
                'branch_name': branch_name,
                'location': location,
                'review_count': 0,
                'tags': [],
                'summaries': {},
                'reviews': []
            }

        # 3. 키워드 추출 (blocking → thread)
        review_texts = [r.get('content', '') or '' for r in reviews_data]

        def extract_keywords():
            extractor = KeywordExtractor()
            return extractor.extract_batch(review_texts)

        all_keywords = await asyncio.to_thread(extract_keywords)

        # 4. 태그+감정 분류 (blocking → thread)
        def classify_reviews():
            classifier = RuleBasedABSA()
            results = []
            tag_totals = {}

            for i, (keywords, review_text) in enumerate(zip(all_keywords, review_texts)):
                result = classifier.classify_review(review_text, keywords[:10])

                tag_parts = []
                for tag, sentiments in result.items():
                    pos = len(sentiments.get('positive', []))
                    neg = len(sentiments.get('negative', []))
                    neu = len(sentiments.get('neutral', []))

                    if tag not in tag_totals:
                        tag_totals[tag] = {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0}
                    tag_totals[tag]['positive'] += pos
                    tag_totals[tag]['negative'] += neg
                    tag_totals[tag]['neutral'] += neu
                    tag_totals[tag]['total'] += pos + neg + neu

                    if pos > neg:
                        tag_parts.append(f"{tag}(+)")
                    elif neg > pos:
                        tag_parts.append(f"{tag}(-)")

                results.append(', '.join(tag_parts))

            return results, tag_totals

        tag_sentiments, tag_totals = await asyncio.to_thread(classify_reviews)

        # 5. 태그 목록 정리
        sorted_tags = sorted(tag_totals.items(), key=lambda x: x[1]['total'], reverse=True)
        tags_list = [
            {
                'name': tag,
                'total': counts['total'],
                'positive': counts['positive'],
                'negative': counts['negative']
            }
            for tag, counts in sorted_tags
        ]

        # 6. 리뷰 데이터 정리
        reviews_output = []
        for i, review in enumerate(reviews_data):
            reviews_output.append({
                'id': review.get('review_id'),
                'date': review.get('review_date'),
                'content': review.get('content', '')[:500],
                'keywords': all_keywords[i][:10] if i < len(all_keywords) else [],
                'tag_sentiments': tag_sentiments[i] if i < len(tag_sentiments) else ''
            })

        # 7. 기간별 요약 (옵션)
        summaries_output = {}
        if include_summaries:
            summaries_output = {
                '1m': summary_data.get('summary_1m', ''),
                '3m': summary_data.get('summary_3m', ''),
                '6m': summary_data.get('summary_6m', ''),
                '1y': summary_data.get('summary_1y', ''),
                'all': summary_data.get('summary_all', '')
            }

        return {
            'branch_id': branch_id,
            'branch_name': branch_name,
            'location': location,
            'review_count': review_count,
            'tags': tags_list,
            'summaries': summaries_output,
            'reviews': reviews_output
        }

    async def get_branch_reviews(
        self,
        branch_id: int,
        car_model: Optional[str] = None,
        sentiment: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> dict:
        """
        지점별 원본 리뷰 목록 조회 (필터링 지원)

        branch_reviews 테이블에서 페이징된 리뷰 목록 반환
        """
        result = await self.uow.branch_reviews.get_by_branch(
            branch_id=branch_id,
            car_model=car_model,
            sentiment=sentiment,
            limit=limit,
            offset=offset
        )
        return result
