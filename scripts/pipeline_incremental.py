"""
증분 업데이트 파이프라인 (API 기반)

스케줄러에서 주기적으로 호출:
1. Carmore API에서 신규 리뷰 조회
2. 전처리 (빈 리뷰, 욕설, 광고 필터)
3. 감정분석 → 긍정만 통과
4. 키워드 추출 + 가중치 계산
5. branch_keywords 테이블 업데이트
6. 변화 감지 시 → AI 요약 재생성
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'web'))

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

from scripts.weight_calculator import WeightCalculator, KeywordScoreManager

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('pipeline_incremental')


class IncrementalPipeline:
    """
    증분 업데이트 파이프라인

    Excel 배치 처리가 아닌, API에서 신규 리뷰를 받아
    기존 키워드 점수에 증분 업데이트하는 방식
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

    # 욕설/비방 패턴
    PROFANITY_PATTERNS = [
        '씨발', '시발', 'ㅅㅂ', 'ㅆㅂ', '병신', 'ㅂㅅ', '지랄', 'ㅈㄹ',
        '개새끼', '새끼', 'ㅅㄲ', '미친', '또라이', '멍청', '바보',
        '꺼져', '닥쳐', '죽어', '뒤져', '썩어', '고소', '신고'
    ]

    # 광고 패턴
    AD_PATTERNS = [
        '연락주세요', '문의주세요', '카톡', '카카오톡', 'kakao',
        '010-', '02-', '070-', 'http', 'www.', '.com', '.kr',
        '할인', '이벤트', '무료', '선착순', '홍보', '광고'
    ]

    # 긍정 감정 단어
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

    def __init__(self):
        self.weight_calculator = WeightCalculator()
        self.keyword_manager = KeywordScoreManager(self.weight_calculator)
        self.mecab = None
        self.supabase_client = None

        self._init_mecab()
        self._init_supabase()

    def _init_mecab(self):
        """MeCab 초기화"""
        try:
            import mecab
            self.mecab = mecab.MeCab()
            logger.info("MeCab 초기화 완료")
        except ImportError:
            logger.warning("MeCab 미설치 - 정규식 폴백 사용")

    def _init_supabase(self):
        """Supabase 클라이언트 초기화"""
        try:
            from supabase_client import get_client
            self.supabase_client = get_client()
            logger.info("Supabase 연결 완료")
        except Exception as e:
            logger.warning(f"Supabase 연결 실패: {e}")

    # =========================================================================
    # 전처리
    # =========================================================================

    def preprocess_review(self, review: Dict) -> Optional[Dict]:
        """
        리뷰 전처리 (필터링)

        Returns:
            통과한 리뷰 또는 None (필터됨)
        """
        text = review.get('리뷰내용', '') or review.get('content', '')

        # 1. 빈 리뷰 필터
        if not text or len(text.strip()) < 5:
            return None

        # 2. 욕설/비방 필터
        text_lower = text.lower()
        for pattern in self.PROFANITY_PATTERNS:
            if pattern in text_lower:
                logger.debug(f"욕설 필터: {text[:30]}...")
                return None

        # 3. 광고 필터
        for pattern in self.AD_PATTERNS:
            if pattern in text_lower:
                logger.debug(f"광고 필터: {text[:30]}...")
                return None

        # 4. 블라인드/삭제 필터
        status = review.get('리뷰상태', '') or review.get('status', '')
        if status in ['블라인드', '삭제', 'blind', 'deleted']:
            return None

        return review

    # =========================================================================
    # 감정 분석
    # =========================================================================

    def analyze_sentiment(self, text: str) -> Tuple[str, float]:
        """
        간단한 감정 분석 (Lexicon 기반)

        Returns:
            (sentiment, score) - ('positive'/'neutral'/'negative', 0~1)
        """
        if not text:
            return 'neutral', 0.5

        pos_count = sum(1 for w in self.POSITIVE_WORDS if w in text)
        neg_count = sum(1 for w in self.NEGATIVE_WORDS if w in text)
        total = pos_count + neg_count

        if total == 0:
            return 'neutral', 0.5

        score = (pos_count - neg_count + total) / (2 * total)  # 0~1 정규화

        if score >= 0.6:
            return 'positive', score
        elif score <= 0.4:
            return 'negative', score
        else:
            return 'neutral', score

    def is_positive_review(self, review: Dict) -> Tuple[bool, float, str]:
        """리뷰 감정 분석 (긍정/부정 모두 포함, 중립만 제외)"""
        text = review.get('리뷰내용', '') or review.get('content', '')
        sentiment, score = self.analyze_sentiment(text)
        # 긍정+부정 모두 포함 (중립만 제외)
        is_valid = sentiment in ['positive', 'negative']
        return is_valid, score, sentiment

    # =========================================================================
    # 키워드 추출
    # =========================================================================

    def extract_keywords(self, text: str) -> List[str]:
        """텍스트에서 키워드 추출"""
        if not text:
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
    # DB 연동
    # =========================================================================

    def get_last_sync_info(self, branch_id: Optional[int] = None) -> Dict:
        """마지막 동기화 정보 조회"""
        if not self.supabase_client:
            return {}

        try:
            query = self.supabase_client.table('sync_status').select('*')
            if branch_id:
                query = query.eq('branch_id', branch_id)
            else:
                query = query.is_('branch_id', 'null')

            result = query.execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"동기화 정보 조회 실패: {e}")
            return {}

    def update_sync_status(
        self,
        branch_id: Optional[int],
        last_review_id: int,
        last_review_date: datetime,
        review_count: int,
        keyword_count: int
    ):
        """동기화 상태 업데이트"""
        if not self.supabase_client:
            return

        try:
            data = {
                'branch_id': branch_id,
                'last_review_id': last_review_id,
                'last_review_date': last_review_date.isoformat() if last_review_date else None,
                'last_sync_at': datetime.now().isoformat(),
                'review_count': review_count,
                'keyword_count': keyword_count
            }

            self.supabase_client.table('sync_status').upsert(
                data,
                on_conflict='branch_id'
            ).execute()
        except Exception as e:
            logger.error(f"동기화 상태 업데이트 실패: {e}")

    def load_branch_keywords(self, branch_id: int) -> List[Dict]:
        """DB에서 지점 키워드 로드"""
        if not self.supabase_client:
            return []

        try:
            result = self.supabase_client.table('branch_keywords') \
                .select('*') \
                .eq('branch_id', branch_id) \
                .execute()
            return result.data
        except Exception as e:
            logger.error(f"키워드 로드 실패: {e}")
            return []

    def save_branch_keywords(self, branch_id: int, keywords_data: List[Dict]):
        """DB에 지점 키워드 저장"""
        if not self.supabase_client:
            return

        try:
            for kw_data in keywords_data:
                self.supabase_client.table('branch_keywords').upsert(
                    kw_data,
                    on_conflict='branch_id,keyword'
                ).execute()
            logger.info(f"지점 {branch_id}: {len(keywords_data)}개 키워드 저장")
        except Exception as e:
            logger.error(f"키워드 저장 실패: {e}")

    def get_old_top_keywords(self, branch_id: int, limit: int = 10) -> List[str]:
        """이전 TOP 키워드 조회"""
        if not self.supabase_client:
            return []

        try:
            result = self.supabase_client.table('branch_keywords') \
                .select('keyword') \
                .eq('branch_id', branch_id) \
                .order('weighted_score', desc=True) \
                .limit(limit) \
                .execute()
            return [r['keyword'] for r in result.data]
        except Exception as e:
            logger.error(f"TOP 키워드 조회 실패: {e}")
            return []

    # =========================================================================
    # 요약 재생성
    # =========================================================================

    def regenerate_summary_if_needed(self, branch_id: int, old_keywords: List[str]):
        """키워드 변화 시 요약 재생성"""
        new_top = self.keyword_manager.get_top_keywords(branch_id, 10)
        new_keywords = [kw['keyword'] for kw in new_top]

        if self.keyword_manager.detect_significant_change(branch_id, old_keywords):
            logger.info(f"지점 {branch_id}: 키워드 변화 감지 → 요약 재생성 예정")
            # TODO: 요약 재생성 로직 (Gemini API 호출)
            # 현재는 플래그만 설정
            self._mark_summary_for_update(branch_id)

    def _mark_summary_for_update(self, branch_id: int):
        """요약 재생성 예정 표시"""
        if not self.supabase_client:
            return

        try:
            self.supabase_client.table('sync_status').upsert({
                'branch_id': branch_id,
                'next_summary_update_at': datetime.now().isoformat()
            }, on_conflict='branch_id').execute()
        except Exception as e:
            logger.error(f"요약 업데이트 표시 실패: {e}")

    # =========================================================================
    # 메인 처리 로직
    # =========================================================================

    def process_reviews(self, reviews: List[Dict]) -> Dict:
        """
        리뷰 목록 처리 (메인 진입점)

        Args:
            reviews: API에서 받은 리뷰 목록

        Returns:
            처리 결과 통계
        """
        stats = {
            'total': len(reviews),
            'filtered': 0,
            'negative': 0,
            'processed': 0,
            'keywords_extracted': 0,
            'branches_updated': set()
        }

        if not reviews:
            logger.info("처리할 리뷰 없음")
            return stats

        logger.info(f"=== 증분 파이프라인 시작: {len(reviews)}개 리뷰 ===")

        # 지점별 그룹핑
        branch_reviews: Dict[int, List[Dict]] = {}

        for review in reviews:
            # 1. 전처리 (필터링)
            processed = self.preprocess_review(review)
            if not processed:
                stats['filtered'] += 1
                continue

            # 2. 감정분석 (모든 리뷰 처리 - 필터링 없음)
            is_valid, sentiment_score, sentiment = self.is_positive_review(processed)
            processed['sentiment_score'] = sentiment_score
            processed['sentiment'] = sentiment

            # 통계만 기록 (필터링 없음)
            if sentiment == 'positive':
                stats['positive'] = stats.get('positive', 0) + 1
            elif sentiment == 'negative':
                stats['negative'] = stats.get('negative', 0) + 1
            else:
                stats['neutral'] = stats.get('neutral', 0) + 1

            # 지점별 그룹핑
            branch_id = processed.get('지점번호') or processed.get('branch_id')
            if branch_id:
                if branch_id not in branch_reviews:
                    branch_reviews[branch_id] = []
                branch_reviews[branch_id].append(processed)

        # 3. 지점별 처리
        for branch_id, reviews_list in branch_reviews.items():
            self._process_branch_reviews(branch_id, reviews_list, stats)

        logger.info(f"=== 처리 완료: {stats['processed']}개 리뷰, {len(stats['branches_updated'])}개 지점 ===")

        return stats

    def _process_branch_reviews(self, branch_id: int, reviews: List[Dict], stats: Dict):
        """지점별 리뷰 처리"""
        # 기존 키워드 로드
        old_keywords = self.get_old_top_keywords(branch_id)
        existing_kw_data = self.load_branch_keywords(branch_id)
        self.keyword_manager.load_from_db(branch_id, existing_kw_data)

        last_review_id = 0
        last_review_date = None

        for review in reviews:
            text = review.get('리뷰내용', '') or review.get('content', '')

            # 키워드 추출
            keywords = self.extract_keywords(text)
            if not keywords:
                continue

            # 가중치 계산
            review_date = review.get('등록일시') or review.get('created_at')
            if isinstance(review_date, str):
                try:
                    review_date = datetime.fromisoformat(review_date.replace('Z', '+00:00'))
                except:
                    review_date = datetime.now()

            weight = self.weight_calculator.calculate_review_weight(
                review_date=review_date,
                engagement_count=review.get('도움돼요수', 0) or 0,
                review_length=len(text),
                rating=review.get('지점평점(친절/편의성)', 4.0) or 4.0,
                sentiment_score=review.get('sentiment_score', 0.5)
            )

            # 키워드 점수 업데이트
            self.keyword_manager.update_keywords(
                branch_id=branch_id,
                keywords=keywords,
                weight=weight,
                review_date=review_date,
                is_new_review=True
            )

            stats['processed'] += 1
            stats['keywords_extracted'] += len(keywords)

            # 마지막 리뷰 정보 갱신
            review_id = review.get('리뷰번호') or review.get('id', 0)
            if review_id > last_review_id:
                last_review_id = review_id
                last_review_date = review_date

        # 시간 감쇠 적용
        self.keyword_manager.apply_decay_to_all()

        # DB 저장
        keywords_to_save = self.keyword_manager.export_for_db(branch_id)
        self.save_branch_keywords(branch_id, keywords_to_save)

        # 동기화 상태 업데이트
        self.update_sync_status(
            branch_id=branch_id,
            last_review_id=last_review_id,
            last_review_date=last_review_date,
            review_count=len(reviews),
            keyword_count=len(keywords_to_save)
        )

        # 요약 재생성 필요 여부 확인
        self.regenerate_summary_if_needed(branch_id, old_keywords)

        stats['branches_updated'].add(branch_id)

    # =========================================================================
    # API 연동 (Carmore)
    # =========================================================================

    def fetch_new_reviews_from_api(self, since: Optional[datetime] = None) -> List[Dict]:
        """
        Carmore API에서 신규 리뷰 조회

        Args:
            since: 이 시점 이후의 리뷰만 조회

        Returns:
            리뷰 목록
        """
        # TODO: 실제 Carmore API 연동
        # 현재는 플레이스홀더
        logger.warning("Carmore API 연동 미구현 - 빈 목록 반환")
        return []

    def run(self) -> Dict:
        """
        증분 파이프라인 실행 (스케줄러에서 호출)

        Returns:
            처리 결과 통계
        """
        logger.info("=== 증분 파이프라인 시작 ===")

        # 마지막 동기화 시점 확인
        sync_info = self.get_last_sync_info()
        since = None
        if sync_info.get('last_review_date'):
            since = datetime.fromisoformat(sync_info['last_review_date'])

        # API에서 신규 리뷰 조회
        reviews = self.fetch_new_reviews_from_api(since)

        if not reviews:
            logger.info("신규 리뷰 없음")
            return {'total': 0, 'processed': 0, 'message': '신규 리뷰 없음'}

        # 리뷰 처리
        stats = self.process_reviews(reviews)

        return stats


