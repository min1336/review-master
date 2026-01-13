"""
키워드 추출 모듈
- TF-IDF 기반 키워드 추출
- 지점별 상위 키워드 선별
"""

import pandas as pd
from typing import Dict, List
from sklearn.feature_extraction.text import TfidfVectorizer
import warnings

warnings.filterwarnings('ignore')


class KeywordExtractor:
    """키워드 추출 클래스"""
    
    # 불용어 리스트
    STOP_WORDS = [
        '렌트카', '호텔', '예약', '이용', '추천', '정도', '생각',
        '느낌', '그냥', '좀', '약간', '진짜', '정말', '너무', '완전',
        '이번', '다음', '처음', '다시', '계속', '항상', '때문', '위해',
        '통해', '대해', '따라', '같이', '함께', '모두', '전부', '부분'
    ]
    
    # 해시태그 카테고리 매핑
    HASHTAG_MAPPING = {
        "#친절한응대": ["친절", "친절하", "친절한", "친절하게", "친절하시고", "응대", "직원", "안내", "설명", "서비스"],
        "#청결함": ["깨끗", "청결", "깔끔", "깨끗하", "깨끗하고", "세차", "위생", "정리"],
        "#차량상태좋음": ["차량", "상태", "관리", "신차", "차도", "차량도", "컨디션", "새것"],
        "#차량옵션많음": ["전기차", "하이브리드", "옵션", "장착", "기능", "편의"],
        "#가성비": ["저렴", "가성비", "합리적", "경제적", "할인", "프로모션", "이벤트", "혜택"],
        "#셔틀": ["셔틀", "픽업", "송영", "공항", "역", "이동"],
        "#주유가득": ["주유", "가득", "만유", "기름"],
        "#빠른배차및반납": ["빠른", "신속", "간편", "수월", "편리", "빠르", "배차", "반납", "인수", "절차"],
        "#다양한서비스": ["다양", "편의", "서비스", "지원", "도움", "배려"]
    }
    
    @classmethod
    def map_to_hashtags(cls, keywords: List[str]) -> List[str]:
        """
        원문 키워드를 해시태그 카테고리로 매핑
        
        Args:
            keywords: 원문 키워드 리스트
        
        Returns:
            해시태그 리스트
        """
        hashtag_scores = {}
        
        # 각 원문 키워드가 어떤 해시태그에 매칭되는지 확인
        for keyword in keywords:
            for hashtag, patterns in cls.HASHTAG_MAPPING.items():
                # 키워드가 패턴에 포함되는지 확인
                if any(pattern in keyword or keyword in pattern for pattern in patterns):
                    hashtag_scores[hashtag] = hashtag_scores.get(hashtag, 0) + 1
        
        # 점수 기준으로 정렬
        sorted_hashtags = sorted(hashtag_scores.items(), key=lambda x: x[1], reverse=True)
        
        # 상위 해시태그 반환 (최대 5개)
        return [hashtag for hashtag, _ in sorted_hashtags[:5]]
    
    def __init__(self, top_n: int = 10):
        """
        Args:
            top_n: 추출할 키워드 개수
        """
        self.top_n = top_n
        self.stats = {}
        
    def extract_nouns(self, text: str) -> List[str]:
        """
        텍스트에서 명사 추출 (정규식 기반 간단 토큰화)
        
        Args:
            text: 입력 텍스트
        
        Returns:
            명사 리스트
        """
        if pd.isna(text) or not text:
            return []
        
        try:
            import re
            
            # 한글만 추출 (2글자 이상)
            text = str(text)
            korean_pattern = r'[가-힣]{2,}'
            words = re.findall(korean_pattern, text)
            
            # 불용어 제외
            words_filtered = [
                w for w in words 
                if w not in self.STOP_WORDS
            ]
            
            return words_filtered
        except Exception as e:
            print(f"⚠️ 토큰 추출 오류: {e}")
            return []
    
    def extract_keywords_tfidf(self, reviews: List[str], top_n: int = None) -> List[tuple]:
        """
        TF-IDF 기반 키워드 추출
        
        Args:
            reviews: 리뷰 텍스트 리스트
            top_n: 추출할 키워드 개수 (None이면 self.top_n 사용)
        
        Returns:
            (키워드, TF-IDF 점수) 튜플 리스트
        """
        if not reviews:
            return []
        
        top_n = top_n or self.top_n
        
        # 1. 각 리뷰에서 명사 추출
        texts_nouns = []
        for review in reviews:
            nouns = self.extract_nouns(review)
            texts_nouns.append(' '.join(nouns))
        
        # 빈 문서 제거
        texts_nouns = [t for t in texts_nouns if t.strip()]
        
        if not texts_nouns:
            return []
        
        # 2. TF-IDF 계산
        try:
            vectorizer = TfidfVectorizer(
                max_features=top_n * 3,  # 여유있게 추출
                min_df=2,  # 최소 2개 문서에 등장
                max_df=0.8  # 80% 이상 문서에 등장하는 단어 제외
            )
            
            tfidf_matrix = vectorizer.fit_transform(texts_nouns)
            
            # 3. TF-IDF 점수 합산
            feature_names = vectorizer.get_feature_names_out()
            tfidf_scores = tfidf_matrix.sum(axis=0).A1  # 모든 문서의 TF-IDF 합
            
            # 4. 점수 기준 정렬
            keyword_scores = list(zip(feature_names, tfidf_scores))
            keyword_scores.sort(key=lambda x: x[1], reverse=True)
            
            return keyword_scores[:top_n]
        
        except Exception as e:
            print(f"⚠️ TF-IDF 추출 오류: {e}")
            return []
    
    def extract_keywords_for_branch(self, df: pd.DataFrame, branch_id: int, 
                                   top_n: int = None) -> Dict:
        """
        특정 지점의 키워드 추출
        
        Args:
            df: 리뷰 DataFrame
            branch_id: 지점 번호
            top_n: 추출할 키워드 개수
        
        Returns:
            키워드 추출 결과
        """
        top_n = top_n or self.top_n
        
        # 해당 지점 리뷰 필터링
        branch_reviews = df[df['지점번호'] == branch_id]['리뷰내용'].tolist()
        
        if not branch_reviews:
            return {
                'branch_id': branch_id,
                'keywords': [],
                'keyword_count': 0,
                'review_count': 0
            }
        
        # 키워드 추출
        keyword_scores = self.extract_keywords_tfidf(branch_reviews, top_n * 2)  # 더 많이 추출 후 매핑
        
        # 키워드만 추출 (점수 제외)
        raw_keywords = [kw for kw, score in keyword_scores]
        
        # 해시태그로 매핑
        hashtags = self.map_to_hashtags(raw_keywords)
        
        # 해시태그가 부족하면 기본 태그 추가
        if len(hashtags) < 3:
            default_tags = ["#친절한응대", "#청결함", "#차량상태좋음"]
            for tag in default_tags:
                if tag not in hashtags:
                    hashtags.append(tag)
                if len(hashtags) >= 5:
                    break
        
        return {
            'branch_id': branch_id,
            'keywords': hashtags[:5],  # 해시태그 반환
            'raw_keywords': raw_keywords[:10],  # 원문 키워드도 저장
            'keyword_scores': keyword_scores,
            'keyword_count': len(hashtags),
            'review_count': len(branch_reviews)
        }
    
    def extract_keywords_for_all_branches(self, df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
        """
        모든 지점의 키워드 추출
        
        Args:
            df: 리뷰 DataFrame
            top_n: 각 지점별 추출할 키워드 개수
        
        Returns:
            지점별 키워드 DataFrame
        """
        print("="*80)
        print("🔑 키워드 추출 시작")
        print("="*80)
        
        # 지점별 그룹화
        branch_ids = df['지점번호'].unique()
        
        print(f"\n처리 대상: {len(branch_ids)}개 지점")
        
        results = []
        for i, branch_id in enumerate(branch_ids, 1):
            if i % 50 == 0:
                print(f"  처리 중: {i}/{len(branch_ids)} 지점...")
            
            result = self.extract_keywords_for_branch(df, branch_id, top_n)
            results.append(result)
        
        # DataFrame으로 변환
        results_df = pd.DataFrame(results)
        
        # 통계
        self.stats = {
            'total_branches': len(results_df),
            'avg_keywords_per_branch': results_df['keyword_count'].mean(),
            'total_unique_keywords': len(set([kw for keywords in results_df['keywords'] for kw in keywords]))
        }
        
        print(f"\n✅ 키워드 추출 완료")
        print(f"   - 총 지점: {len(results_df)}개")
        print(f"   - 지점당 평균 키워드: {self.stats['avg_keywords_per_branch']:.1f}개")
        print(f"   - 고유 키워드 총 개수: {self.stats['total_unique_keywords']}개")
        
        return results_df
    
    def get_top_keywords_overall(self, df: pd.DataFrame, top_n: int = 20) -> List[tuple]:
        """
        전체 리뷰에서 가장 많이 등장한 키워드
        
        Args:
            df: 리뷰 DataFrame
            top_n: 추출할 키워드 개수
        
        Returns:
            (키워드, 점수) 튜플 리스트
        """
        all_reviews = df['리뷰내용'].tolist()
        return self.extract_keywords_tfidf(all_reviews, top_n)


# 실행 예시
if __name__ == '__main__':
    # 테스트 데이터 로드
    print("📂 데이터 로드 중...")
    df = pd.read_csv('/home/teamo2/Downloads/Review_Summary_AI/preprocessed_positive_reviews.csv')
    print(f"✅ 로드 완료: {len(df):,}개 리뷰")
    
    # 키워드 추출기 생성
    extractor = KeywordExtractor(top_n=5)
    
    # 1. 전체 키워드 추출
    print("\n" + "="*80)
    print("🌐 전체 리뷰 키워드 (상위 20개)")
    print("="*80)
    
    top_keywords = extractor.get_top_keywords_overall(df, top_n=20)
    for i, (keyword, score) in enumerate(top_keywords, 1):
        print(f"{i:2d}. {keyword:10s} (점수: {score:.2f})")
    
    # 2. 지점별 키워드 추출 (샘플: 상위 10개 지점만)
    print("\n" + "="*80)
    print("🏢 지점별 키워드 추출 (샘플: 상위 10개 지점)")
    print("="*80)
    
    # 리뷰 많은 순으로 정렬
    top_branches = df['지점번호'].value_counts().head(10).index.tolist()
    
    for branch_id in top_branches:
        result = extractor.extract_keywords_for_branch(df, branch_id, top_n=5)
        print(f"\n지점 {branch_id} ({result['review_count']}개 리뷰):")
        print(f"  키워드: {', '.join(result['keywords'])}")
    
    print("\n" + "🎉 "*40)
    print("키워드 추출 테스트 완료!")
    print("🎉 "*40)
