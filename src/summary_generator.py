"""
GPT-4o-mini 기반 리뷰 요약 생성 모듈
- 지점별 긍정 리뷰 묶음을 1~2문장으로 요약
- 배치 처리 및 비용 최적화
"""

import pandas as pd
from typing import Dict, List
import os
from tenacity import retry, stop_after_attempt, wait_exponential
import warnings

warnings.filterwarnings('ignore')

# OpenAI API는 실제 환경에서만 import
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ OpenAI 라이브러리가 설치되지 않았습니다. 'pip install openai' 실행 필요")


class SummaryGenerator:
    """GPT-4o-mini 기반 요약 생성기"""
    
    # 프롬프트 템플릿 (최적화된 버전)
    SUMMARY_PROMPT_TEMPLATE = """당신은 10년 경력의 렌트카 마케팅 전문가이자 전환율 최적화 카피라이터입니다.

**미션**: 고객 리뷰를 분석하여 예약 전환율을 높이는 신뢰감 있는 지점 소개 문구 작성

**[입력 데이터]**
• 지점: {branch_name}
• 검증된 리뷰: {review_count}개
• 평균 평점: {avg_rating}/5.0
• 핵심 키워드: {keywords}

**[고객 리뷰 샘플]**
{reviews}

**[작성 전략 - 3단계]**
1단계: 리뷰에서 가장 많이 언급된 강점 2-3개 파악
2단계: 해당 강점을 구체적 수치/사례와 연결
3단계: 예약을 유도하는 자연스러운 문장으로 완성

**[우수 사례 - 패턴 분석]**
✅ "{review_count}명 고객이 검증한 청결한 차량과 신속한 배차 서비스"
   → 패턴: [수치] + [검증] + [구체적 강점 2개]

✅ "제주 여행객들이 극찬한 공항 픽업과 친절한 직원 응대"
   → 패턴: [타겟 고객] + [행동] + [구체적 강점 2개]

✅ "신차급 관리와 주유 만충 서비스로 {avg_rating}점 평점 달성"
   → 패턴: [차별화 포인트] + [결과/성과]

✅ "빠른 배차, 깨끗한 차량 - 재방문 고객이 인정한 품질"
   → 패턴: [핵심 키워드 나열] + [사회적 증거]

**[실패 사례 - 반드시 회피]**
❌ "고객들이 만족했습니다" → 왜 만족? 무엇에? (구체성 없음)
❌ "서비스가 좋습니다" → 어떤 서비스? (모호함)
❌ "차량도 좋고 직원도 친절합니다" → 너무 일반적 (차별화 없음)
❌ "최고의 렌트카입니다" → 근거 없는 과장 (신뢰 저하)
❌ "추천합니다" → 이유 없는 추천 (설득력 없음)

**[필수 체크리스트]**
□ 70-120자 사이인가? (2줄 내외)
□ 제공된 키워드 중 2개 이상 포함했는가?
□ 수치나 구체적 사례가 있는가?
□ "좋다", "만족", "추천" 같은 모호한 단어만 쓰지 않았는가?
□ 이 지점만의 차별점이 드러나는가?

**[금지 단어/표현]**
- 단독 사용 금지: 좋다, 좋아요, 괜찮다, 만족, 추천, 최고, 최상, 완벽, 대박
- 금지 문장 패턴: "~에 만족했습니다", "~가 좋았습니다", "추천합니다"

**[출력 형식]**
요약문만 출력. 설명이나 부연 없이 완성된 2줄 문장만 작성.

요약:"""
    
    def __init__(self, api_key: str = None, model: str = "gpt-4o-mini"):
        """
        Args:
            api_key: OpenAI API 키 (None이면 환경 변수에서 읽음)
            model: 사용할 모델 (기본값: gpt-4o-mini)
        """
        self.model = model
        self.client = None
        self.stats = {
            'total_calls': 0,
            'total_cost': 0.0,
            'total_tokens': 0
        }
        
        # API 키 설정
        if OPENAI_AVAILABLE:
            api_key = api_key or os.getenv('OPENAI_API_KEY')
            
            if api_key:
                self.client = OpenAI(api_key=api_key)
            else:
                print("⚠️ OpenAI API 키가 설정되지 않았습니다.")
                print("   환경 변수 OPENAI_API_KEY를 설정하거나 api_key 인자를 전달하세요.")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))
    def _call_gpt(self, prompt: str, max_tokens: int = 150) -> Dict:
        """
        GPT API 호출 (재시도 로직 포함)
        
        Args:
            prompt: 프롬프트
            max_tokens: 최대 토큰 수
        
        Returns:
            응답 딕셔너리
        """
        if not OPENAI_AVAILABLE or not self.client:
            # API 사용 불가시 더미 응답
            return {
                'summary': "고객들은 서비스와 차량에 만족했습니다.",
                'tokens': 0,
                'cost': 0.0,
                'model': 'dummy'
            }
        
        try:
            # OpenAI 1.0+ API 호출 방식
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "당신은 렌트카 마케팅 전문가이자 카피라이터입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=max_tokens
            )
            
            # 응답 추출
            summary = response.choices[0].message.content.strip()
            
            # 토큰 사용량 및 비용 계산
            usage = response.usage
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens
            
            # GPT-4o-mini 가격: $0.150 / 1M input, $0.600 / 1M output
            cost = (input_tokens * 0.150 + output_tokens * 0.600) / 1_000_000
            
            # 통계 업데이트
            self.stats['total_calls'] += 1
            self.stats['total_cost'] += cost
            self.stats['total_tokens'] += input_tokens + output_tokens
            
            return {
                'summary': summary,
                'tokens': input_tokens + output_tokens,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost': cost,
                'model': self.model
            }
            
        except Exception as e:
            print(f"⚠️ GPT API 호출 오류: {e}")
            # 오류 시 기본 메시지 반환
            return {
                'summary': "고객들은 서비스에 만족했습니다.",
                'tokens': 0,
                'cost': 0.0,
                'model': 'error',
                'error': str(e)
            }

    def _validate_and_improve_summary(self, summary: str, keywords: List[str],
                                      review_count: int, avg_rating: float) -> str:
        """
        요약 품질 검증 및 개선

        Args:
            summary: 원본 요약문
            keywords: 키워드 리스트
            review_count: 리뷰 수
            avg_rating: 평균 평점

        Returns:
            검증/개선된 요약문
        """
        import re

        # 1. 길이 검증
        if len(summary) < 30 or len(summary) > 200:
            return self._generate_fallback_summary(keywords, review_count, avg_rating)

        # 2. 저품질 패턴 탐지
        low_quality_patterns = [
            r'^고객들은?\s*(만족|좋아)',
            r'^서비스가?\s*(좋|훌륭)',
            r'^차량\s*(상태가?)?\s*(좋|깨끗)',
            r'만족했습니다\.?$',
            r'추천합니다\.?$',
            r'^좋았습니다',
            r'^괜찮았습니다',
        ]

        for pattern in low_quality_patterns:
            if re.search(pattern, summary, re.IGNORECASE):
                return self._generate_fallback_summary(keywords, review_count, avg_rating)

        # 3. 키워드 포함 검증 (최소 1개)
        keywords_found = 0
        if keywords:
            for kw in keywords[:5]:  # 상위 5개 키워드만 확인
                kw_clean = kw.replace('#', '').strip()
                if kw_clean and kw_clean in summary:
                    keywords_found += 1

        if keywords_found == 0 and keywords:
            # 키워드가 없으면 fallback
            return self._generate_fallback_summary(keywords, review_count, avg_rating)

        # 4. 반복 단어 제거
        summary = re.sub(r'(\b\w+\b)\s+\1', r'\1', summary)

        # 5. 불필요한 접두사 제거
        summary = re.sub(r'^(요약:?\s*|답변:?\s*)', '', summary).strip()

        return summary

    def _generate_fallback_summary(self, keywords: List[str],
                                   review_count: int, avg_rating: float) -> str:
        """
        품질 미달 시 템플릿 기반 대체 요약 생성

        Args:
            keywords: 키워드 리스트
            review_count: 리뷰 수
            avg_rating: 평균 평점

        Returns:
            템플릿 기반 요약문
        """
        import random

        # 키워드 정리
        clean_keywords = []
        if keywords:
            for kw in keywords[:4]:
                kw_clean = kw.replace('#', '').replace('_', ' ').strip()
                if kw_clean and len(kw_clean) >= 2:
                    clean_keywords.append(kw_clean)

        kw1 = clean_keywords[0] if len(clean_keywords) > 0 else "친절한 서비스"
        kw2 = clean_keywords[1] if len(clean_keywords) > 1 else "깨끗한 차량"

        # 다양한 템플릿
        templates = [
            f"{review_count}명의 고객이 검증한 {kw1}과 {kw2}",
            f"{kw1}, {kw2} - {review_count}건의 리뷰가 증명하는 품질",
            f"평점 {avg_rating:.1f}점을 기록한 {kw1}과 {kw2}",
            f"고객들이 인정한 {kw1}과 {kw2}로 높은 재방문율 달성",
            f"{kw1}과 {kw2}로 {review_count}명 고객의 신뢰 획득",
        ]

        return random.choice(templates)

    def generate_summary_for_branch(self, branch_id: int, reviews: List[str], 
                                   keywords: List[str] = None,
                                   avg_rating: float = None,
                                   review_df: pd.DataFrame = None,
                                   max_reviews: int = 100) -> Dict:
        """
        특정 지점의 리뷰 요약 생성
        
        Args:
            branch_id: 지점 번호
            reviews: 리뷰 텍스트 리스트
            keywords: 해시태그 키워드 리스트
            avg_rating: 평균 평점
            review_df: 리뷰 DataFrame (공감수, 날짜 등 메타데이터 포함)
            max_reviews: 최대 처리 리뷰 수 (토큰 제한)
        
        Returns:
            요약 결과
        """
        if not reviews:
            return {
                'branch_id': branch_id,
                'summary': None,
                'review_count': 0,
                'tokens': 0,
                'cost': 0.0
            }
        
        # ========================================================================
        # 🎯 가중치 기반 스마트 샘플링
        # ========================================================================
        if review_df is not None and len(review_df) > 0:
            import datetime
            from datetime import timedelta
            
            # 현재 날짜 기준 설정
            if '작성일' in review_df.columns:
                review_df['작성일_dt'] = pd.to_datetime(review_df['작성일'], errors='coerce')
                now = datetime.datetime.now()
                one_month_ago = now - timedelta(days=30)
            
            # 각 리뷰에 가중치 계산
            weights = []
            for idx, row in review_df.iterrows():
                weight = 1.0  # 기본 가중치
                
                # 1. ✅ 최신성 가중치 (최근 1개월 간 데이터)
                if '작성일_dt' in review_df.columns and pd.notna(row.get('작성일_dt')):
                    written_date = row['작성일_dt']
                    if written_date >= one_month_ago:
                        weight *= 2.0  # 최근 1개월: 2배
                    elif written_date >= now - timedelta(days=90):
                        weight *= 1.5  # 최근 3개월: 1.5배
                    elif written_date < now - timedelta(days=365):
                        weight *= 0.3  # 1년 이상 오래된 리뷰: 0.3배
                
                # 2. ✅ 공감수 가중치
                empathy = row.get('공감수', 0) or 0
                if empathy >= 10:
                    weight *= 2.5  # 공감 10개 이상: 2.5배
                elif empathy >= 5:
                    weight *= 1.8  # 공감 5개 이상: 1.8배
                elif empathy >= 1:
                    weight *= 1.3  # 공감 1개 이상: 1.3배
                
                # 3. ✅ 리뷰 길이 가중치 (고품질 리뷰)
                review_text = row.get('리뷰내용', '') or ''
                review_length = len(str(review_text))
                if review_length >= 100:
                    weight *= 1.5  # 긴 리뷰 (100자 이상): 1.5배
                elif review_length >= 50:
                    weight *= 1.2  # 중간 길이 (50자 이상): 1.2배
                elif review_length < 20:
                    weight *= 0.3  # 짧은 리뷰 (20자 미만): 0.3배
                
                # 4. ✅ 별점 가중치
                rating = row.get('차량평점', 5) or 5
                if rating >= 4.5:
                    weight *= 1.2  # 높은 별점: 1.2배
                elif rating < 3.0:
                    weight *= 0.2  # 낮은 별점: 0.2배 (부정적)
                
                # 5. ❌ 블라인드/삭제된 리뷰
                blocked = row.get('블라인드여부', 'N') or 'N'
                if blocked == 'Y':
                    weight *= 0.1  # 블라인드: 거의 제외

                # 6. ✅ 품질 점수 가중치 (전처리에서 계산된 quality_score 활용)
                quality_score = row.get('quality_score', 0.5) or 0.5
                weight *= (0.5 + quality_score)  # 0.5~1.5 범위 승수

                # 7. ❌ 템플릿 리뷰 패널티
                is_template = row.get('is_template', False)
                if is_template:
                    weight *= 0.3  # 템플릿 리뷰: 0.3배

                weights.append(weight)
            
            # 가중치 기반 샘플링
            review_df['weight'] = weights
            
            # 상위 가중치 리뷰 선택
            top_reviews = review_df.nlargest(max_reviews, 'weight')
            reviews_sampled = top_reviews['리뷰내용'].tolist()
        else:
            # DataFrame 없으면 기존 방식 (최신 순)
            reviews_sampled = reviews[:max_reviews]
        
        # 리뷰 텍스트 결합 (간결하게)
        review_texts = '\n'.join([f"- {r[:100]}" for r in reviews_sampled if r])
        
        # 키워드 문자열 생성
        keywords_str = ', '.join(keywords) if keywords else "차량, 서비스, 친절"
        
        # 평점 기본값
        avg_rating = avg_rating or 4.9
        
        # 프롬프트 생성
        prompt = self.SUMMARY_PROMPT_TEMPLATE.format(
            branch_name=f"지점 {branch_id}",
            review_count=len(reviews_sampled),
            avg_rating=f"{avg_rating:.1f}",
            keywords=keywords_str,
            reviews=review_texts
        )
        
        # GPT 호출
        result = self._call_gpt(prompt, max_tokens=200)  # 2-3줄 요약을 위해 200 토큰으로 증가

        # 품질 검증 및 후처리
        summary = result['summary']
        summary = self._validate_and_improve_summary(summary, keywords, len(reviews_sampled), avg_rating)
        
        return {
            'branch_id': branch_id,
            'summary': summary,
            'review_count': len(reviews_sampled),
            'tokens': result.get('tokens', 0),
            'input_tokens': result.get('input_tokens', 0),
            'output_tokens': result.get('output_tokens', 0),
            'cost': result.get('cost', 0.0),
            'model': result.get('model', 'unknown')
        }
    
    def generate_summaries_for_all_branches(self, df: pd.DataFrame,
                                           keywords_df: pd.DataFrame = None,
                                           max_reviews_per_branch: int = 100,
                                           progress_interval: int = 50) -> pd.DataFrame:
        """
        모든 지점의 요약 생성
        
        Args:
            df: 리뷰 DataFrame (지점번호, 리뷰내용 포함)
            keywords_df: 지점별 키워드 DataFrame (branch_id, keywords 컬럼 포함)
            max_reviews_per_branch: 지점당 최대 처리 리뷰 수
            progress_interval: 진행 상황 출력 간격
        
        Returns:
            지점별 요약 DataFrame
        """
        print("="*80)
        print("📝 GPT-4o-mini 요약 생성 시작")
        print("="*80)
        
        # 지점별 그룹화
        branch_ids = df['지점번호'].unique()
        
        print(f"\n처리 대상: {len(branch_ids)}개 지점")
        print(f"지점당 최대 리뷰: {max_reviews_per_branch}개")
        
        if not OPENAI_AVAILABLE or not self.client:
            print("\n⚠️ OpenAI API 사용 불가 - 더미 데이터로 진행합니다.")
        
        results = []
        
        for i, branch_id in enumerate(branch_ids, 1):
            if i % progress_interval == 0:
                print(f"  처리 중: {i}/{len(branch_ids)} 지점... (비용: ${self.stats['total_cost']:.4f})")
            
            # 해당 지점 리뷰
            branch_reviews_df = df[df['지점번호'] == branch_id].copy()
            reviews_list = branch_reviews_df['리뷰내용'].tolist()
            
            # 평균 평점 계산
            avg_rating = branch_reviews_df['차량평점'].mean() if '차량평점' in branch_reviews_df.columns else 4.9
            
            # 키워드 추출 (있으면)
            keywords = None
            if keywords_df is not None:
                keyword_row = keywords_df[keywords_df['branch_id'] == branch_id]
                if len(keyword_row) > 0:
                    keywords = keyword_row.iloc[0]['keywords']
            
            # 요약 생성 (review_df 전달 - 가중치 시스템 사용)
            result = self.generate_summary_for_branch(
                branch_id, 
                reviews_list,
                keywords=keywords,
                avg_rating=avg_rating,
                review_df=branch_reviews_df,  # DataFrame 전달
                max_reviews=max_reviews_per_branch
            )
            
            results.append(result)
        
        # DataFrame으로 변환
        results_df = pd.DataFrame(results)
        
        # 최종 통계
        print(f"\n✅ 요약 생성 완료")
        print(f"   - 총 지점: {len(results_df)}개")
        print(f"   - 총 API 호출: {self.stats['total_calls']}회")
        print(f"   - 총 토큰: {self.stats['total_tokens']:,}개")
        print(f"   - 총 비용: ${self.stats['total_cost']:.4f}")
        print(f"   - 평균 비용/지점: ${self.stats['total_cost']/len(results_df):.6f}")
        
        return results_df
    
    def get_statistics(self) -> Dict:
        """
        요약 생성 통계 반환
        
        Returns:
            통계 딕셔너리
        """
        return self.stats


