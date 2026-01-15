"""
리뷰 키워드 가중치 계산 모듈

가중치 요소:
1. 최신성: 1개월 이내 2.0x, 3개월 1.5x, 1년 이내 1.0x, 1년+ 0.3x
2. 공감수: 10+ 2.5x, 5+ 1.8x, 1+ 1.3x, 0 1.0x
3. 리뷰 길이: 100자+ 1.5x, 50자+ 1.2x, 20자- 0.3x
4. 별점: 4.5+ 1.2x, 3.0- 0.2x
5. 품질 점수: 감정분석 신뢰도 기반
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd


class WeightCalculator:
    """리뷰 키워드 가중치 계산기"""

    # 가중치 설정 (조정 가능)
    CONFIG = {
        # 최신성 가중치
        'recency': {
            30: 2.0,    # 1개월 이내
            90: 1.5,    # 3개월 이내
            365: 1.0,   # 1년 이내
            'default': 0.3  # 1년 이상
        },
        # 공감수 가중치
        'engagement': {
            10: 2.5,    # 10개 이상
            5: 1.8,     # 5개 이상
            1: 1.3,     # 1개 이상
            'default': 1.0
        },
        # 리뷰 길이 가중치
        'length': {
            100: 1.5,   # 100자 이상
            50: 1.2,    # 50자 이상
            20: 0.3,    # 20자 미만 (패널티)
            'default': 1.0
        },
        # 별점 가중치
        'rating': {
            4.5: 1.2,   # 4.5점 이상 (보너스)
            3.0: 0.2,   # 3.0점 이하 (패널티)
            'default': 1.0
        },
        # 신규 키워드 감소 계수
        'new_keyword_factor': 0.5,
        # 시간 감쇠 계수 (매 업데이트마다)
        'time_decay_factor': 0.95
    }

    def __init__(self, config: Optional[Dict] = None):
        """
        Args:
            config: 커스텀 가중치 설정 (선택적)
        """
        if config:
            self.config = {**self.CONFIG, **config}
        else:
            self.config = self.CONFIG

    def calculate_review_weight(
        self,
        review_date: datetime,
        engagement_count: int = 0,
        review_length: int = 0,
        rating: float = 4.0,
        sentiment_score: float = 0.5,
        reference_date: Optional[datetime] = None
    ) -> float:
        """
        리뷰의 종합 가중치 계산

        Args:
            review_date: 리뷰 작성일
            engagement_count: 공감수 (도움돼요수)
            review_length: 리뷰 길이 (글자수)
            rating: 별점 (1.0 ~ 5.0)
            sentiment_score: 감정분석 점수 (0 ~ 1)
            reference_date: 기준일 (기본: 현재)

        Returns:
            종합 가중치 (1.0 기준)
        """
        if reference_date is None:
            reference_date = datetime.now()

        weight = 1.0

        # 1. 최신성 가중치
        weight *= self._calc_recency_weight(review_date, reference_date)

        # 2. 공감수 가중치
        weight *= self._calc_engagement_weight(engagement_count)

        # 3. 리뷰 길이 가중치
        weight *= self._calc_length_weight(review_length)

        # 4. 별점 가중치
        weight *= self._calc_rating_weight(rating)

        # 5. 감정분석 신뢰도 가중치 (0.5 ~ 1.5 범위)
        weight *= (0.5 + sentiment_score)

        return round(weight, 3)

    def _calc_recency_weight(self, review_date: datetime, reference_date: datetime) -> float:
        """최신성 가중치"""
        if not review_date:
            return self.config['recency']['default']

        # timezone aware 처리
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
        else:
            return recency['default']

    def _calc_engagement_weight(self, count: int) -> float:
        """공감수 가중치"""
        engagement = self.config['engagement']
        if count >= 10:
            return engagement[10]
        elif count >= 5:
            return engagement[5]
        elif count >= 1:
            return engagement[1]
        else:
            return engagement['default']

    def _calc_length_weight(self, length: int) -> float:
        """리뷰 길이 가중치"""
        length_cfg = self.config['length']
        if length >= 100:
            return length_cfg[100]
        elif length >= 50:
            return length_cfg[50]
        elif length < 20:
            return length_cfg[20]
        else:
            return length_cfg['default']

    def _calc_rating_weight(self, rating: float) -> float:
        """별점 가중치"""
        rating_cfg = self.config['rating']
        if rating >= 4.5:
            return rating_cfg[4.5]
        elif rating <= 3.0:
            return rating_cfg[3.0]
        else:
            return rating_cfg['default']

    def calculate_from_dataframe_row(self, row: pd.Series) -> float:
        """
        DataFrame 행에서 가중치 계산

        예상 컬럼:
        - 등록일시: 리뷰 작성일
        - 도움돼요수: 공감수
        - 리뷰내용: 리뷰 텍스트
        - 지점평점(친절/편의성) 또는 차량평점: 별점
        - sentiment_score: 감정분석 점수 (있는 경우)
        """
        # 등록일시
        review_date = None
        if '등록일시' in row.index and pd.notna(row['등록일시']):
            review_date = pd.to_datetime(row['등록일시'])

        # 공감수
        engagement = 0
        if '도움돼요수' in row.index and pd.notna(row['도움돼요수']):
            engagement = int(row['도움돼요수'])

        # 리뷰 길이
        length = 0
        if '리뷰내용' in row.index and pd.notna(row['리뷰내용']):
            length = len(str(row['리뷰내용']))

        # 별점 (여러 컬럼 체크)
        rating = 4.0
        for col in ['지점평점(친절/편의성)', '차량평점', '지점평점']:
            if col in row.index and pd.notna(row[col]):
                rating = float(row[col])
                break

        # 감정분석 점수
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
        """신규 키워드 감소 계수 적용"""
        return weight * self.config['new_keyword_factor']

    def apply_time_decay(self, score: float) -> float:
        """시간 감쇠 적용"""
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
        """
        키워드 점수 업데이트

        Args:
            branch_id: 지점 번호
            keywords: 추출된 키워드 리스트
            weight: 리뷰 가중치
            review_date: 리뷰 작성일
            is_new_review: 신규 리뷰 여부 (API에서 온 경우 True)
        """
        if branch_id not in self.branch_keywords:
            self.branch_keywords[branch_id] = {}

        branch_kws = self.branch_keywords[branch_id]

        for kw in keywords:
            if kw in branch_kws:
                # 기존 키워드: 가중치 누적
                branch_kws[kw]['raw_count'] += 1
                branch_kws[kw]['weighted_score'] += weight
                branch_kws[kw]['last_seen_at'] = review_date
            else:
                # 신규 키워드
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
        """
        키워드 변화 감지 (요약 재생성 필요 여부)

        Args:
            branch_id: 지점 번호
            old_top_keywords: 이전 TOP 키워드 리스트
            threshold: 변화 임계값 (0.3 = 30% 이상 변경시)

        Returns:
            True면 요약 재생성 필요
        """
        new_top = [kw['keyword'] for kw in self.get_top_keywords(branch_id, len(old_top_keywords))]

        if not old_top_keywords:
            return True

        # 겹치는 키워드 비율 계산
        overlap = len(set(old_top_keywords) & set(new_top))
        overlap_ratio = overlap / len(old_top_keywords)

        # 30% 이상 변경되면 재생성 필요
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


# 테스트
if __name__ == '__main__':
    from datetime import datetime, timedelta

    calc = WeightCalculator()

    # 테스트 케이스
    print("=== 가중치 계산 테스트 ===\n")

    # 1. 최근 + 높은 공감수 리뷰
    w1 = calc.calculate_review_weight(
        review_date=datetime.now() - timedelta(days=7),
        engagement_count=15,
        review_length=120,
        rating=4.8,
        sentiment_score=0.85
    )
    print(f"최근 + 인기 리뷰: {w1}")  # 예상: 높은 가중치

    # 2. 오래된 + 공감 없는 리뷰
    w2 = calc.calculate_review_weight(
        review_date=datetime.now() - timedelta(days=400),
        engagement_count=0,
        review_length=30,
        rating=3.5,
        sentiment_score=0.5
    )
    print(f"오래된 + 평범한 리뷰: {w2}")  # 예상: 낮은 가중치

    # 3. 짧은 리뷰
    w3 = calc.calculate_review_weight(
        review_date=datetime.now() - timedelta(days=60),
        engagement_count=2,
        review_length=15,
        rating=4.0,
        sentiment_score=0.6
    )
    print(f"짧은 리뷰: {w3}")  # 예상: 패널티 적용

    print(f"\n가중치 비교: 인기({w1}) > 평범({w2}) > 짧은({w3})")
