"""
ABSA (Aspect-Based Sentiment Analysis) 모듈
- 카테고리별 감정 분석
- 서비스, 차량상태, 가격, 위치, 절차 등으로 분류
"""

import pandas as pd
from typing import Dict, List
import warnings

warnings.filterwarnings('ignore')


class AspectClassifier:
    """ABSA (Aspect-Based Sentiment Analysis) 분류기"""
    
    # 12개 카테고리로 확장된 키워드 매핑
    ASPECT_KEYWORDS = {
        # 서비스 관련 (3개 카테고리)
        '친절한응대': [
            '친절', '친절하', '친절한', '친절하게', '친절하시고', 
            '응대', '직원', '안내', '설명', '대응', '태도', '배려',
            '상냥', '정중', '세심', '도움'
        ],
        '다양한서비스': [
            '다양', '편의', '서비스', '지원', '추가', '옵션',
            '할인', '이벤트', '혜택', '프로모션', '멤버십', '포인트'
        ],
        '빠른절차': [
            '빠른', '신속', '간편', '수월', '편리', '빠르', 
            '절차', '간단', '쉬운', '손쉬운', '빨리', '금방', '바로'
        ],
        
        # 차량 관련 (3개 카테고리)
        '청결함': [
            '깨끗', '청결', '깔끔', '깨끗하', '깨끗하고', 
            '세차', '위생', '정리', '청소', '말끔'
        ],
        '차량외관상태좋음': [
            '외관', '상태', '관리', '신차', '새것', '컨디션',
            '깔끔', '무사고', '흠집', '스크래치'
        ],
        '차량기능정상': [
            '기능', '작동', '정상', '문제없', '이상없', 
            '엔진', '에어컨', '히터', '네비', '블루투스', 'usb'
        ],
        
        # 차량 옵션
        '차량옵션많음': [
            '전기차', '하이브리드', '옵션', '장착', '최신', 
            '선루프', '통풍시트', '열선', '후방카메라', '크루즈'
        ],
        
        # 가격/가치
        '가성비': [
            '저렴', '가성비', '합리적', '경제적', '싸', '저렴하',
            '가격', '비용', '할인', '프로모션', '쿠폰', '포인트'
        ],
        
        # 위치/이동
        '가까운위치': [
            '위치', '접근성', '가까', '편리', '역', '터미널', '공항',
            '찾기쉬운', '교통', '주차', '거리', '근처'
        ],
        '셔틀': [
            '셔틀', '픽업', '송영', '공항', '역', '이동', 
            '배차', '모시', '데려다', '데리러'
        ],
        
        # 배차/반납
        '빠른배차및반납': [
            '배차', '반납', '인수', '인계', '대기',
            '빠른', '신속', '즉시', '바로', '대기시간', '준비'
        ],
        
        # 기타 서비스
        '주유가득': [
            '주유', '가득', '만유', '기름', '연료',
            '충전', '풀충전', '만충', '주유비'
        ]
    }
    
    def __init__(self):
        """ABSA 분류기 초기화"""
        self.stats = {
            'total_reviews': 0,
            'categorized_reviews': 0
        }
    
    def classify_aspect(self, text: str, keywords: List[str]) -> Dict[str, Dict]:
        """
        단일 리뷰의 카테고리 분류
        
        Args:
            text: 리뷰 텍스트
            keywords: 추출된 키워드 리스트
        
        Returns:
            카테고리별 점수 딕셔너리
        """
        if pd.isna(text):
            text = ""
        
        text = str(text).lower()
        aspect_scores = {}
        
        for category, category_keywords in self.ASPECT_KEYWORDS.items():
            # 1. 카테고리 키워드가 텍스트에 포함되어 있는지 확인
            text_mentions = sum(1 for kw in category_keywords if kw in text)
            
            # 2. 추출된 키워드와 겹치는지 확인
            keyword_match = sum(
                1 for kw in keywords 
                if any(cat_kw in kw or kw in cat_kw for cat_kw in category_keywords)
            )
            
            # 3. 점수 계산 (키워드 매칭에 더 높은 가중치)
            score = text_mentions + keyword_match * 2
            
            if score > 0:
                aspect_scores[category] = {
                    'mentioned': True,
                    'score': score,
                    'sentiment': 'positive'  # 긍정 리뷰만 처리하므로 항상 positive
                }
        
        return aspect_scores
    
    def classify_aspects_for_branch(self, df: pd.DataFrame, branch_id: int, 
                                   keywords: List[str]) -> Dict:
        """
        특정 지점의 ABSA 분석
        
        Args:
            df: 리뷰 DataFrame
            branch_id: 지점 번호
            keywords: 해당 지점의 키워드 리스트
        
        Returns:
            카테고리별 집계 결과
        """
        # 해당 지점 리뷰 필터링
        branch_reviews = df[df['지점번호'] == branch_id]
        
        if len(branch_reviews) == 0:
            return {
                'branch_id': branch_id,
                'aspects': {},
                'total_reviews': 0
            }
        
        # 각 리뷰별 ABSA 수행
        all_aspects = []
        for _, row in branch_reviews.iterrows():
            aspects = self.classify_aspect(row['리뷰내용'], keywords)
            all_aspects.append(aspects)
        
        # 카테고리별 집계
        aspect_summary = {}
        for aspects in all_aspects:
            for category, data in aspects.items():
                if category not in aspect_summary:
                    aspect_summary[category] = {
                        'count': 0,
                        'total_score': 0,
                        'avg_score': 0
                    }
                aspect_summary[category]['count'] += 1
                aspect_summary[category]['total_score'] += data['score']
        
        # 평균 계산
        for category in aspect_summary:
            if aspect_summary[category]['count'] > 0:
                aspect_summary[category]['avg_score'] = round(
                    aspect_summary[category]['total_score'] / aspect_summary[category]['count'],
                    2
                )
        
        # 비중 계산 (전체 리뷰 대비 해당 카테고리 언급 비율)
        total_reviews = len(branch_reviews)
        for category in aspect_summary:
            aspect_summary[category]['percentage'] = round(
                aspect_summary[category]['count'] / total_reviews * 100,
                1
            )
        
        return {
            'branch_id': branch_id,
            'aspects': aspect_summary,
            'total_reviews': total_reviews
        }
    
    def analyze_all_branches(self, df: pd.DataFrame, keywords_df: pd.DataFrame) -> pd.DataFrame:
        """
        모든 지점의 ABSA 분석
        
        Args:
            df: 리뷰 DataFrame
            keywords_df: 지점별 키워드 DataFrame (branch_id, keywords 컬럼 포함)
        
        Returns:
            지점별 ABSA 분석 결과 DataFrame
        """
        print("="*80)
        print("📊 ABSA (카테고리별 감정 분석) 시작")
        print("="*80)
        
        results = []
        
        for _, row in keywords_df.iterrows():
            branch_id = row['branch_id']
            keywords = row['keywords'] if isinstance(row['keywords'], list) else []
            
            result = self.classify_aspects_for_branch(df, branch_id, keywords)
            results.append(result)
        
        # 통계
        category_counts = {}
        for result in results:
            for category in result['aspects'].keys():
                category_counts[category] = category_counts.get(category, 0) + 1
        
        self.stats = {
            'total_branches': len(results),
            'category_distribution': category_counts
        }
        
        print(f"\n✅ ABSA 분석 완료")
        print(f"   - 총 지점: {len(results)}개")
        print(f"\n카테고리별 언급 지점 수:")
        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   - {category}: {count}개 지점 ({count/len(results)*100:.1f}%)")
        
        # DataFrame으로 변환 (aspects를 별도 컬럼으로)
        results_df = pd.DataFrame(results)
        
        return results_df
    
    def get_top_aspects_for_branch(self, aspect_result: Dict, top_n: int = 3) -> List[str]:
        """
        특정 지점의 상위 N개 카테고리 반환
        
        Args:
            aspect_result: ABSA 분석 결과
            top_n: 반환할 카테고리 개수
        
        Returns:
            상위 카테고리 리스트
        """
        aspects = aspect_result.get('aspects', {})
        
        # 언급 비율 기준 정렬
        sorted_aspects = sorted(
            aspects.items(),
            key=lambda x: x[1]['percentage'],
            reverse=True
        )
        
        return [category for category, _ in sorted_aspects[:top_n]]


