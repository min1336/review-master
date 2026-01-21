#!/usr/bin/env python
"""태그 재집계 스크립트 - 7개 카테고리 태그로 집계"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(line_buffering=True)

import pandas as pd
from collections import defaultdict
from web.supabase_client import get_client

# 7개 카테고리 태그 및 키워드 매핑
CATEGORY_KEYWORDS = {
    '고객응대': ['친절', '응대', '설명', '안내', '배려', '직원', '상담', '말씀', '인사', '미소', '태도', '매너', '친절한', '불친절'],
    '차량상태': ['깨끗', '청결', '새차', '상태', '넓은', '쾌적', '차량', '옵션', '성능', '연비', '세차', '냄새', '더러', '지저분', '고장', '흠집', '기스', '상처'],
    '가성비': ['가성비', '합리적', '저렴', '비싼', '요금', '가격', '할인', '무료', '싼', '비용', '저렴한', '비싸'],
    '반납/픽업': ['반납', '픽업', '인수', '인계', '수령', '배차', '출차', '입고', '출고', '셔틀', '버스', '대기'],
    '위치/접근성': ['접근', '위치', '주차', '거리', '가까운', '편리', '접근성', '공항', '가까워', '멀어'],
    '서비스': ['서비스', '예약', '시스템', '절차', '프로세스', '업무', '처리', '신속', '빠른', '느린', '늦은', '지연'],
    '보험/보장': ['보험', '보장', '면책', '자차', '완전자차', '자기부담금', '사고', '책임', '대인', '대물', '보상', '안심'],
}

# 부정 키워드 패턴
NEGATIVE_PATTERNS = [
    '불친절', '불편', '더럽', '지저분', '늦', '느리', '비싸', '비쌈',
    '불만', '실망', '아쉽', '부족', '고장', '문제', '별로', '최악',
    '짜증', '화나', '싫', '안좋', '나빠', '후회', '환불', '냄새',
    '흠집', '기스', '상처', '멀어', '지연'
]

def get_category(keyword: str) -> str:
    """키워드 → 카테고리 매핑"""
    keyword_lower = keyword.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in keyword_lower or keyword_lower in kw:
                return category
    return None

def get_sentiment(keyword: str, context: str = '') -> str:
    """키워드 + 문맥에서 감정 판단"""
    text = f"{keyword} {context}".lower()
    for neg in NEGATIVE_PATTERNS:
        if neg in text:
            return 'negative'
    return 'positive'

def main():
    print("=== 태그 재집계 시작 ===\n")

    # 1. 데이터 로드
    print("1. 데이터 로드...")
    df = pd.read_excel('data/리뷰_예약통합.xlsx')
    print(f"   리뷰 수: {len(df):,}개")
    print(f"   지점 수: {df['지점번호'].nunique():,}개")

    # 2. 태그 ID 조회
    print("\n2. 태그 ID 조회...")
    client = get_client()
    tags = client.table('tags').select('*').execute()
    tag_id_map = {t['name']: t['id'] for t in tags.data}
    print(f"   태그: {list(tag_id_map.keys())}")

    # 3. 키워드 추출 및 카테고리 집계
    print("\n3. 키워드 추출 및 카테고리 집계...")

    # MeCab 로드
    try:
        from src.analysis.keywords import KeywordExtractor
        extractor = KeywordExtractor()
        use_mecab = True
        print("   MeCab 사용")
    except:
        use_mecab = False
        print("   MeCab 없음 - 단순 매칭 사용")

    # 지점별 카테고리 집계
    branch_category_stats = defaultdict(lambda: defaultdict(lambda: {'positive': 0, 'negative': 0}))

    total = len(df)
    for idx, row in df.iterrows():
        if idx % 10000 == 0:
            print(f"   처리 중: {idx:,}/{total:,} ({idx/total*100:.1f}%)")

        branch_id = row['지점번호']
        review = str(row.get('리뷰내용', ''))

        if not review or len(review) < 5:
            continue

        # 키워드 추출
        if use_mecab:
            keywords = extractor.extract(review)  # 문자열 리스트 반환
        else:
            # 단순 매칭
            keywords = []
            for category, kws in CATEGORY_KEYWORDS.items():
                for kw in kws:
                    if kw in review:
                        keywords.append(kw)

        # 카테고리별 집계
        matched_categories = set()
        for keyword in keywords:
            category = get_category(keyword)
            if category and category not in matched_categories:
                sentiment = get_sentiment(keyword, review)
                branch_category_stats[branch_id][category][sentiment] += 1
                matched_categories.add(category)

    print(f"   완료: {len(branch_category_stats):,}개 지점")

    # 4. DB 저장
    print("\n4. DB 저장...")
    saved = 0
    errors = 0

    for branch_id, categories in branch_category_stats.items():
        for category, sentiments in categories.items():
            tag_id = tag_id_map.get(category)
            if not tag_id:
                continue

            pos_count = sentiments['positive']
            neg_count = sentiments['negative']

            # 긍정 저장
            if pos_count > 0:
                try:
                    client.table('branch_tags').upsert({
                        'branch_id': int(branch_id),
                        'tag_id': tag_id,
                        'period_type': 'positive',
                        'count': pos_count,
                        'weighted_score': pos_count
                    }, on_conflict='branch_id,tag_id,period_type').execute()
                    saved += 1
                except Exception as e:
                    errors += 1

            # 부정 저장
            if neg_count > 0:
                try:
                    client.table('branch_tags').upsert({
                        'branch_id': int(branch_id),
                        'tag_id': tag_id,
                        'period_type': 'negative',
                        'count': neg_count,
                        'weighted_score': neg_count
                    }, on_conflict='branch_id,tag_id,period_type').execute()
                    saved += 1
                except Exception as e:
                    errors += 1

    print(f"   저장: {saved:,}개, 오류: {errors}개")

    # 5. 결과 확인
    print("\n5. 결과 확인...")
    result = client.table('branch_tags').select('*', count='exact').execute()
    print(f"   branch_tags 총 레코드: {result.count}개")

    # 샘플 출력
    sample = client.table('branch_tags').select('branch_id, tag_id, period_type, count').order('count', desc=True).limit(10).execute()
    print("\n   상위 10개:")
    for r in sample.data:
        tag_name = [k for k, v in tag_id_map.items() if v == r['tag_id']][0]
        print(f"      지점 {r['branch_id']}: {tag_name} ({r['period_type']}) = {r['count']}")

    print("\n=== 완료 ===")

if __name__ == '__main__':
    main()
