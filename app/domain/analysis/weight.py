"""
리뷰 키워드 가중치 계산 모듈

가중치 요소:
1. 최신성: 1개월 이내 2.0x, 3개월 1.5x, 1년 이내 1.0x, 1년+ 0.3x
2. 공감수: 10+ 2.5x, 5+ 1.8x, 1+ 1.3x, 0 1.0x
3. 리뷰 길이: 100자+ 1.5x, 50자+ 1.2x, 20자- 0.3x
4. 별점: 4.5+ 1.2x, 3.0- 0.2x
5. 품질 점수: 감정분석 신뢰도 기반
"""
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd


class WeightCalculator:
    """리뷰 키워드 가중치 계산기"""

    CONFIG = {
        'recency': {
            30: 2.0,    # 1개월 이내
            90: 1.5,    # 3개월 이내
            365: 1.0,   # 1년 이내
            'default': 0.3
        },
        'engagement': {
            10: 2.5,
            5: 1.8,
            1: 1.3,
            'default': 1.0
        },
        'length': {
            100: 1.5,
            50: 1.2,
            20: 0.3,
            'default': 1.0
        },
        'rating': {
            4.5: 1.2,
            3.0: 0.2,
            'default': 1.0
        },
        'new_keyword_factor': 0.5,
        'time_decay_factor': 0.95
    }

    def __init__(self, config: Optional[Dict] = None):
        self.config = {**self.CONFIG, **(config or {})}

    def calculate_review_weight(
        self,
        review_date: datetime,
        engagement_count: int = 0,
        review_length: int = 0,
        rating: float = 4.0,
        sentiment_score: float = 0.5,
        reference_date: Optional[datetime] = None
    ) -> float:
        """리뷰의 종합 가중치 계산"""
        if reference_date is None:
            reference_date = datetime.now()

        weight = 1.0
        weight *= self._calc_recency_weight(review_date, reference_date)
        weight *= self._calc_engagement_weight(engagement_count)
        weight *= self._calc_length_weight(review_length)
        weight *= self._calc_rating_weight(rating)
        weight *= (0.5 + sentiment_score)

        return round(weight, 3)

    def _calc_recency_weight(self, review_date: datetime, reference_date: datetime) -> float:
        if not review_date:
            return self.config['recency']['default']

        if hasattr(review_date, 'tzinfo') and review_date.tzinfo:
            if not reference_date.tzinfo:
                reference_date = reference_date.replace(tzinfo=review_date.tzinfo)

        days_ago = (reference_date - review_date).days
        recency = self.config['recency']

        if days_ago <= 30:
            return recency[30]
        elif days_ago <= 90:
            return recency[90]
        elif days_ago <= 365:
            return recency[365]
        return recency['default']

    def _calc_engagement_weight(self, count: int) -> float:
        engagement = self.config['engagement']
        if count >= 10:
            return engagement[10]
        elif count >= 5:
            return engagement[5]
        elif count >= 1:
            return engagement[1]
        return engagement['default']

    def _calc_length_weight(self, length: int) -> float:
        length_cfg = self.config['length']
        if length >= 100:
            return length_cfg[100]
        elif length >= 50:
            return length_cfg[50]
        elif length < 20:
            return length_cfg[20]
        return length_cfg['default']

    def _calc_rating_weight(self, rating: float) -> float:
        rating_cfg = self.config['rating']
        if rating >= 4.5:
            return rating_cfg[4.5]
        elif rating <= 3.0:
            return rating_cfg[3.0]
        return rating_cfg['default']

    def calculate_from_dataframe_row(self, row: pd.Series) -> float:
        """DataFrame 행에서 가중치 계산"""
        review_date = None
        if '등록일시' in row.index and pd.notna(row['등록일시']):
            review_date = pd.to_datetime(row['등록일시'])

        engagement = 0
        if '도움돼요수' in row.index and pd.notna(row['도움돼요수']):
            engagement = int(row['도움돼요수'])

        length = 0
        if '리뷰내용' in row.index and pd.notna(row['리뷰내용']):
            length = len(str(row['리뷰내용']))

        rating = 4.0
        for col in ['지점평점(친절/편의성)', '차량평점', '지점평점']:
            if col in row.index and pd.notna(row[col]):
                rating = float(row[col])
                break

        sentiment = 0.5
        if 'sentiment_score' in row.index and pd.notna(row['sentiment_score']):
            sentiment = float(row['sentiment_score'])

        return self.calculate_review_weight(
            review_date=review_date,
            engagement_count=engagement,
            review_length=length,
            rating=rating,
            sentiment_score=sentiment
        )

    def apply_new_keyword_factor(self, weight: float) -> float:
        return weight * self.config['new_keyword_factor']

    def apply_time_decay(self, score: float) -> float:
        return score * self.config['time_decay_factor']


