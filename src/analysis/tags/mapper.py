"""
태그 자동 매핑 모듈

키워드 → 태그 매핑 규칙:
1. 어간 추출 (친절한 → 친절)
2. 동의어 그룹 매칭 (깨끗/청결/깔끔 → '깨끗' 태그)
3. 새 키워드는 자동 태그 생성 + 카테고리 자동 분류
"""

import os
import sys
from typing import Dict, List, Optional, Tuple

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class TagMapper:
    """키워드 → 태그 자동 매핑"""

    # 동의어 그룹 정의 (태그명 → 동의어 리스트)
    SYNONYM_GROUPS: Dict[str, List[str]] = {
        # 서비스 관련
        '친절': ['친절', '친절한', '친절함', '친절하다', '친절히', '친절하게'],
        '응대': ['응대', '대응', '빠른', '빠르다', '빠름', '신속', '신속한', '신속하다', '신속히'],
        '설명': ['설명', '안내', '상세한', '자세한', '자세히'],
        '배려': ['배려', '세심', '세심한', '꼼꼼', '꼼꼼한'],

        # 차량 관련
        '깨끗': ['깨끗', '깨끗한', '깨끗함', '청결', '청결한', '깔끔', '깔끔한', '깔끔함', '청소'],
        '새차': ['새차', '신차', '새것', '새 차'],
        '넓은': ['넓은', '넓다', '넓음', '널찍', '널찍한', '공간'],
        '쾌적': ['쾌적', '쾌적한', '쾌적함', '편안', '편안한'],
        '상태': ['상태', '컨디션', '관리'],

        # 가격 관련
        '저렴': ['저렴', '저렴한', '저렴함', '싼', '싸다', '싸요'],
        '합리적': ['합리적', '합리적인', '적당', '적당한'],
        '가성비': ['가성비', '가격대비', '가격 대비'],
        '비싼': ['비싼', '비싸다', '비쌈', '고가'],

        # 위치 관련
        '접근성': ['접근', '접근성', '가까운', '가깝다', '가까움', '근처'],
        '편리': ['편리', '편리한', '편리함', '편하다', '편해요', '편함'],
        '주차': ['주차', '주차장', '파킹'],

        # 편의시설 관련
        '대기실': ['대기실', '대기', '대기공간', '휴게실'],
        '편의': ['편의', '편의시설', '시설'],

        # 보험/보장 관련
        '보험': ['보험', '보장', '면책', '커버', '안심'],
        '자차': ['자차', '완전자차', '자기부담금', '자기부담'],
        '보상': ['보상', '사고', '책임', '대인', '대물'],
    }

    # 카테고리 자동 분류 규칙 (카테고리명 → 키워드 패턴)
    CATEGORY_RULES: Dict[str, List[str]] = {
        '서비스': ['친절', '응대', '설명', '안내', '배려', '직원', '서비스', '상담', '예약', '픽업', '반납'],
        '차량': ['깨끗', '청결', '새차', '상태', '넓은', '쾌적', '차량', '옵션', '성능', '연비'],
        '가격': ['가성비', '합리적', '저렴', '비싼', '요금', '가격', '할인', '무료'],
        '위치': ['접근', '위치', '주차', '거리', '가까운', '편리'],
        '편의시설': ['대기실', '화장실', '휴게', '편의', '시설', '와이파이', 'wifi'],
        '보험': ['보험', '보장', '면책', '자차', '완전자차', '자기부담금', '사고', '책임', '대인', '대물', '보상'],
    }

    # 부정 키워드 (부정 태그로 분류)
    NEGATIVE_KEYWORDS: List[str] = [
        '불친절', '불편', '더럽', '지저분', '늦', '느리', '비싸',
        '불만', '실망', '아쉽', '부족', '고장', '문제', '별로', '최악',
        '짜증', '화나', '싫', '안좋', '나빠', '후회', '환불'
    ]

    def __init__(self):
        """초기화: 역매핑 테이블 생성"""
        # 키워드 → 태그명 역매핑
        self._keyword_to_tag: Dict[str, str] = {}
        for tag_name, synonyms in self.SYNONYM_GROUPS.items():
            for synonym in synonyms:
                self._keyword_to_tag[synonym] = tag_name

        # 태그명 → 카테고리명 매핑
        self._tag_to_category: Dict[str, str] = {}
        for category, patterns in self.CATEGORY_RULES.items():
            for pattern in patterns:
                self._tag_to_category[pattern] = category

    def extract_stem(self, keyword: str) -> str:
        """
        간단한 어간 추출 (형태소 분석 없이)

        예: '친절한' → '친절', '깨끗함' → '깨끗'
        """
        if not keyword:
            return keyword

        # 일반적인 어미 제거
        suffixes = ['한', '함', '하다', '하게', '히', '하고', '해요', '합니다', '해서', '은', '는', '이', '가']
        result = keyword
        for suffix in suffixes:
            if result.endswith(suffix) and len(result) > len(suffix):
                result = result[:-len(suffix)]
                break

        return result if result else keyword

    def is_negative_keyword(self, keyword: str) -> bool:
        """부정 키워드 여부 확인"""
        keyword_lower = keyword.lower()
        return any(neg in keyword_lower for neg in self.NEGATIVE_KEYWORDS)

    def map_keyword_to_tag(self, keyword: str) -> Tuple[str, str]:
        """
        키워드 → (태그명, 감정) 매핑

        Args:
            keyword: 원본 키워드

        Returns:
            (태그명, 감정) - 감정은 'positive' 또는 'negative'
        """
        # 부정 키워드 확인
        sentiment = 'negative' if self.is_negative_keyword(keyword) else 'positive'

        # 1. 정확히 일치하는 매핑 확인
        if keyword in self._keyword_to_tag:
            return self._keyword_to_tag[keyword], sentiment

        # 2. 어간 추출 후 매핑 확인
        stem = self.extract_stem(keyword)
        if stem in self._keyword_to_tag:
            return self._keyword_to_tag[stem], sentiment

        # 3. 부분 매칭 (키워드가 동의어에 포함되거나 동의어가 키워드에 포함)
        for tag_name, synonyms in self.SYNONYM_GROUPS.items():
            for synonym in synonyms:
                if synonym in keyword or keyword in synonym:
                    return tag_name, sentiment

        # 4. 매핑 없음 → 어간을 태그명으로 사용
        return stem if stem else keyword, sentiment

    def get_category_for_tag(self, tag_name: str) -> Optional[str]:
        """
        태그 → 카테고리 자동 분류

        Args:
            tag_name: 태그명

        Returns:
            카테고리명 (없으면 None)
        """
        # 정확히 일치
        if tag_name in self._tag_to_category:
            return self._tag_to_category[tag_name]

        # 부분 일치
        for category, patterns in self.CATEGORY_RULES.items():
            for pattern in patterns:
                if pattern in tag_name or tag_name in pattern:
                    return category

        return None

    def auto_map_all_keywords(self) -> Dict:
        """
        DB의 모든 미매핑 키워드를 자동 매핑

        Returns:
            {'mapped': int, 'created_tags': int, 'errors': list}
        """
        try:
            # web 모듈에서 supabase 함수 임포트
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'web'))
            from supabase_client import (
                get_unmapped_keywords,
                get_or_create_tag,
                create_keyword_mapping,
                get_all_categories
            )
        except ImportError as e:
            return {'mapped': 0, 'created_tags': 0, 'errors': [f'Import error: {e}']}

        result = {
            'mapped': 0,
            'created_tags': 0,
            'errors': []
        }

        # 카테고리 ID 캐시
        categories = get_all_categories()
        category_id_map = {c['name']: c['id'] for c in categories}

        # 미매핑 키워드 조회
        unmapped = get_unmapped_keywords(limit=500)

        for item in unmapped:
            keyword = item['keyword']

            try:
                # 키워드 → 태그명, 감정 매핑
                tag_name, sentiment = self.map_keyword_to_tag(keyword)

                # 카테고리 자동 분류
                category_name = self.get_category_for_tag(tag_name)
                category_id = category_id_map.get(category_name) if category_name else None

                # 태그 조회 또는 생성
                tag = get_or_create_tag(
                    name=tag_name,
                    category_id=category_id,
                    sentiment=sentiment
                )

                if tag and tag.get('id'):
                    # 키워드 → 태그 매핑 생성
                    create_keyword_mapping(
                        keyword=keyword,
                        tag_id=tag['id'],
                        is_auto=True,
                        confidence=0.8  # 자동 매핑은 0.8 신뢰도
                    )
                    result['mapped'] += 1

                    # 새로 생성된 태그인지 확인
                    if tag.get('created_at') == tag.get('updated_at'):
                        result['created_tags'] += 1

            except Exception as e:
                result['errors'].append(f"{keyword}: {str(e)}")

        return result

    def map_keywords_batch(self, keywords: List[str]) -> List[Dict]:
        """
        키워드 리스트를 일괄 매핑 (DB 저장 없이 결과만 반환)

        Args:
            keywords: 키워드 리스트

        Returns:
            [{'keyword': str, 'tag_name': str, 'sentiment': str, 'category': str}, ...]
        """
        results = []
        for keyword in keywords:
            tag_name, sentiment = self.map_keyword_to_tag(keyword)
            category = self.get_category_for_tag(tag_name)
            results.append({
                'keyword': keyword,
                'tag_name': tag_name,
                'sentiment': sentiment,
                'category': category
            })
        return results


if __name__ == '__main__':
    # 테스트
    mapper = TagMapper()

    test_keywords = [
        '친절한', '친절함', '깨끗해요', '청결', '빠른', '신속한',
        '가성비', '저렴함', '주차', '대기실', '불친절', '더러움'
    ]

    print("=== 키워드 → 태그 매핑 테스트 ===\n")
    for kw in test_keywords:
        tag_name, sentiment = mapper.map_keyword_to_tag(kw)
        category = mapper.get_category_for_tag(tag_name)
        print(f"'{kw}' → 태그: '{tag_name}', 감정: {sentiment}, 카테고리: {category}")
