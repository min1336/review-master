"""
감정 분석 모듈
- 평점 기반 감정 분류
- 긍정/중립/부정 분류
"""

import pandas as pd
from typing import Dict, List
import warnings

warnings.filterwarnings('ignore')


class SentimentAnalyzer:
    """감정 분석 클래스"""
    
    def __init__(self):
        """감정 분석기 초기화"""
        self.stats = {}
        
    def classify_sentiment(self, rating: float) -> str:
        """
        평점 기반 감정 분류
        
        Args:
            rating: 차량 평점 (0.0 ~ 5.0)
        
        Returns:
            감정 레이블 (positive/neutral/negative/unknown)
        """
        if pd.isna(rating):
            return 'unknown'
        elif rating >= 4.0:
            return 'positive'
        elif rating >= 3.0:
            return 'neutral'
        else:
            return 'negative'
    
    def calculate_sentiment_score(self, rating: float, sentiment: str) -> float:
        """
        감정 점수 계산 (0.0 ~ 1.0)
        
        Args:
            rating: 차량 평점
            sentiment: 감정 레이블
        
        Returns:
            감정 점수
        """
        if pd.isna(rating):
            return 0.5
        
        if sentiment == 'positive':
            # 0.7 ~ 1.0
            return 0.7 + (rating - 4.0) / 1.0 * 0.3
        elif sentiment == 'neutral':
            # 0.4 ~ 0.7
            return 0.4 + (rating - 3.0) / 1.0 * 0.3
        else:  # negative
            # 0.0 ~ 0.4
            return max(0.0, rating / 3.0 * 0.4)
    
    def determine_confidence(self, score: float) -> str:
        """
        신뢰도 판단
        
        Args:
            score: 감정 점수
        
        Returns:
            신뢰도 (high/medium/low)
        """
        if score >= 0.8 or score <= 0.2:
            return 'high'
        elif score >= 0.6 or score <= 0.4:
            return 'medium'
        else:
            return 'low'
    
    def analyze_single(self, review: Dict) -> Dict:
        """
        단일 리뷰 감정 분석
        
        Args:
            review: 리뷰 데이터 (review_id, text, rating 포함)
        
        Returns:
            감정 분석 결과
        """
        rating = review.get('rating', 0)
        
        # 감정 분류
        sentiment = self.classify_sentiment(rating)
        
        # 점수 계산
        score = self.calculate_sentiment_score(rating, sentiment)
        
        # 신뢰도
        confidence = self.determine_confidence(score)
        
        return {
            'review_id': review.get('review_id'),
            'sentiment': sentiment,
            'sentiment_score': round(score, 3),
            'sentiment_method': 'rating_based',
            'confidence': confidence
        }
    
    def analyze_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        DataFrame 전체 감정 분석
        
        Args:
            df: 리뷰 DataFrame (차량평점 컬럼 필요)
        
        Returns:
            감정 분석 결과 추가된 DataFrame
        """
        print("="*80)
        print("😊 감정 분석 시작")
        print("="*80)
        
        # 컬럼명 매핑
        df_work = df.copy()
        review_data = []
        
        for idx, row in df_work.iterrows():
            review_data.append({
                'review_id': row.get('리뷰번호', idx),
                'rating': row.get('차량평점', 0)
            })
        
        # 감정 분석 수행
        results = [self.analyze_single(r) for r in review_data]
        results_df = pd.DataFrame(results)
        
        # 원본 DataFrame에 병합
        df_work['sentiment'] = results_df['sentiment']
        df_work['sentiment_score'] = results_df['sentiment_score']
        df_work['sentiment_method'] = results_df['sentiment_method']
        df_work['confidence'] = results_df['confidence']
        
        # 통계
        sentiment_counts = df_work['sentiment'].value_counts()
        
        self.stats = {
            'total': len(df_work),
            'positive': sentiment_counts.get('positive', 0),
            'neutral': sentiment_counts.get('neutral', 0),
            'negative': sentiment_counts.get('negative', 0),
            'unknown': sentiment_counts.get('unknown', 0)
        }
        
        print(f"\n✅ 감정 분석 완료")
        print(f"   - 총 리뷰: {len(df_work):,}개")
        print(f"   - 긍정: {self.stats['positive']:,}개 ({self.stats['positive']/len(df_work)*100:.1f}%)")
        print(f"   - 중립: {self.stats['neutral']:,}개 ({self.stats['neutral']/len(df_work)*100:.1f}%)")
        print(f"   - 부정: {self.stats['negative']:,}개 ({self.stats['negative']/len(df_work)*100:.1f}%)")
        
        return df_work
    
    def filter_positive(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        긍정 리뷰만 필터링
        
        Args:
            df: 감정 분석된 DataFrame
        
        Returns:
            긍정 리뷰만 포함된 DataFrame
        """
        print(f"\n{'='*80}")
        print("✨ 긍정 리뷰 선별")
        print("="*80)
        
        original_count = len(df)
        df_positive = df[df['sentiment'] == 'positive'].copy()
        
        excluded = original_count - len(df_positive)
        
        print(f"✅ 긍정 리뷰 선별 완료")
        print(f"   - AI 처리 대상: {len(df_positive):,}개")
        print(f"   - 제외 (중립/부정): {excluded:,}개 ({excluded/original_count*100:.1f}%)")
        
        return df_positive
    
    def get_statistics(self) -> Dict:
        """
        감정 분석 통계 반환
        
        Returns:
            통계 딕셔너리
        """
        return self.stats


# 실행 예시
if __name__ == '__main__':
    # 테스트 데이터
    test_reviews = [
        {'review_id': 1, 'rating': 5.0, 'text': '정말 좋았어요!'},
        {'review_id': 2, 'rating': 4.5, 'text': '만족스럽습니다'},
        {'review_id': 3, 'rating': 3.5, 'text': '그냥 그래요'},
        {'review_id': 4, 'rating': 2.0, 'text': '별로였어요'},
        {'review_id': 5, 'rating': 1.0, 'text': '최악입니다'},
    ]
    
    # 감정 분석기 생성
    analyzer = SentimentAnalyzer()
    
    # 단일 리뷰 분석
    print("="*80)
    print("단일 리뷰 감정 분석 테스트")
    print("="*80)
    
    for review in test_reviews:
        result = analyzer.analyze_single(review)
        print(f"\n리뷰 ID {result['review_id']}:")
        print(f"  평점: {review['rating']}")
        print(f"  감정: {result['sentiment']}")
        print(f"  점수: {result['sentiment_score']}")
        print(f"  신뢰도: {result['confidence']}")
    
    print("\n" + "🎉 "*40)
    print("감정 분석 테스트 완료!")
    print("🎉 "*40)
