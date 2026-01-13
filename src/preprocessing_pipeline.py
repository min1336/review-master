"""
전처리 파이프라인 구현
- CLT 필터링 (n≥30)
- 기본 정제 (빈 리뷰/욕설/블라인드)
- 광고/스팸 필터링 (시맨틱 기반)
- PII 마스킹
- 텍스트 정규화
"""

import pandas as pd
import re
import warnings
from typing import Dict, List, Tuple
from datetime import datetime

warnings.filterwarnings('ignore')


# ============================================================================
# 광고/스팸 탐지 패턴 정의
# ============================================================================

# 광고성 키워드 패턴 (비즈니스 홍보, 연락처 유도)
AD_PATTERNS = [
    # 연락처 유도
    r'연락\s*주세요', r'연락\s*바랍니다', r'문의\s*주세요', r'전화\s*주세요',
    r'카톡\s*주세요', r'카카오톡\s*주세요', r'톡\s*주세요',
    r'방문\s*해\s*주세요', r'방문\s*바랍니다',
    # 가격/할인 홍보
    r'최저가\s*보장', r'특가\s*할인', r'무료\s*제공', r'이벤트\s*진행',
    r'프로모션', r'쿠폰\s*제공', r'적립금\s*지급',
    # 경쟁사 언급/비교
    r'다른\s*업체\s*보다', r'타\s*업체', r'경쟁\s*업체', r'여기\s*말고',
    # 사업 홍보
    r'블로그\s*방문', r'인스타\s*팔로우', r'유튜브\s*구독', r'네이버\s*검색',
    r'홈페이지\s*방문', r'앱\s*다운', r'회원\s*가입',
    # URL 패턴
    r'https?://', r'www\.', r'\.com', r'\.co\.kr', r'\.kr',
]

# 스팸성 패턴 (봇, 무의미한 내용)
SPAM_PATTERNS = [
    # 반복 문자 (5회 이상)
    r'(.)\1{4,}',
    # 반복 단어 (동일 단어 3회 이상 연속)
    r'(\b\w+\b)\s+\1\s+\1',
    # 의미없는 자음/모음 나열
    r'[ㄱ-ㅎㅏ-ㅣ]{5,}',
    # 이모지 과다 (5개 이상 연속)
    r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF]{5,}',
    # 특수문자 과다 (5개 이상 연속)
    r'[!@#$%^&*()_+=\[\]{}|;:,.<>?]{5,}',
]

# 템플릿/일반적 리뷰 패턴 (품질 저하)
TEMPLATE_PATTERNS = [
    # 너무 일반적인 표현
    r'^좋아요\.?$', r'^좋았어요\.?$', r'^굿\.?$', r'^good\.?$',
    r'^괜찮아요\.?$', r'^그냥\s*그래요\.?$', r'^보통이에요\.?$',
    r'^감사합니다\.?$', r'^고맙습니다\.?$',
    r'^별로\.?$', r'^싫어요\.?$', r'^최악\.?$',
    # 단순 별점 언급
    r'^별\s*\d개\.?$', r'^\d점\.?$', r'^만점\.?$',
    # 복사/붙여넣기 의심 (정형화된 문구)
    r'이\s*글은\s*.*을\s*위해', r'솔직한\s*후기입니다',
    r'광고\s*아닙니다', r'순수\s*후기',
]

# 저품질 지표 키워드 (점수 감소용)
LOW_QUALITY_INDICATORS = [
    '그냥', '뭐', '음', '글쎄', '모르겠', '별로',
    '그저그런', '평범', '무난', '딱히', '특별히',
]

# 고품질 지표 키워드 (점수 증가용)
HIGH_QUALITY_INDICATORS = [
    '친절', '깨끗', '청결', '신속', '빠른', '편리', '만족',
    '추천', '재방문', '다음에도', '또', '항상', '최고',
    '직원', '서비스', '차량', '상태', '가격', '위치',
]