# 실행 예시
if __name__ == '__main__':
    import sys
    sys.path.append('/home/teamo2/Downloads/Review_Summary_AI/src')
    from keyword_extractor import KeywordExtractor
    
    # 데이터 로드
    print("📂 데이터 로드 중...")
    df = pd.read_csv('/home/teamo2/Downloads/Review_Summary_AI/preprocessed_positive_reviews.csv')
    print(f"✅ 로드 완료: {len(df):,}개 리뷰")
    
    # 키워드 추출 (샘플: 상위 10개 지점만)
    print("\n키워드 추출 중...")
    extractor = KeywordExtractor(top_n=5)
    
    top_branches = df['지점번호'].value_counts().head(10).index.tolist()
    keywords_results = []
    
    for branch_id in top_branches:
        result = extractor.extract_keywords_for_branch(df, branch_id, top_n=5)
        keywords_results.append(result)
    
    keywords_df = pd.DataFrame(keywords_results)
    
    # ABSA 분석
    classifier = AspectClassifier()
    absa_results = classifier.analyze_all_branches(df[df['지점번호'].isin(top_branches)], keywords_df)
    
    # 결과 출력
    print("\n" + "="*80)
    print("📊 지점별 ABSA 결과 (샘플)")
    print("="*80)
    
    for _, row in absa_results.head(5).iterrows():
        branch_id = row['branch_id']
        aspects = row['aspects']
        
        print(f"\n지점 {branch_id}:")
        for category, data in sorted(aspects.items(), key=lambda x: x[1]['percentage'], reverse=True):
            print(f"  - {category}: {data['percentage']}% 언급 (평균 점수: {data['avg_score']})")
    
    print("\n" + "🎉 "*40)
    print("ABSA 테스트 완료!")
    print("🎉 "*40)
