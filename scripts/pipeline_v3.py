"""
리뷰 요약 파이프라인 v3
실행: python pipeline_v3.py
"""

import pandas as pd
import os
import sys
import time
from typing import List, Dict
from datetime import datetime
from collections import Counter
import warnings

warnings.filterwarnings('ignore')

# src 모듈 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.llm.prompts import PromptTemplates
from src.llm.validator import validate_summary


# ============================================================================
# Rate Limiter 클래스
# ============================================================================
class RateLimiter:
    """
    분당 요청 수(RPM) 제한을 위한 Rate Limiter

    Gemini 1.5 Flash 무료 티어: 15 RPM
    안전 마진을 두고 12 RPM으로 설정
    """

    def __init__(self, rpm: int = 12):
        self.rpm = rpm
        self.min_interval = 60.0 / rpm
        self.last_request_time = 0
        self.request_count = 0
        self.window_start = time.time()

    def wait_if_needed(self):
        """필요시 대기하여 Rate Limit 준수"""
        current_time = time.time()

        # 1분 윈도우 리셋
        if current_time - self.window_start >= 60:
            self.window_start = current_time
            self.request_count = 0

        # 분당 요청 수 초과 시 대기
        if self.request_count >= self.rpm:
            wait_time = 60 - (current_time - self.window_start)
            if wait_time > 0:
                print(f"  ⏳ Rate limit 도달, {wait_time:.1f}초 대기...")
                time.sleep(wait_time)
                self.window_start = time.time()
                self.request_count = 0

        # 요청 간 최소 간격 유지
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        self.last_request_time = time.time()
        self.request_count += 1

# .env 파일 로드 (python-dotenv)
try:
    from dotenv import load_dotenv
    from pathlib import Path
    # 프로젝트 루트의 .env 파일 로드
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(env_path)
except ImportError:
    pass

# Supabase 연동
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'web'))
try:
    from supabase_client import upsert_summaries_batch, upsert_sentiment_stats, upsert_recent_reviews
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# MeCab
try:
    import mecab
    MECAB_AVAILABLE = True
except ImportError:
    MECAB_AVAILABLE = False

# OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Gemini
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Transformers (딥러닝 감정분석)
try:
    from transformers import pipeline as hf_pipeline
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False