# 실행 예시
if __name__ == '__main__':
    print("="*80)
    print("GPT-4o-mini 요약 생성 테스트")
    print("="*80)
    
    # API 키 확인
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("\n⚠️ OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        print("   더미 모드로 실행합니다.\n")
    
    # 데이터 로드
    print("\n📂 데이터 로드 중...")
    df = pd.read_csv('/home/teamo2/Downloads/Review_Summary_AI/preprocessed_positive_reviews.csv')
    print(f"✅ 로드 완료: {len(df):,}개 리뷰")
    
    # 요약 생성기 생성
    generator = SummaryGenerator(api_key=api_key)
    
    # 샘플: 상위 5개 지점만 테스트
    print("\n" + "="*80)
    print("🧪 샘플 테스트 (상위 5개 지점)")
    print("="*80)
    
    top_branches = df['지점번호'].value_counts().head(5).index.tolist()
    sample_df = df[df['지점번호'].isin(top_branches)]
    
    # 요약 생성
    summaries_df = generator.generate_summaries_for_all_branches(
        sample_df,
        max_reviews_per_branch=50,
        progress_interval=1
    )
    
    # 결과 출력
    print("\n" + "="*80)
    print("📊 요약 결과")
    print("="*80)
    
    for _, row in summaries_df.iterrows():
        print(f"\n지점 {row['branch_id']} ({row['review_count']}개 리뷰):")
        print(f"  요약: {row['summary']}")
        print(f"  비용: ${row['cost']:.6f} (토큰: {row['tokens']})")
    
    # 통계 출력
    stats = generator.get_statistics()
    print(f"\n{'='*80}")
    print("📈 전체 통계")
    print("="*80)
    print(f"총 API 호출: {stats['total_calls']}회")
    print(f"총 토큰: {stats['total_tokens']:,}개")
    print(f"총 비용: ${stats['total_cost']:.4f}")
    
    print("\n" + "🎉 "*40)
    print("GPT 요약 테스트 완료!")
    print("🎉 "*40)