class KeywordScoreManager:
    """지점별 키워드 점수 관리"""

    def __init__(self, weight_calculator: Optional[WeightCalculator] = None):
        self.calculator = weight_calculator or WeightCalculator()
        self.branch_keywords: Dict[int, Dict[str, dict]] = {}

    def load_from_db(self, branch_id: int, keywords_data: List[Dict]):
        """DB에서 키워드 데이터 로드"""
        self.branch_keywords[branch_id] = {}
        for kw_data in keywords_data:
            self.branch_keywords[branch_id][kw_data['keyword']] = {
                'raw_count': kw_data.get('raw_count', 0),
                'weighted_score': kw_data.get('weighted_score', 0),
                'last_seen_at': kw_data.get('last_seen_at')
            }

    def update_keywords(
        self,
        branch_id: int,
        keywords: List[str],
        weight: float,
        review_date: datetime,
        is_new_review: bool = True
    ):
        """키워드 점수 업데이트"""
        if branch_id not in self.branch_keywords:
            self.branch_keywords[branch_id] = {}

        branch_kws = self.branch_keywords[branch_id]

        for kw in keywords:
            if kw in branch_kws:
                branch_kws[kw]['raw_count'] += 1
                branch_kws[kw]['weighted_score'] += weight
                branch_kws[kw]['last_seen_at'] = review_date
            else:
                adjusted_weight = self.calculator.apply_new_keyword_factor(weight) if is_new_review else weight
                branch_kws[kw] = {
                    'raw_count': 1,
                    'weighted_score': adjusted_weight,
                    'last_seen_at': review_date
                }

    def apply_decay_to_all(self):
        """전체 키워드에 시간 감쇠 적용"""
        for branch_id in self.branch_keywords:
            for kw in self.branch_keywords[branch_id]:
                old_score = self.branch_keywords[branch_id][kw]['weighted_score']
                self.branch_keywords[branch_id][kw]['weighted_score'] = \
                    self.calculator.apply_time_decay(old_score)

    def get_top_keywords(self, branch_id: int, limit: int = 10) -> List[Dict]:
        """지점의 TOP N 키워드 반환"""
        if branch_id not in self.branch_keywords:
            return []

        keywords = self.branch_keywords[branch_id]
        sorted_kws = sorted(
            keywords.items(),
            key=lambda x: x[1]['weighted_score'],
            reverse=True
        )

        return [
            {
                'keyword': kw,
                'weighted_score': data['weighted_score'],
                'raw_count': data['raw_count'],
                'rank': idx + 1
            }
            for idx, (kw, data) in enumerate(sorted_kws[:limit])
        ]

    def detect_significant_change(
        self,
        branch_id: int,
        old_top_keywords: List[str],
        threshold: float = 0.3
    ) -> bool:
        """키워드 변화 감지"""
        new_top = [kw['keyword'] for kw in self.get_top_keywords(branch_id, len(old_top_keywords))]

        if not old_top_keywords:
            return True

        overlap = len(set(old_top_keywords) & set(new_top))
        overlap_ratio = overlap / len(old_top_keywords)

        return (1 - overlap_ratio) >= threshold

    def export_for_db(self, branch_id: int) -> List[Dict]:
        """DB 저장용 데이터 추출"""
        if branch_id not in self.branch_keywords:
            return []

        return [
            {
                'branch_id': branch_id,
                'keyword': kw,
                'raw_count': data['raw_count'],
                'weighted_score': round(data['weighted_score'], 2),
                'last_seen_at': data['last_seen_at'].isoformat() if data['last_seen_at'] else None
            }
            for kw, data in self.branch_keywords[branch_id].items()
        ]