class ReviewPipeline:
    """
    9단계 리뷰 분석 파이프라인 v3.2

    [1] 리뷰 로드 (21만개)
    [2] 빈 리뷰 제거 (5자 미만)
    [3] 블라인드/삭제 제거 + 30개 이하 지점 삭제
    [4] 2단계 감정 분석 (1차: Lexicon → 2차: BERT 애매한 경우만)
    [5] 긍정 리뷰 필터링 (score >= 0.45)
    [6] 리뷰당 키워드 추출 (명사 + 형용사)
    [7] 지점별 키워드 엑셀 출력 (가중치 적용)
    [8] AI 요약 생성 (TOP 10 키워드 + 대표 리뷰 5개)
    [9] LLM: OpenAI GPT-4o-mini (Rate Limited 500 RPM)
    """

    # 불용어
    STOP_WORDS = {
        '렌트카', '호텔', '예약', '이용', '추천', '정도', '생각',
        '느낌', '그냥', '좀', '약간', '진짜', '정말', '너무', '완전',
        '이번', '다음', '처음', '다시', '계속', '항상', '때문', '위해',
        '것', '수', '등', '중', '내', '더', '안', '잘', '곳', '거',
        '분', '점', '때', '후', '전', '번', '개', '회', '데', '말',
        '사용', '경우', '사람', '시간', '정보', '방법', '상황',
        '여행', '출장', '경험', '기대', '방문', '오늘', '어제',
        '네', '예', '응', '음', '아', '오', '저', '제', '이', '그'
    }

    # 부정 키워드 패턴
    NEGATIVE_PATTERNS = [
        '불친절', '불편', '더럽', '지저분', '늦었', '느리', '비싸',
        '불만', '실망', '아쉽', '부족', '고장', '문제', '별로', '최악',
        '짜증', '화나', '열받', '싫', '안좋', '나빠', '후회', '환불'
    ]

    # 감정 어휘 사전 (MeCab 분석용)
    POSITIVE_WORDS = {
        '좋다', '좋아', '좋은', '좋았', '최고', '만족', '편리', '친절', '깨끗',
        '빠르다', '빠른', '신속', '감사', '추천', '굿', '훌륭', '완벽', '대박',
        '짱', '쾌적', '편하다', '편한', '넓다', '넓은', '저렴', '합리적'
    }

    NEGATIVE_WORDS = {
        '불친절', '불편', '더럽다', '더러운', '지저분', '느리다', '느린', '늦다',
        '비싸다', '비싼', '불만', '실망', '아쉽다', '아쉬운', '부족', '고장',
        '문제', '별로', '최악', '짜증', '화나다', '싫다', '후회', '환불'
    }

    def __init__(self, min_reviews: int = 30, use_deep_learning: bool = True):
        self.min_reviews = min_reviews
        self.use_deep_learning = use_deep_learning
        self.stats = {}

        # MeCab 초기화
        if MECAB_AVAILABLE:
            self.mecab = mecab.MeCab()
            print("✅ MeCab 초기화 완료")
        else:
            self.mecab = None
            print("⚠️ MeCab 미설치 - 정규식 폴백 사용")

        # 딥러닝 감정분석 모델 초기화
        self.sentiment_pipeline = None
        if use_deep_learning and TRANSFORMERS_AVAILABLE:
            try:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                print(f"🤖 딥러닝 감정분석 모델 로딩 중... (장치: {device})")
                self.sentiment_pipeline = hf_pipeline(
                    "sentiment-analysis",
                    model="nlptown/bert-base-multilingual-uncased-sentiment",
                    device=0 if device == "cuda" else -1,
                    truncation=True,
                    max_length=512
                )
                print("✅ 딥러닝 감정분석 모델 로딩 완료")
            except Exception as e:
                print(f"⚠️ 딥러닝 모델 로딩 실패: {e}")
                self.use_deep_learning = False
        elif use_deep_learning:
            print("⚠️ transformers/torch 미설치 - 사전 기반 분석 사용")
            self.use_deep_learning = False

        # LLM Provider 설정
        self.llm_provider = os.getenv('LLM_PROVIDER', 'gemini').lower()

        # Gemini 초기화 (기본값)
        self.gemini_model = None
        if self.llm_provider == 'gemini' and GEMINI_AVAILABLE:
            api_key = os.getenv('GEMINI_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
                self.rate_limiter = RateLimiter(rpm=1000)  # Gemini: 1000 RPM
                print(f"✅ Gemini 2.5 Flash 초기화 완료 (Rate Limit: 1000 RPM)")
            else:
                print("⚠️ GEMINI_API_KEY 환경변수 필요")

        # OpenAI 초기화
        self.openai_client = None
        self.openai_model = "gpt-3.5-turbo"
        if self.llm_provider == 'openai' and OPENAI_AVAILABLE:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.openai_client = OpenAI(
                    api_key=api_key,
                    organization=os.getenv('OPENAI_ORG_ID'),
                    project=os.getenv('OPENAI_PROJECT_ID')
                )
                self.rate_limiter = RateLimiter(rpm=3500)  # GPT-3.5-turbo: 3500 RPM
                print(f"✅ OpenAI {self.openai_model} 초기화 완료 (Rate Limit: 3500 RPM)")
            else:
                print("⚠️ OPENAI_API_KEY 환경변수 필요")

        if not self.gemini_model and not self.openai_client:
            self.rate_limiter = RateLimiter(rpm=60)
            print("⚠️ LLM 미설정 - 기본 요약 사용")

    # =========================================================================
    # Step 1: 데이터 로드
    # =========================================================================
    def load_data(self, file_path: str) -> pd.DataFrame:
        print("\n" + "="*60)
        print("[Step 1] 데이터 로드")
        print("="*60)

        df = pd.read_excel(file_path)
        self.stats['total_reviews'] = len(df)
        print(f"✅ {len(df):,}개 리뷰 로드 완료")
        return df

    # =========================================================================
    # Step 2: 빈 리뷰 제거
    # =========================================================================
    def remove_empty_reviews(self, df: pd.DataFrame) -> pd.DataFrame:
        print("\n" + "="*60)
        print("[Step 2] 빈 리뷰 제거")
        print("="*60)

        before = len(df)

        # null 제거
        df = df[df['리뷰내용'].notna()]

        # 빈 문자열 제거
        df = df[df['리뷰내용'].str.strip() != '']

        # 5자 미만 제거
        df = df[df['리뷰내용'].str.len() >= 5]

        removed = before - len(df)
        self.stats['empty_removed'] = removed
        print(f"✅ {removed:,}개 제거 → {len(df):,}개 남음")
        return df

    # =========================================================================
    # Step 3: 블라인드/삭제 제거 + 지점 필터링
    # =========================================================================
    def filter_reviews_and_branches(self, df: pd.DataFrame) -> pd.DataFrame:
        print("\n" + "="*60)
        print("[Step 3] 블라인드/삭제 제거 + 지점 필터링")
        print("="*60)

        before = len(df)

        # 블라인드/삭제 제거
        df = df[~df['리뷰상태'].isin(['블라인드', '삭제'])]
        status_removed = before - len(df)
        print(f"   블라인드/삭제 {status_removed:,}개 제거")

        # 30개 이하 지점 제거
        branch_counts = df.groupby('지점번호').size()
        valid_branches = branch_counts[branch_counts > self.min_reviews].index
        df = df[df['지점번호'].isin(valid_branches)]

        self.stats['valid_branches'] = len(valid_branches)
        self.stats['filtered_reviews'] = len(df)
        print(f"✅ {len(valid_branches)}개 지점, {len(df):,}개 리뷰 남음")
        return df

    # =========================================================================
    # Step 4: 리뷰당 키워드 추출 (명사 + 형용사)
    # =========================================================================
    def extract_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        print("\n" + "="*60)
        print("[Step 4] 리뷰당 키워드 추출 (명사 + 형용사)")
        print("="*60)

        df = df.copy()
        df['keywords'] = df['리뷰내용'].apply(self._extract_keywords_mecab)

        total_keywords = df['keywords'].apply(len).sum()
        self.stats['total_keywords'] = total_keywords
        print(f"✅ 총 {total_keywords:,}개 키워드 추출")
        return df

    def _extract_keywords_mecab(self, text: str) -> List[str]:
        """텍스트에서 명사 + 형용사 추출"""
        if not text or not isinstance(text, str):
            return []

        if self.mecab:
            try:
                keywords = []
                for token in self.mecab.parse(text):
                    pos = token.pos
                    word = token.surface
                    # 명사(NNG, NNP) + 형용사(VA)
                    if pos.startswith('NNG') or pos.startswith('NNP') or pos.startswith('VA'):
                        if len(word) >= 2 and word not in self.STOP_WORDS:
                            keywords.append(word)
                return keywords
            except:
                pass

        # 정규식 폴백
        import re
        words = re.findall(r'[가-힣]{2,}', text)
        return [w for w in words if w not in self.STOP_WORDS]

    # =========================================================================
    # Step 4: 2단계 하이브리드 감정 분석 (Lexicon → BERT)
    # =========================================================================
    def analyze_sentiment(self, df: pd.DataFrame) -> pd.DataFrame:
        print("\n" + "="*60)
        print("[Step 4] 2단계 하이브리드 감정 분석")
        print("="*60)
        print(f"   1차: Lexicon (빠름) → 2차: BERT (애매한 경우만)")

        df = df.copy()
        total = len(df)

        sentiment_results = []
        bert_count = 0

        for i, (idx, row) in enumerate(df.iterrows()):
            if (i + 1) % 1000 == 0:
                print(f"   처리 중: {i+1:,}/{total:,} ({(i+1)/total*100:.1f}%) [BERT 호출: {bert_count}회]")

            text = str(row.get('리뷰내용', ''))

            # 2단계 하이브리드 감정 분석
            result, used_bert = self._analyze_sentiment_two_stage(text)
            if used_bert:
                bert_count += 1
            sentiment_results.append(result)

        # 결과 추가
        df['sentiment'] = [r['sentiment'] for r in sentiment_results]
        df['sentiment_score'] = [r['score'] for r in sentiment_results]

        # 통계
        sentiment_counts = df['sentiment'].value_counts()
        self.stats['sentiment'] = {
            'positive': int(sentiment_counts.get('positive', 0)),
            'neutral': int(sentiment_counts.get('neutral', 0)),
            'negative': int(sentiment_counts.get('negative', 0))
        }
        self.stats['bert_calls'] = bert_count

        print(f"\n✅ 감정 분석 완료")
        print(f"   - 긍정: {self.stats['sentiment']['positive']:,}개 ({self.stats['sentiment']['positive']/total*100:.1f}%)")
        print(f"   - 중립: {self.stats['sentiment']['neutral']:,}개 ({self.stats['sentiment']['neutral']/total*100:.1f}%)")
        print(f"   - 부정: {self.stats['sentiment']['negative']:,}개 ({self.stats['sentiment']['negative']/total*100:.1f}%)")
        print(f"   - BERT 호출: {bert_count:,}회 ({bert_count/total*100:.1f}%)")

        return df

    def _analyze_sentiment_two_stage(self, text: str) -> tuple:
        """
        2단계 하이브리드 감정 분석
        1차: Lexicon (빠름) - 확실한 경우 바로 결정
        2차: BERT (정밀) - 애매한 경우만 처리

        Returns: (result_dict, used_bert)
        """
        # 텍스트가 없으면 중립
        if not text or not text.strip():
            return {'sentiment': 'neutral', 'score': 0.5}, False

        # 1차: Lexicon 기반 빠른 분류
        lexicon_score = self._calculate_lexicon_score(text)

        # 확실한 긍정 (score >= 0.7)
        if lexicon_score >= 0.7:
            return {'sentiment': 'positive', 'score': round(lexicon_score, 3)}, False

        # 확실한 부정 (score <= 0.3)
        if lexicon_score <= 0.3:
            return {'sentiment': 'negative', 'score': round(lexicon_score, 3)}, False

        # 2차: 애매한 구간 (0.3 < score < 0.7) → BERT로 정밀 분석
        if self.use_deep_learning and self.sentiment_pipeline:
            bert_score = self._predict_sentiment_dl(text)

            # BERT 결과로 최종 판단
            if bert_score >= 0.6:
                sentiment = 'positive'
            elif bert_score >= 0.4:
                sentiment = 'neutral'
            else:
                sentiment = 'negative'

            return {'sentiment': sentiment, 'score': round(bert_score, 3)}, True

        # BERT 사용 불가 시 Lexicon으로 결정
        if lexicon_score >= 0.5:
            sentiment = 'neutral'  # 애매하면 중립
        else:
            sentiment = 'negative'

        return {'sentiment': sentiment, 'score': round(lexicon_score, 3)}, False

    def _predict_sentiment_dl(self, text: str) -> float:
        """딥러닝 감정 예측 (0~1 점수)"""
        try:
            text = text[:500] if len(text) > 500 else text
            result = self.sentiment_pipeline(text)[0]
            label = result['label']

            # nlptown 모델: "1 star" ~ "5 stars"
            if 'star' in label.lower():
                stars = int(label.split()[0])
                return (stars - 1) / 4  # 0~1
            return 0.5
        except:
            return 0.5

    def _calculate_lexicon_score(self, text: str) -> float:
        """사전 기반 감정 점수 (0~1)"""
        if not text:
            return 0.5

        pos_count = sum(1 for w in self.POSITIVE_WORDS if w in text)
        neg_count = sum(1 for w in self.NEGATIVE_WORDS if w in text)
        total = pos_count + neg_count

        if total == 0:
            return 0.5

        # -1~1 → 0~1 변환
        raw_score = (pos_count - neg_count) / total
        return (raw_score + 1) / 2

    # =========================================================================
    # Step 5: 감정분석 통계 (필터링 없음)
    # =========================================================================
    def filter_positive_reviews(self, df: pd.DataFrame, min_score: float = 0.45) -> pd.DataFrame:
        print("\n" + "="*60)
        print("[Step 5] 감정분석 통계 (필터링 없음)")
        print("="*60)

        # 모든 리뷰 유지 (필터링 없음)
        df_filtered = df.copy()

        positive_count = len(df_filtered[df_filtered['sentiment'] == 'positive'])
        negative_count = len(df_filtered[df_filtered['sentiment'] == 'negative'])
        neutral_count = len(df_filtered[df_filtered['sentiment'] == 'neutral'])

        self.stats['positive_filtered'] = positive_count
        self.stats['negative_filtered'] = negative_count
        self.stats['neutral_filtered'] = neutral_count

        print(f"✅ {len(df_filtered):,}개 리뷰 (필터링 없음)")
        print(f"   - 긍정: {positive_count:,}개 ({positive_count/len(df_filtered)*100:.1f}%)")
        print(f"   - 부정: {negative_count:,}개 ({negative_count/len(df_filtered)*100:.1f}%)")
        print(f"   - 중립: {neutral_count:,}개 ({neutral_count/len(df_filtered)*100:.1f}%)")

        return df_filtered

    # =========================================================================
    # (레거시) 부정 키워드 삭제 - 감정분석으로 대체됨
    # =========================================================================
    def remove_negative_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        """레거시: 단순 패턴 매칭 기반 부정 리뷰 필터링"""
        print("\n" + "="*60)
        print("[Step 5-Legacy] 부정 키워드 삭제")
        print("="*60)

        df = df.copy()

        def is_negative(text: str) -> bool:
            if not text:
                return False
            text_lower = text.lower()
            return any(pattern in text_lower for pattern in self.NEGATIVE_PATTERNS)

        # 부정 리뷰 식별
        df['is_negative'] = df['리뷰내용'].apply(is_negative)
        negative_count = df['is_negative'].sum()

        # 부정 리뷰의 키워드 제거
        df.loc[df['is_negative'], 'keywords'] = df.loc[df['is_negative'], 'keywords'].apply(lambda x: [])

        self.stats['negative_reviews'] = negative_count
        print(f"✅ 부정 리뷰 {negative_count:,}개의 키워드 제거")
        return df

    # =========================================================================
    # Step 6: 지점별 키워드 집계 + 엑셀 출력 (가중치 적용)
    # =========================================================================
    def aggregate_branch_keywords(self, df: pd.DataFrame, use_weights: bool = True) -> pd.DataFrame:
        print("\n" + "="*60)
        print("[Step 6] 지점별 키워드 집계" + (" (가중치 적용)" if use_weights else ""))
        print("="*60)

        # 가중치 계산기 임포트
        weight_calculator = None
        if use_weights:
            try:
                from scripts.weight_calculator import WeightCalculator
                weight_calculator = WeightCalculator()
                print("   가중치 계산기 로드됨")
            except ImportError:
                print("   ⚠️ 가중치 계산기 없음 - 단순 빈도 사용")
                use_weights = False

        results = []
        weighted_keywords_data = []  # DB 저장용

        for branch_id in df['지점번호'].unique():
            branch_df = df[df['지점번호'] == branch_id]

            if use_weights and weight_calculator:
                # 가중치 기반 키워드 집계
                keyword_scores = {}  # {keyword: weighted_score}
                keyword_counts = {}  # {keyword: raw_count}

                for _, row in branch_df.iterrows():
                    keywords = row.get('keywords', [])
                    if not keywords:
                        continue

                    # 리뷰별 가중치 계산
                    weight = weight_calculator.calculate_from_dataframe_row(row)

                    for kw in keywords:
                        keyword_scores[kw] = keyword_scores.get(kw, 0) + weight
                        keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

                # 가중치 점수로 정렬
                sorted_keywords = sorted(
                    keyword_scores.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                top10 = [kw for kw, _ in sorted_keywords[:10]]

                # DB 저장용 데이터
                for kw, score in sorted_keywords:
                    weighted_keywords_data.append({
                        'branch_id': branch_id,
                        'keyword': kw,
                        'raw_count': keyword_counts.get(kw, 0),
                        'weighted_score': round(score, 2)
                    })
            else:
                # 단순 빈도 기반 (기존 로직)
                all_keywords = []
                for keywords in branch_df['keywords']:
                    all_keywords.extend(keywords)

                keyword_counts = Counter(all_keywords)
                top10 = [kw for kw, _ in keyword_counts.most_common(10)]

            results.append({
                'branch_id': branch_id,
                'review_count': len(branch_df),
                'keywords': top10
            })

        keywords_df = pd.DataFrame(results)
        print(f"✅ {len(keywords_df)}개 지점 키워드 집계 완료")

        # 가중치 데이터 저장 (Supabase)
        if weighted_keywords_data:
            self._save_weighted_keywords_to_db(weighted_keywords_data)

        return keywords_df

    def _save_weighted_keywords_to_db(self, keywords_data: List[Dict]):
        """가중치 키워드를 DB에 저장"""
        try:
            from supabase_client import get_client
            client = get_client()

            # 배치로 upsert
            batch_size = 100
            saved = 0
            for i in range(0, len(keywords_data), batch_size):
                batch = keywords_data[i:i+batch_size]
                client.table('branch_keywords').upsert(
                    batch,
                    on_conflict='branch_id,keyword'
                ).execute()
                saved += len(batch)

            print(f"   💾 branch_keywords 테이블에 {saved}개 키워드 저장됨")
        except Exception as e:
            print(f"   ⚠️ 키워드 DB 저장 실패: {e}")

    def export_keywords_excel(self, keywords_df: pd.DataFrame, output_dir: str):
        """지점별 키워드 엑셀 출력"""
        os.makedirs(output_dir, exist_ok=True)

        # 키워드 엑셀 (상위 10개)
        rows = []
        for _, row in keywords_df.iterrows():
            kw = row['keywords']
            rows.append({
                '지점번호': row['branch_id'],
                '리뷰수': row['review_count'],
                '키워드1': kw[0] if len(kw) > 0 else '',
                '키워드2': kw[1] if len(kw) > 1 else '',
                '키워드3': kw[2] if len(kw) > 2 else '',
                '키워드4': kw[3] if len(kw) > 3 else '',
                '키워드5': kw[4] if len(kw) > 4 else '',
                '키워드6': kw[5] if len(kw) > 5 else '',
                '키워드7': kw[6] if len(kw) > 6 else '',
                '키워드8': kw[7] if len(kw) > 7 else '',
                '키워드9': kw[8] if len(kw) > 8 else '',
                '키워드10': kw[9] if len(kw) > 9 else '',
            })

        path = os.path.join(output_dir, 'branch_keywords.xlsx')
        pd.DataFrame(rows).to_excel(path, index=False)
        print(f"✅ {path}")
        return path

    # =========================================================================
    # Step 7: 요약 생성 + TOP 3 키워드 엑셀
    # =========================================================================
    def generate_summaries_and_top3(self, keywords_df: pd.DataFrame, reviews_df: pd.DataFrame, output_dir: str):
        """
        요약 생성 (TOP 10 키워드 + 대표 리뷰 5개 기반)

        Args:
            keywords_df: 지점별 키워드 집계 결과
            reviews_df: 긍정 리뷰 원본 DataFrame
            output_dir: 출력 디렉토리
        """
        print("\n" + "="*60)
        print("[Step 7] 요약 생성 + TOP 3 키워드 엑셀")
        print("   (TOP 10 키워드 + 대표 리뷰 5개 기반)")
        print("="*60)

        os.makedirs(output_dir, exist_ok=True)

        top3_rows = []
        summary_rows = []
        total = len(keywords_df)

        for i, (_, row) in enumerate(keywords_df.iterrows(), 1):
            if i % 50 == 0:
                print(f"   {i}/{total} 처리 중...")

            branch_id = row['branch_id']
            keywords = row['keywords']
            review_count = row['review_count']

            # 지점명 가져오기 (reviews_df에서)
            branch_name = None
            if '지점명' in reviews_df.columns:
                branch_rows = reviews_df[reviews_df['지점번호'] == branch_id]['지점명']
                if not branch_rows.empty:
                    branch_name = str(branch_rows.iloc[0])

            # TOP 3 키워드
            top3_rows.append({
                '지점번호': branch_id,
                '1위': keywords[0] if len(keywords) > 0 else '',
                '2위': keywords[1] if len(keywords) > 1 else '',
                '3위': keywords[2] if len(keywords) > 2 else '',
            })

            # 대표 리뷰 5개 추출
            representative_reviews = self._get_representative_reviews(
                reviews_df, branch_id, keywords[:10]
            )

            # AI 요약 생성 (v2: 지점명 전달)
            summary = self._generate_summary(keywords, review_count, representative_reviews, branch_name)
            summary_rows.append({
                '지점번호': branch_id,
                '리뷰수': review_count,
                'TOP3키워드': ', '.join(keywords[:3]),
                'AI요약': summary
            })

        # TOP 3 엑셀 저장
        top3_path = os.path.join(output_dir, 'branch_top3_keywords.xlsx')
        pd.DataFrame(top3_rows).to_excel(top3_path, index=False)
        print(f"✅ {top3_path}")

        # 요약 엑셀 저장
        summary_path = os.path.join(output_dir, 'branch_summaries.xlsx')
        pd.DataFrame(summary_rows).to_excel(summary_path, index=False)
        print(f"✅ {summary_path}")

        # Supabase용 데이터 변환
        supabase_data = []
        for row in summary_rows:
            keywords = row['TOP3키워드'].split(', ') if row['TOP3키워드'] else []
            supabase_data.append({
                'branch_id': row['지점번호'],
                'ai_summary': row['AI요약'],
                'keywords': keywords,
                'review_count': row['리뷰수']
            })

        return top3_path, summary_path, supabase_data

    def _get_representative_reviews(self, df: pd.DataFrame, branch_id: int, keywords: List[str]) -> List[str]:
        """
        지점별 대표 리뷰 추출 (긍정 3개 + 부정 2개 = 5개)
        - 키워드를 많이 포함한 리뷰 우선
        """
        branch_df = df[df['지점번호'] == branch_id].copy()

        if branch_df.empty:
            return []

        # 키워드 포함 횟수 계산
        def count_keywords(text):
            if not isinstance(text, str):
                return 0
            return sum(1 for kw in keywords if kw in text)

        branch_df['kw_count'] = branch_df['리뷰내용'].apply(count_keywords)

        # 긍정 리뷰 3개 선택
        positive_df = branch_df[branch_df['sentiment'] == 'positive']
        positive_reviews = positive_df.nlargest(3, 'kw_count')['리뷰내용'].tolist() if not positive_df.empty else []

        # 부정 리뷰 2개 선택
        negative_df = branch_df[branch_df['sentiment'] == 'negative']
        negative_reviews = negative_df.nlargest(2, 'kw_count')['리뷰내용'].tolist() if not negative_df.empty else []

        # 합치기 (긍정 먼저, 부정 나중)
        all_reviews = positive_reviews + negative_reviews

        # 리뷰 길이 제한 (각 100자)
        return [str(r)[:100] for r in all_reviews if r]

    def _generate_summary(
        self,
        keywords: List[str],
        review_count: int,
        representative_reviews: List[str],
        branch_name: str = None
    ) -> str:
        """
        LLM으로 요약 생성 (v2: PromptTemplates 사용 + 검증)

        Args:
            keywords: 키워드 리스트
            review_count: 리뷰 수
            representative_reviews: 대표 리뷰 리스트
            branch_name: 지점명 (유형 판별용)
        """
        if not keywords:
            return PromptTemplates.get_default_summary(keywords)

        # 프롬프트 생성 (v2: 구조화 + 지점 유형별)
        system_prompt, user_prompt = PromptTemplates.build_summary_prompt(
            keywords=keywords,
            review_count=review_count,
            representative_reviews=representative_reviews,
            branch_name=branch_name
        )

        try:
            # Rate Limit 대기
            self.rate_limiter.wait_if_needed()

            result = None

            # Gemini 사용
            if self.gemini_model:
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                response = self.gemini_model.generate_content(full_prompt)
                result = response.text.strip()

            # OpenAI 사용
            elif self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model=self.openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=300,
                    temperature=0.5  # 일관성 향상을 위해 낮춤
                )
                result = response.choices[0].message.content.strip()

            else:
                return PromptTemplates.get_default_summary(keywords)

            # 문장이 잘렸으면 마침표 추가
            if result and not result.endswith(('.', '!', '?', '다', '요', '"')):
                result += '.'

            # 검증
            is_valid, errors = validate_summary(result)
            if not is_valid:
                print(f"   ⚠️ [{branch_name or '지점'}] 검증 경고: {'; '.join(errors)}")

            return result

        except Exception as e:
            # Rate limit 에러 시 추가 대기 후 재시도
            if '429' in str(e) or 'rate' in str(e).lower() or 'quota' in str(e).lower():
                print(f"  ⏳ Rate limit 초과, 60초 대기 후 재시도...")
                time.sleep(60)
                try:
                    if self.gemini_model:
                        full_prompt = f"{system_prompt}\n\n{user_prompt}"
                        response = self.gemini_model.generate_content(full_prompt)
                        result = response.text.strip()
                    elif self.openai_client:
                        response = self.openai_client.chat.completions.create(
                            model=self.openai_model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}
                            ],
                            max_tokens=300,
                            temperature=0.5
                        )
                        result = response.choices[0].message.content.strip()
                    if result and not result.endswith(('.', '!', '?', '다', '요', '"')):
                        result += '.'
                    return result
                except:
                    pass
            print(f"⚠️ LLM API 오류: {e}")
            return PromptTemplates.get_default_summary(keywords)

    # =========================================================================
    # 메인 실행
    # =========================================================================
    def run(self, input_file: str, output_dir: str = 'output'):
        start = datetime.now()

        print("\n" + "="*60)
        print("🚀 리뷰 요약 파이프라인 v3.2 시작")
        print("   2단계 감정분석 (Lexicon→BERT) + OpenAI GPT-4o-mini")
        print("="*60)

        # Step 1-3: 데이터 로드 및 기본 필터링
        df = self.load_data(input_file)
        df = self.remove_empty_reviews(df)
        df = self.filter_reviews_and_branches(df)

        # Step 4: 감정 분석 (MeCab + 딥러닝 하이브리드)
        df = self.analyze_sentiment(df)

        # Step 5: 긍정 리뷰 필터링
        df_positive = self.filter_positive_reviews(df)

        # Step 6: 키워드 추출 (긍정 리뷰만)
        df_positive = self.extract_keywords(df_positive)

        # Step 7: 지점별 키워드 집계
        keywords_df = self.aggregate_branch_keywords(df_positive)
        self.export_keywords_excel(keywords_df, output_dir)

        # Step 8: 요약 생성 (키워드 + 대표 리뷰 기반)
        _, _, supabase_data = self.generate_summaries_and_top3(keywords_df, df_positive, output_dir)

        # Step 9: Supabase 저장
        if SUPABASE_AVAILABLE:
            print("\n" + "="*60)
            print("[Step 9] Supabase 저장")
            print("="*60)

            # 9-1: 요약 저장
            saved = upsert_summaries_batch(supabase_data)
            print(f"✅ 요약 저장 완료: {saved}개 지점")
            self.stats['supabase_saved'] = saved

            # 9-2: 지점별 감정통계 저장
            print("\n[Step 9-2] 감정통계 저장")
            sentiment_stats = df.groupby('지점번호')['sentiment'].value_counts().unstack(fill_value=0)
            stats_data = []
            for branch_id in sentiment_stats.index:
                row = sentiment_stats.loc[branch_id]
                stats_data.append({
                    'branch_id': int(branch_id),
                    'positive_count': int(row.get('positive', 0)),
                    'negative_count': int(row.get('negative', 0)),
                    'neutral_count': int(row.get('neutral', 0))
                })
            stats_saved = upsert_sentiment_stats(stats_data)
            print(f"✅ 감정통계 저장 완료: {stats_saved}개 지점")
            self.stats['stats_saved'] = stats_saved

            # 9-3: 최근 리뷰만 저장 (최근 1개월 = 샘플 용도)
            # 지점당 최근 10개씩만 저장 (디버깅/샘플용)
            print("\n[Step 9-3] 최근 리뷰 샘플 저장")
            recent_reviews = []
            for branch_id in df['지점번호'].unique():
                branch_df = df[df['지점번호'] == branch_id].tail(10)  # 지점당 최근 10개
                recent_reviews.extend(branch_df[['지점번호', '리뷰내용', 'sentiment', 'sentiment_score']].to_dict('records'))

            if recent_reviews:
                reviews_saved = upsert_recent_reviews(recent_reviews)
                print(f"✅ 최근 리뷰 저장 완료: {reviews_saved}개 (지점당 최대 10개)")
                self.stats['reviews_saved'] = reviews_saved
        else:
            print("\n⚠️ Supabase 미설정 - DB 저장 건너뜀")

        # 완료
        elapsed = (datetime.now() - start).total_seconds()

        print("\n" + "="*60)
        print("✅ 파이프라인 완료!")
        print("="*60)
        print(f"소요 시간: {elapsed:.1f}초")
        print(f"처리 지점: {self.stats.get('valid_branches', 0)}개")
        print(f"전체 리뷰: {self.stats.get('filtered_reviews', 0):,}개")
        print(f"긍정 리뷰: {self.stats.get('positive_filtered', 0):,}개")
        if self.stats.get('sentiment'):
            print(f"\n📊 감정 분석 결과:")
            print(f"   - 긍정: {self.stats['sentiment']['positive']:,}개")
            print(f"   - 중립: {self.stats['sentiment']['neutral']:,}개")
            print(f"   - 부정: {self.stats['sentiment']['negative']:,}개")
        print(f"\n📁 출력 파일:")
        print(f"   - {output_dir}/branch_keywords.xlsx")
        print(f"   - {output_dir}/branch_top3_keywords.xlsx")
        print(f"   - {output_dir}/branch_summaries.xlsx")

        if self.stats.get('supabase_saved'):
            print(f"\n💾 Supabase 저장:")
            print(f"   - 요약: {self.stats['supabase_saved']}개 지점")
            print(f"   - 감정통계: {self.stats.get('stats_saved', 0)}개 지점")
            print(f"   - 최근 리뷰: {self.stats.get('reviews_saved', 0):,}개 (샘플)")


if __name__ == '__main__':
    pipeline = ReviewPipeline(min_reviews=30, use_deep_learning=False)
    pipeline.run(
        input_file='/home/teamo2/Downloads/Review_Summary_AI/data/리뷰리스트_20260109.xlsx',
        output_dir='/home/teamo2/Downloads/Review_Summary_AI/output'
    )