# 테스트
if __name__ == '__main__':
    pipeline = IncrementalPipeline()

    # 테스트 리뷰
    test_reviews = [
        {
            '리뷰번호': 1,
            '지점번호': 1234,
            '리뷰내용': '정말 친절하고 깨끗한 차량이었어요. 가격도 합리적이고 서비스도 최고였습니다.',
            '등록일시': datetime.now().isoformat(),
            '도움돼요수': 5,
            '지점평점(친절/편의성)': 4.8,
            '리뷰상태': '정상'
        },
        {
            '리뷰번호': 2,
            '지점번호': 1234,
            '리뷰내용': '차량 상태가 아주 좋았고 직원분들도 친절했어요. 다음에도 이용하겠습니다.',
            '등록일시': (datetime.now() - timedelta(days=10)).isoformat(),
            '도움돼요수': 3,
            '지점평점(친절/편의성)': 4.5,
            '리뷰상태': '정상'
        },
        {
            '리뷰번호': 3,
            '지점번호': 1234,
            '리뷰내용': '별로예요. 차가 더러웠어요.',  # 부정 리뷰 (필터됨)
            '등록일시': datetime.now().isoformat(),
            '도움돼요수': 0,
            '지점평점(친절/편의성)': 2.0,
            '리뷰상태': '정상'
        },
        {
            '리뷰번호': 4,
            '지점번호': 5678,
            '리뷰내용': '연락주세요 010-1234-5678',  # 광고 (필터됨)
            '등록일시': datetime.now().isoformat(),
            '도움돼요수': 0,
            '지점평점(친절/편의성)': 5.0,
            '리뷰상태': '정상'
        }
    ]

    print("=== 증분 파이프라인 테스트 ===\n")
    stats = pipeline.process_reviews(test_reviews)
    print(f"\n결과: {stats}")
