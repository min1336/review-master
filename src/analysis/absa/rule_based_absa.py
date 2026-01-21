"""
규칙 기반 ABSA (Aspect-Based Sentiment Analysis)

비용 없이 로컬에서 실행되는 ABSA 구현:
1. 문장 분리 (절 단위)
2. Aspect 추출 (키워드 매칭)
3. Opinion 연결 (동일 문장/절 내)
4. 감정 판단 (패턴 매칭)

사용법:
    from src.analysis.absa import RuleBasedABSA

    absa = RuleBasedABSA()
    results = absa.analyze("직원이 친절했지만 차량이 더러웠어요")
    # [
    #   {'aspect': '고객응대', 'opinion': '직원이 친절했지만', 'sentiment': 'positive'},
    #   {'aspect': '차량청결', 'opinion': '차량이 더러웠어요', 'sentiment': 'negative'}
    # ]
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AspectOpinion:
    """Aspect-Opinion-Sentiment 결과"""
    aspect: str           # 태그명 (고객응대, 차량청결 등)
    opinion: str          # 원문에서 추출한 의견 표현
    sentiment: str        # positive, negative, neutral
    confidence: float     # 신뢰도 (0.0 ~ 1.0)
    keywords: List[str]   # 매칭된 키워드들


class RuleBasedABSA:
    """
    규칙 기반 Aspect-Based Sentiment Analysis

    처리 흐름:
    1. 리뷰를 절(clause) 단위로 분리
    2. 각 절에서 Aspect 키워드 탐지
    3. 동일 절 내에서 Opinion/Sentiment 판단
    4. 결과 병합 및 반환
    """

    # =========================================================================
    # Aspect 키워드 사전 (태그별)
    # =========================================================================
    # 일반 긍정어 (특정 태그에 매핑하지 않음 - 단독 사용 시 제외)
    GENERAL_POSITIVE = {'좋', '만족', '굿', 'good', '최고', '훌륭', '완벽', '추천', '강추', '최곱', '짱'}

    # 문맥 필요 키워드: 키워드 → (태그, 필요 문맥 키워드들)
    # 이 키워드들은 주변에 특정 문맥 키워드가 있어야만 매핑됨
    CONTEXT_REQUIRED_KEYWORDS = {
        '늦': ('배차/시간', ['배차', '차량', '픽업', '도착', '출발', '시간', '대기', '기다']),
        '빨리': ('배차/시간', ['배차', '차량', '픽업', '처리', '배달', '대기']),
        '빠르': ('배차/시간', ['배차', '차량', '픽업', '처리', '배달', '대기']),
    }

    ASPECT_KEYWORDS = {
        '고객응대': [
            '직원', '사장', '사장님', '알바', '스태프',
            '응대', '안내', '설명', '인사', '배웅', '친절', '불친절', '태도',
            '상담', '도움', '배려', '미소', '표정'
        ],
        '차량외관': [
            '외관', '외부', '외형', '겉', '바디',
            '스크래치', '흠집', '긁힘', '찍힘', '찌그러짐', '파손', '깨진',
            '범퍼', '휠', '바퀴', '타이어', '유리', '창문', '미러', '사이드미러',
            '도색', '페인트', '광택', '세차',
            '브레이크', '제동', '핸들', '엔진', '시동',
            '오래된', '낡은', '연식', '노후', '빵꾸', '펑크'
        ],
        '차량청결': [
            '내부', '실내', '시트', '좌석', '바닥', '매트', '트렁크',
            '청결', '청소', '깨끗', '지저분', '더러', '더럽', '드러',
            '냄새', '담배', '악취', '퀴퀴', '쩔어', '냄새나', '공기',
            '먼지', '얼룩', '이물질', '쓰레기', '머리카락',
            '에어컨', '히터', '송풍구'
        ],
        '가성비': [
            '가격', '가성비', '비용', '요금', '돈', '금액', '원',
            '저렴', '싼', '싸', '비싸', '비싼', '적정', '합리',
            '할인', '쿠폰', '이벤트', '혜택', '프로모션',
            '호구', '호갱', '바가지', '폭리',
            '추가비용', '추가금', '부담금', '수리비', '면책금'
        ],
        '위치/접근성': [
            '위치', '장소', '접근', '거리', '가까', '멀', '먼',
            '공항', '역', '터미널', '정류장', '버스', '지하철',
            '교통', '도보', '걸어', '찾기', '찾아', '헤매',
            '주변', '근처', '앞', '옆', '건물'
        ],
        '서비스': [
            '셔틀', '셔틀버스', '픽업버스', '무료셔틀',
            '대기실', '휴게실', '라운지', '화장실',
            '주차', '주차장', '발렛',
            '와이파이', 'wifi', '충전', '충전기',
            '음료', '커피', '다과', '간식',
            '예약', '예약확정', '문의', '상담', '전화', '카톡', '문자', '앱'
        ],
        '반납/픽업': [
            '반납', '픽업', '인수', '수령', '전달', '인계', '반환',
            '출차', '입차', '수거',
            '대여', '렌트', '렌탈', '빌리', '빌렸', '빌려',
            '서류', '계약서', '면허', '면허증',
            '절차', '과정', '프로세스', '간편', '간단', '복잡'
        ],
        '배차/시간': [
            '배차', '차종', '차량변경', '대차', '차종변경', '배정',
            '배달', '딜리버리', '탁송',
            '대기', '기다', '지연',  # '늦', '빨리', '빠르'는 CONTEXT_REQUIRED로 이동
            '약속', '예약시간', '도착시간',
            '재촉', '독촉', '급하', '서두르',
            '노쇼', '취소', '변경'
        ],
        '보험/보장': [
            '보험', '보장', '면책', '자기부담', '자차', '대인', '대물',
            '완전자차', '슈퍼', '풀커버', '안심',
            '사고', '접수', '처리', '보상', '배상', '손해',
            '긁', '부딪', '충돌', '파손'
        ]
    }

    # =========================================================================
    # 감정 패턴
    # =========================================================================

    # 긍정 패턴
    POSITIVE_PATTERNS = [
        # 기본 긍정
        r'좋[았아은네습고]', r'좋더', r'좋음',
        r'친절', r'깨끗', r'깔끔', r'쾌적', r'편[하안해했리]',
        r'만족', r'훌륭', r'최고', r'완벽', r'짱', r'굿', r'good', r'ok', r'OK',
        r'감사', r'고마', r'추천', r'강추',
        # 상태/품질
        r'괜찮', r'나쁘지.?않', r'무난', r'양호',
        r'넓[어은고]', r'넉넉', r'여유',
        r'새차', r'신차', r'최신', r'새것',
        # 속도/효율
        r'빠[르른]', r'신속', r'빨[리랐]', r'즉시', r'바로',
        r'간편', r'간단', r'쉽[게고]', r'수월',
        # 가격
        r'저렴', r'싸[고요]?', r'합리', r'착한.?가격', r'착해', r'착합',
        # 감탄/만족
        r'대박', r'짱', r'최곱?', r'베스트', r'best',
        r'맘에.?[들드]', r'마음에.?[들드]',
        r'기분.?좋', r'즐[거겁]', r'행복',
        # 재이용 의사
        r'또.?이용', r'다음에도', r'자주', r'계속',
        r'없[어었]',  # 부정+없다 = 긍정 (별도 처리)
    ]

    # 부정 패턴
    NEGATIVE_PATTERNS = [
        # 서비스 불만
        r'불친절', r'불편', r'불만', r'불쾌', r'불량',
        r'무례', r'퉁명', r'싸가지', r'건방',
        # 청결 문제
        r'더[럽러]', r'지저분', r'드러[워웠]', r'때[가끼]',
        r'냄새', r'악취', r'퀴퀴', r'쩔어', r'찝찝',
        r'먼지', r'얼룩', r'이물',
        # 시간/속도
        r'늦[었어게은]', r'지연', r'느[리린렸]', r'기다[리렸]',
        r'오래.?걸', r'한참',
        # 가격 불만
        r'비싸[고요]?', r'비싼', r'바가지', r'호구', r'호갱',
        r'추가.?요금', r'추가.?비용', r'추가.?금',
        # 감정 표현
        r'아쉬[운웠워움]', r'별로', r'그저.?그[래런]', r'그냥.?그',
        r'최악', r'짜증', r'화[나났]', r'열받', r'빡[치쳐]',
        r'실망', r'후회', r'황당', r'어이.?없',
        # 부정 동사
        r'없[어었다네]',  # 긍정+없다 = 부정
        r'안[돼되좋해]', r'못[했해하]',
        # 차량 문제
        r'고장', r'파손', r'문제', r'이상',
        r'오래[된됐]', r'낡[은았]', r'노후', r'헌차',
        r'덜컹', r'소음', r'삐걱',
        # 복합 부정
        r'이해.{0,3}안', r'납득.{0,3}안',
        r'기분.{0,5}나빠', r'기분.{0,5}안',
        r'말이.?안', r'도대체',
        # 폭행/위협 (심각)
        r'폭행', r'폭언', r'협박', r'위협', r'욕설',
    ]

    # 이중부정 → 긍정
    DOUBLE_NEGATION_PATTERNS = [
        (r'불편.{0,5}없', 'positive'),
        (r'불만.{0,10}없', 'positive'),
        (r'문제.{0,5}없', 'positive'),
        (r'걱정.{0,5}없', 'positive'),
        (r'아쉬.{0,5}없', 'positive'),
        (r'부족.{0,5}없', 'positive'),
        (r'부족함.{0,5}없', 'positive'),  # "부족함 없이"
        (r'냄새.{0,10}없', 'positive'),  # "냄새도 하나도 안나고"
        (r'냄새.{0,10}안.{0,3}나', 'positive'),  # "냄새도 안나고"
        (r'흠.{0,3}없', 'positive'),
        (r'잡.{0,3}없', 'positive'),
        # 추가 이중부정 패턴
        (r'하나도.{0,5}없', 'positive'),
        (r'하나도.{0,5}안', 'positive'),
        (r'전혀.{0,5}없', 'positive'),
        (r'전혀.{0,5}안', 'positive'),
        (r'별로.{0,5}없', 'positive'),
        (r'힘들.{0,10}없', 'positive'),
        # 긍정 표현 (없이 = without 긍정)
        (r'부족함\s*없이', 'positive'),
        (r'불편함\s*없이', 'positive'),
        (r'문제\s*없이', 'positive'),
    ]

    # 긍정 키워드 + 없다 → 부정
    POSITIVE_NEGATION_PATTERNS = [
        (r'친절.{0,5}없', 'negative'),
        (r'설명.{0,5}없', 'negative'),
        (r'안내.{0,5}없', 'negative'),
        (r'배려.{0,5}없', 'negative'),
    ]

    # 절 분리 패턴
    CLAUSE_SEPARATORS = [
        r'[.!?]',           # 문장 종결
        r'(?<=[다요죠음])[\s,]',  # 종결어미 + 공백/쉼표
        r'[,;]',            # 쉼표, 세미콜론
        r'(?:하지만|그런데|그러나|근데|다만)',  # 역접
        r'(?:그리고|또한|그래서|따라서)',      # 순접
        r'지만',            # ~지만 연결어미
        r'는데',            # ~는데 연결어미
        r'고\s',            # ~고 연결어미
    ]

    def __init__(self):
        """초기화"""
        # 정규식 컴파일
        self._positive_regex = re.compile('|'.join(self.POSITIVE_PATTERNS))
        self._negative_regex = re.compile('|'.join(self.NEGATIVE_PATTERNS))
        self._clause_regex = re.compile('|'.join(self.CLAUSE_SEPARATORS))

        # Aspect 키워드 → 태그 역매핑
        self._keyword_to_aspect = {}
        for aspect, keywords in self.ASPECT_KEYWORDS.items():
            for kw in keywords:
                self._keyword_to_aspect[kw] = aspect

    def analyze(self, review: str) -> List[Dict]:
        """
        단일 리뷰 ABSA 분석

        Args:
            review: 리뷰 텍스트

        Returns:
            [{'aspect': '고객응대', 'opinion': '직원이 친절했어요',
              'sentiment': 'positive', 'confidence': 0.9, 'keywords': ['직원', '친절']}]
        """
        if not review or len(review.strip()) < 3:
            return []

        # 1. 절 단위로 분리
        clauses = self._split_clauses(review)

        # 2. 각 절에서 Aspect-Opinion-Sentiment 추출
        results = []
        for clause in clauses:
            clause_results = self._analyze_clause(clause)
            results.extend(clause_results)

        # 3. 중복 제거 및 병합
        merged = self._merge_results(results)

        return [self._to_dict(r) for r in merged]

    def analyze_batch(self, reviews: List[str]) -> List[List[Dict]]:
        """배치 분석"""
        return [self.analyze(review) for review in reviews]

    def _split_clauses(self, text: str) -> List[str]:
        """절 단위 분리"""
        # 정규식으로 분리
        parts = self._clause_regex.split(text)

        # 빈 문자열 제거 및 정리
        clauses = []
        for part in parts:
            part = part.strip()
            if len(part) >= 2:
                clauses.append(part)

        # 분리 실패 시 원문 반환
        if not clauses:
            return [text]

        return clauses

    def _analyze_clause(self, clause: str) -> List[AspectOpinion]:
        """단일 절 분석"""
        results = []

        # 1. Aspect 키워드 찾기
        found_aspects = self._find_aspects(clause)

        if not found_aspects:
            return []

        # 2. 감정 판단
        sentiment, confidence = self._determine_sentiment(clause)

        # 3. 각 Aspect에 대해 결과 생성
        for aspect, keywords in found_aspects.items():
            results.append(AspectOpinion(
                aspect=aspect,
                opinion=clause,
                sentiment=sentiment,
                confidence=confidence,
                keywords=keywords
            ))

        return results

    def _find_aspects(self, text: str) -> Dict[str, List[str]]:
        """텍스트에서 Aspect 키워드 찾기"""
        found = {}  # {aspect: [keywords]}
        text_lower = text.lower()

        # 1. 일반 ASPECT_KEYWORDS 매칭
        for keyword, aspect in self._keyword_to_aspect.items():
            if keyword in text_lower:
                # 일반 긍정어는 단독 사용 시 제외 (다른 태그 키워드와 함께일 때만 유효)
                if keyword in self.GENERAL_POSITIVE:
                    continue

                if aspect not in found:
                    found[aspect] = []
                found[aspect].append(keyword)

        # 2. 문맥 필요 키워드 처리
        for keyword, (aspect, context_keywords) in self.CONTEXT_REQUIRED_KEYWORDS.items():
            if keyword in text_lower:
                # 문맥 키워드 중 하나라도 있으면 매핑
                has_context = any(ctx in text_lower for ctx in context_keywords)
                if has_context:
                    if aspect not in found:
                        found[aspect] = []
                    if keyword not in found[aspect]:
                        found[aspect].append(keyword)

        return found

    def _determine_sentiment(self, text: str) -> Tuple[str, float]:
        """감정 판단"""

        # 1. 이중부정 체크 (최우선)
        for pattern, sentiment in self.DOUBLE_NEGATION_PATTERNS:
            if re.search(pattern, text):
                return sentiment, 0.95

        # 2. 긍정+부정 체크
        for pattern, sentiment in self.POSITIVE_NEGATION_PATTERNS:
            if re.search(pattern, text):
                return sentiment, 0.9

        # 3. 일반 패턴 매칭
        positive_matches = len(self._positive_regex.findall(text))
        negative_matches = len(self._negative_regex.findall(text))

        # "없" 특수 처리 - 앞 단어에 따라 판단
        if '없' in text:
            # 부정 키워드 + 없다 → 긍정
            neg_keywords = ['불편', '불만', '문제', '걱정', '아쉬', '냄새', '흠']
            for nk in neg_keywords:
                if nk in text and '없' in text[text.find(nk):text.find(nk)+10]:
                    positive_matches += 1
                    negative_matches = max(0, negative_matches - 1)

        # 4. 결과 판단
        if positive_matches > negative_matches:
            confidence = min(0.95, 0.6 + 0.1 * (positive_matches - negative_matches))
            return 'positive', confidence
        elif negative_matches > positive_matches:
            confidence = min(0.95, 0.6 + 0.1 * (negative_matches - positive_matches))
            return 'negative', confidence
        elif positive_matches > 0:
            return 'positive', 0.5
        elif negative_matches > 0:
            return 'negative', 0.5
        else:
            # 패턴 없을 때: 맥락 기반 추론
            # 렌트카 리뷰 특성상 중립보다 긍정/부정이 많음
            return self._infer_sentiment_from_context(text)

    def _infer_sentiment_from_context(self, text: str) -> Tuple[str, float]:
        """
        패턴 매칭 실패 시 맥락 기반 감정 추론

        렌트카 리뷰 특성:
        - 대부분 긍정적 (만족 후 작성)
        - 부정적일 때는 명확한 불만 표현
        - 중립은 드묾
        """
        # 긍정 신호 (약한 패턴)
        weak_positive = [
            '요', '네요', '습니다', '에요', '세요',  # 존댓말 종결
            '^^', '~', '!', 'ㅎㅎ', 'ㅋㅋ',  # 이모티콘/웃음
            '잘', '편', '쉽', '빠', '넓', '깔끔',  # 긍정 형용사 어근
            '감사', '고마', '덕분', '좋',  # 감사 표현
        ]

        # 부정 신호 (약한 패턴)
        weak_negative = [
            '..', ';;;', 'ㅜ', 'ㅠ', ';;',  # 부정 이모티콘
            '좀', '근데', '다만', '그런데',  # 불만 전조
            '힘들', '어렵', '불', '안',  # 부정 어근
        ]

        pos_score = sum(1 for p in weak_positive if p in text)
        neg_score = sum(1 for p in weak_negative if p in text)

        # 길이에 따른 보정 (긴 리뷰는 보통 긍정)
        if len(text) > 50:
            pos_score += 1

        if pos_score > neg_score:
            return 'positive', 0.4
        elif neg_score > pos_score:
            return 'negative', 0.4
        else:
            # 기본값: 약한 긍정 (렌트카 리뷰 특성)
            return 'positive', 0.3

    def _merge_results(self, results: List[AspectOpinion]) -> List[AspectOpinion]:
        """중복 Aspect 병합"""
        merged = {}

        for r in results:
            if r.aspect not in merged:
                merged[r.aspect] = r
            else:
                # 기존 결과와 병합 (confidence 높은 것 우선)
                existing = merged[r.aspect]
                if r.confidence > existing.confidence:
                    merged[r.aspect] = AspectOpinion(
                        aspect=r.aspect,
                        opinion=f"{existing.opinion} / {r.opinion}",
                        sentiment=r.sentiment,
                        confidence=r.confidence,
                        keywords=list(set(existing.keywords + r.keywords))
                    )
                else:
                    merged[r.aspect] = AspectOpinion(
                        aspect=existing.aspect,
                        opinion=f"{existing.opinion} / {r.opinion}",
                        sentiment=existing.sentiment,
                        confidence=existing.confidence,
                        keywords=list(set(existing.keywords + r.keywords))
                    )

        return list(merged.values())

    def _to_dict(self, ao: AspectOpinion) -> Dict:
        """AspectOpinion → dict 변환"""
        return {
            'aspect': ao.aspect,
            'opinion': ao.opinion,
            'sentiment': ao.sentiment,
            'confidence': ao.confidence,
            'keywords': ao.keywords
        }

    # =========================================================================
    # 유틸리티 메서드
    # =========================================================================

    def get_aspect_summary(self, results: List[Dict]) -> Dict[str, Dict]:
        """
        분석 결과를 Aspect별로 요약

        Returns:
            {
                '고객응대': {'positive': 3, 'negative': 1, 'opinions': [...]},
                '차량청결': {'positive': 2, 'negative': 2, 'opinions': [...]}
            }
        """
        summary = {}

        for r in results:
            aspect = r['aspect']
            sentiment = r['sentiment']

            if aspect not in summary:
                summary[aspect] = {
                    'positive': 0,
                    'negative': 0,
                    'neutral': 0,
                    'opinions': []
                }

            summary[aspect][sentiment] += 1
            summary[aspect]['opinions'].append(r['opinion'])

        return summary

    def format_results(self, results: List[Dict]) -> str:
        """결과를 보기 좋게 포맷팅"""
        if not results:
            return "분석 결과 없음"

        lines = []
        for r in results:
            sentiment_symbol = {
                'positive': '+',
                'negative': '-',
                'neutral': '0'
            }.get(r['sentiment'], '?')

            lines.append(
                f"  [{r['aspect']}]({sentiment_symbol}) {r['opinion'][:50]}..."
                if len(r['opinion']) > 50 else
                f"  [{r['aspect']}]({sentiment_symbol}) {r['opinion']}"
            )

        return '\n'.join(lines)