class ReviewPreprocessor:
    """리뷰 데이터 전처리 클래스"""
    
    def __init__(self, min_branch_reviews: int = 30, min_review_length: int = 10):
        """
        Args:
            min_branch_reviews: CLT 기준 최소 리뷰 개수
            min_review_length: 최소 리뷰 길이 (자)
        """
        self.min_branch_reviews = min_branch_reviews
        self.min_review_length = min_review_length
        self.stats = {}
        
    def load_data(self, file_path: str) -> pd.DataFrame:
        """
        엑셀 데이터 로드 및 검증
        
        Args:
            file_path: 엑셀 파일 경로
        
        Returns:
            검증된 DataFrame
        """
        print("="*80)
        print("📂 1단계: 데이터 로드")
        print("="*80)
        
        # 데이터 로드
        df = pd.read_excel(file_path)
        
        # 필수 컬럼 검증
        required_columns = [
            '리뷰번호', '지점번호', '리뷰내용', '차량평점',
            '욕설포함여부', '리뷰상태', '등록일시'
        ]
        
        missing = set(required_columns) - set(df.columns)
        if missing:
            raise ValueError(f"필수 컬럼 누락: {missing}")
        
        # 데이터 타입 변환
        df['등록일시'] = pd.to_datetime(df['등록일시'], errors='coerce')
        df['차량평점'] = pd.to_numeric(df['차량평점'], errors='coerce')
        
        self.stats['original_count'] = len(df)
        
        print(f"✅ 데이터 로드 완료: {len(df):,}개 리뷰")
        print(f"   - 컬럼 개수: {len(df.columns)}개")
        print(f"   - 기간: {df['등록일시'].min()} ~ {df['등록일시'].max()}")
        
        return df
    
    def filter_by_clt(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        중심극한정리 기준으로 지점 필터링
        
        Args:
            df: 원본 DataFrame
        
        Returns:
            필터링된 DataFrame
        """
        print(f"\n{'='*80}")
        print("📊 2단계: CLT 필터링 (n ≥ 30)")
        print("="*80)
        
        # 지점별 리뷰 개수 계산
        branch_counts = df['지점번호'].value_counts()
        
        # n≥30 지점만 선택
        valid_branches = branch_counts[branch_counts >= self.min_branch_reviews].index
        df_filtered = df[df['지점번호'].isin(valid_branches)].copy()
        
        # 통계
        excluded = len(df) - len(df_filtered)
        self.stats['clt_filtered_count'] = len(df_filtered)
        self.stats['clt_excluded_count'] = excluded
        self.stats['valid_branches'] = len(valid_branches)
        
        print(f"✅ CLT 필터링 완료")
        print(f"   - 유효 지점: {len(valid_branches):,}개 (30개 이상 리뷰)")
        print(f"   - 남은 리뷰: {len(df_filtered):,}개")
        print(f"   - 제외 리뷰: {excluded:,}개 ({excluded/len(df)*100:.1f}%)")
        
        return df_filtered
    
    def basic_cleanup(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        기본 데이터 정제
        
        제거 대상:
        - 빈 리뷰 (10자 미만)
        - 욕설 포함 리뷰
        - 블라인드/삭제된 리뷰
        
        Args:
            df: 입력 DataFrame
        
        Returns:
            정제된 DataFrame
        """
        print(f"\n{'='*80}")
        print("🧹 3단계: 기본 정제")
        print("="*80)
        
        original_count = len(df)
        
        # 리뷰내용 길이 계산
        df['리뷰길이'] = df['리뷰내용'].fillna('').astype(str).str.len()
        
        # 각 조건별 제외 개수 계산
        empty_count = (df['리뷰길이'] < self.min_review_length).sum()
        profanity_count = (df['욕설포함여부'] == '포함').sum()
        blind_count = (df['리뷰상태'] != '정상').sum()
        
        # 필터링 조건
        conditions = (
            (df['리뷰길이'] >= self.min_review_length) &  # 최소 길이 이상
            (df['욕설포함여부'] != '포함') &  # 욕설 제외
            (df['리뷰상태'] == '정상')  # 정상 리뷰만
        )
        
        df_clean = df[conditions].copy()
        
        # 통계
        removed = original_count - len(df_clean)
        self.stats['cleanup_count'] = len(df_clean)
        self.stats['cleanup_removed'] = removed
        
        print(f"✅ 기본 정제 완료")
        print(f"   - 남은 리뷰: {len(df_clean):,}개")
        print(f"   - 제거 리뷰: {removed:,}개")
        print(f"     ・빈 리뷰 ({self.min_review_length}자 미만): {empty_count:,}개")
        print(f"     ・욕설 포함: {profanity_count:,}개")
        print(f"     ・블라인드/삭제: {blind_count:,}개")

        return df_clean

    def detect_ad_content(self, text: str) -> Tuple[bool, float, List[str]]:
        """
        광고성 콘텐츠 탐지

        Args:
            text: 리뷰 텍스트

        Returns:
            (광고 여부, 광고 점수 0-1, 탐지된 패턴 리스트)
        """
        if pd.isna(text) or not text:
            return False, 0.0, []

        text = str(text).lower()
        detected_patterns = []

        for pattern in AD_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                detected_patterns.append(pattern)

        # 광고 점수 계산 (탐지 패턴 수 기반)
        ad_score = min(len(detected_patterns) / 3.0, 1.0)  # 3개 이상이면 1.0
        is_ad = ad_score >= 0.33  # 1개 이상 탐지시 광고로 판정

        return is_ad, ad_score, detected_patterns

    def detect_spam_content(self, text: str) -> Tuple[bool, float, List[str]]:
        """
        스팸성 콘텐츠 탐지

        Args:
            text: 리뷰 텍스트

        Returns:
            (스팸 여부, 스팸 점수 0-1, 탐지된 패턴 리스트)
        """
        if pd.isna(text) or not text:
            return False, 0.0, []

        text = str(text)
        detected_patterns = []

        for pattern in SPAM_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                detected_patterns.append(pattern)

        # 스팸 점수 계산
        spam_score = min(len(detected_patterns) / 2.0, 1.0)  # 2개 이상이면 1.0
        is_spam = spam_score >= 0.5  # 1개 이상 탐지시 스팸으로 판정

        return is_spam, spam_score, detected_patterns

    def detect_template_review(self, text: str) -> Tuple[bool, float]:
        """
        템플릿/일반적 리뷰 탐지

        Args:
            text: 리뷰 텍스트

        Returns:
            (템플릿 여부, 템플릿 점수 0-1)
        """
        if pd.isna(text) or not text:
            return False, 0.0

        text = str(text).strip()

        for pattern in TEMPLATE_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return True, 1.0

        return False, 0.0

    def calculate_quality_score(self, text: str) -> float:
        """
        리뷰 품질 점수 계산 (0-1)

        높을수록 고품질 리뷰

        Args:
            text: 리뷰 텍스트

        Returns:
            품질 점수 (0-1)
        """
        if pd.isna(text) or not text:
            return 0.0

        text = str(text)
        score = 0.5  # 기본 점수

        # 1. 길이 기반 점수 (20-200자 최적)
        length = len(text)
        if length >= 50:
            score += 0.15
        if length >= 100:
            score += 0.10
        if length < 20:
            score -= 0.2
        if length > 300:
            score -= 0.05  # 너무 긴 것도 약간 감점

        # 2. 고품질 키워드 포함
        high_quality_count = sum(1 for kw in HIGH_QUALITY_INDICATORS if kw in text)
        score += min(high_quality_count * 0.05, 0.2)  # 최대 +0.2

        # 3. 저품질 키워드 포함
        low_quality_count = sum(1 for kw in LOW_QUALITY_INDICATORS if kw in text)
        score -= min(low_quality_count * 0.05, 0.15)  # 최대 -0.15

        # 4. 구체적 내용 여부 (숫자, 고유명사 등)
        if re.search(r'\d+', text):  # 숫자 포함
            score += 0.05
        if re.search(r'[A-Za-z]{3,}', text):  # 영문 단어 (차종 등)
            score += 0.03

        # 점수 범위 제한
        return max(0.0, min(1.0, score))

    def filter_ad_spam(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        광고/스팸 필터링 적용

        Args:
            df: 입력 DataFrame

        Returns:
            필터링된 DataFrame
        """
        print(f"\n{'='*80}")
        print("🛡️ 3.5단계: 광고/스팸 필터링")
        print("="*80)

        original_count = len(df)

        # 각 리뷰에 대해 탐지 수행
        ad_flags = []
        spam_flags = []
        template_flags = []
        quality_scores = []

        for _, row in df.iterrows():
            text = row.get('리뷰내용', '')

            is_ad, _, _ = self.detect_ad_content(text)
            is_spam, _, _ = self.detect_spam_content(text)
            is_template, _ = self.detect_template_review(text)
            quality = self.calculate_quality_score(text)

            ad_flags.append(is_ad)
            spam_flags.append(is_spam)
            template_flags.append(is_template)
            quality_scores.append(quality)

        df['is_ad'] = ad_flags
        df['is_spam'] = spam_flags
        df['is_template'] = template_flags
        df['quality_score'] = quality_scores

        # 통계 수집
        ad_count = sum(ad_flags)
        spam_count = sum(spam_flags)
        template_count = sum(template_flags)

        # 필터링: 광고/스팸은 제거, 템플릿은 가중치만 감소 (제거 안함)
        df_filtered = df[~(df['is_ad'] | df['is_spam'])].copy()

        removed = original_count - len(df_filtered)
        self.stats['ad_count'] = ad_count
        self.stats['spam_count'] = spam_count
        self.stats['template_count'] = template_count
        self.stats['ad_spam_removed'] = removed

        print(f"✅ 광고/스팸 필터링 완료")
        print(f"   - 남은 리뷰: {len(df_filtered):,}개")
        print(f"   - 제거 리뷰: {removed:,}개")
        print(f"     ・광고 탐지: {ad_count:,}개")
        print(f"     ・스팸 탐지: {spam_count:,}개")
        print(f"     ・템플릿 리뷰: {template_count:,}개 (가중치 감소)")
        print(f"   - 평균 품질 점수: {df_filtered['quality_score'].mean():.3f}")

        return df_filtered

    def mask_pii(self, text: str) -> str:
        """
        개인정보 마스킹
        
        Args:
            text: 원본 텍스트
        
        Returns:
            마스킹된 텍스트
        """
        if pd.isna(text) or not text:
            return text
        
        text = str(text)
        
        # 전화번호 (010-xxxx-xxxx, 010xxxxxxxx)
        text = re.sub(r'\d{2,3}[-\s]?\d{3,4}[-\s]?\d{4}', '***-****-****', text)
        
        # 이메일
        text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '***@***.com', text)
        
        # 차량번호 (12가1234)
        text = re.sub(r'\d{2,3}[가-힣]\d{4}', '**가****', text)
        
        return text
    
    def apply_pii_masking(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        전체 데이터에 PII 마스킹 적용
        
        Args:
            df: 입력 DataFrame
        
        Returns:
            PII 마스킹된 DataFrame
        """
        print(f"\n{'='*80}")
        print("🔒 4단계: PII 마스킹")
        print("="*80)
        
        # 원본 백업
        df['리뷰내용_원본'] = df['리뷰내용'].copy()
        
        # 마스킹 적용
        df['리뷰내용'] = df['리뷰내용'].apply(self.mask_pii)
        
        # 마스킹 적용 건수
        masked_count = (df['리뷰내용'] != df['리뷰내용_원본']).sum()
        self.stats['pii_masked_count'] = masked_count
        
        print(f"✅ PII 마스킹 완료")
        print(f"   - 마스킹 적용: {masked_count:,}개 리뷰 ({masked_count/len(df)*100:.1f}%)")
        
        return df
    
    def normalize_text(self, text: str) -> str:
        """
        텍스트 정규화
        
        Args:
            text: 원본 텍스트
        
        Returns:
            정규화된 텍스트
        """
        if pd.isna(text) or not text:
            return text
        
        text = str(text)
        
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', text)
        
        # 연속된 공백 → 단일 공백
        text = re.sub(r'\s+', ' ', text)
        
        # 연속된 특수문자 정리
        text = re.sub(r'!{2,}', '!', text)
        text = re.sub(r'\?{2,}', '?', text)
        text = re.sub(r'\.{2,}', '...', text)
        
        # 연속된 한글 자음/모음 (최대 3개)
        text = re.sub(r'([ㅋㅎㅠㅜ])\1{3,}', r'\1\1\1', text)
        
        # 양쪽 공백 제거
        text = text.strip()
        
        return text
    
    def apply_text_normalization(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        전체 데이터에 텍스트 정규화 적용
        
        Args:
            df: 입력 DataFrame
        
        Returns:
            정규화된 DataFrame
        """
        print(f"\n{'='*80}")
        print("📝 5단계: 텍스트 정규화")
        print("="*80)
        
        df['리뷰내용'] = df['리뷰내용'].apply(self.normalize_text)
        
        print(f"✅ 텍스트 정규화 완료")
        
        return df
    
    def preprocess(self, file_path: str) -> pd.DataFrame:
        """
        전체 전처리 파이프라인 실행
        
        Args:
            file_path: 입력 엑셀 파일 경로
        
        Returns:
            전처리 완료된 DataFrame
        """
        print("\n" + "🚀 "*40)
        print("리뷰 데이터 전처리 파이프라인 시작")
        print("🚀 "*40 + "\n")
        
        # 1. 데이터 로드
        df = self.load_data(file_path)

        # 2. CLT 필터링
        df = self.filter_by_clt(df)

        # 3. 기본 정제
        df = self.basic_cleanup(df)

        # 3.5. 광고/스팸 필터링 (시맨틱 기반)
        df = self.filter_ad_spam(df)

        # 4. PII 마스킹
        df = self.apply_pii_masking(df)

        # 5. 텍스트 정규화
        df = self.apply_text_normalization(df)
        
        # 최종 통계
        print(f"\n{'='*80}")
        print("✅ 전처리 파이프라인 완료")
        print("="*80)
        print(f"최종 데이터: {len(df):,}개 리뷰")
        print(f"원본 대비: {len(df)/self.stats['original_count']*100:.1f}%")
        print(f"제거율: {(1 - len(df)/self.stats['original_count'])*100:.1f}%")
        
        self.stats['final_count'] = len(df)
        
        return df
    
    def save_results(self, df: pd.DataFrame, output_path: str):
        """
        결과 저장
        
        Args:
            df: 전처리된 DataFrame
            output_path: 출력 파일 경로
        """
        print(f"\n💾 결과 저장 중...")
        
        # CSV 저장
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        print(f"✅ 저장 완료: {output_path}")
        print(f"   - 파일 크기: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")


# 실행 예시
if __name__ == '__main__':
    # 전처리 객체 생성
    preprocessor = ReviewPreprocessor(
        min_branch_reviews=30,
        min_review_length=10
    )
    
    # 전처리 실행
    df_clean = preprocessor.preprocess(
        file_path='/home/teamo2/Downloads/Review_Summary_AI/리뷰리스트_20260109.xlsx'
    )
    
    # 결과 저장
    preprocessor.save_results(
        df=df_clean,
        output_path='/home/teamo2/Downloads/Review_Summary_AI/preprocessed_reviews.csv'
    )
    
    print("\n" + "🎉 "*40)
    print("전처리 완료!")
    print("🎉 "*40)
