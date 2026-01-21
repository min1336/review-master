"""
단일 업체 상세 분석 엑셀 생성 (v2.0)

리뷰별 키워드 추출 → 태그+감정 분류 → 지점 집계 → 기간별 AI 요약

출력 구조:
  - 상단 (1-2행): 업체명 / 위치 / 리뷰수 / 태그목록 / 기간별 요약 (5개)
  - 하단 (4행~): 모든 리뷰 + 추출 키워드 + 태그별 감정

태그별 감정 형식:
  - 고객응대(+), 차량상태(-), 가성비(0)
  - +: 긍정, -: 부정, 0: 중립

처리 흐름:
  1. 데이터 로드 → 지점 필터링
  2. 키워드 추출 (MeCab)
  3. 리뷰별 태그+감정 분류 (문맥 기반)
  4. 지점 태그 집계 (긍정/부정 비율)
  5. 기간별 AI 요약 생성 (1개월/3개월/6개월/1년/전체)
  6. 엑셀 출력

실행:
    python scripts/export_branch_detail.py --branch_id 2
    python scripts/export_branch_detail.py --branch_id 426 --input data/리뷰리스트.xlsx

변경 이력:
- 2026-01-19: v2.0 - 태그별 감정 분류 추가, 문맥 기반 감정 판단
- 2026-01-19: v1.0 - 초기 구현
"""

import pandas as pd
import sys
import os
import argparse
from datetime import datetime, timedelta
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.analysis.keywords import KeywordExtractor
from src.analysis.tags import HybridClassifier


PERIOD_CONFIGS = {
    '1개월': 30,
    '3개월': 90,
    '6개월': 180,
    '1년': 365,
    '전체': None
}


def filter_by_period(df: pd.DataFrame, days: int) -> pd.DataFrame:
    """기간별 데이터 필터링"""
    if days is None:
        return df

    df = df.copy()
    df['등록일시'] = pd.to_datetime(df['등록일시'])
    cutoff = datetime.now() - timedelta(days=days)
    return df[df['등록일시'] >= cutoff]


def calculate_review_sentiment(tag_sentiment_str: str) -> str:
    """
    리뷰 단위 감정 판단
    - 모든 태그가 긍정 → 'positive'
    - 하나라도 부정 → 'negative' (혼합 감정은 부정 처리)
    - 중립만 → 'neutral'
    - 태그 없음 → 'neutral'
    """
    import re

    if not tag_sentiment_str or tag_sentiment_str.strip() == '':
        return 'neutral'

    matches = re.findall(r'([^,()]+)\(([+\-0])\)', tag_sentiment_str)

    if not matches:
        return 'neutral'

    has_negative = False
    has_positive = False

    for _, symbol in matches:
        if symbol == '-':
            has_negative = True
        elif symbol == '+':
            has_positive = True

    # 하나라도 부정이면 부정 리뷰로 분류
    if has_negative:
        return 'negative'
    elif has_positive:
        return 'positive'
    else:
        return 'neutral'


def generate_summary_for_period(
    df: pd.DataFrame,
    classifier: HybridClassifier,
    branch_name: str
) -> str:
    """기간별 AI 요약 생성 (리뷰별 태그+감정 데이터 + 건수/비율 포함)"""
    if len(df) == 0:
        return "(리뷰 없음)"

    if len(df) < 5:
        return f"(리뷰 {len(df)}개 - 요약 생략)"

    # 해당 기간 리뷰의 키워드 집계
    period_keywords = []
    for kws in df['추출키워드'].fillna(''):
        if kws:
            period_keywords.extend([k.strip() for k in kws.split(',') if k.strip()])

    keyword_counts = Counter(period_keywords)
    top_keywords = [kw for kw, _ in keyword_counts.most_common(15)]

    if not top_keywords:
        return "(키워드 없음)"

    # 리뷰 단위 감정 집계 (긍정/부정 건수)
    positive_count = 0
    negative_count = 0
    neutral_count = 0

    for _, row in df.iterrows():
        tag_sentiment_str = str(row.get('태그별감정', ''))
        review_sentiment = calculate_review_sentiment(tag_sentiment_str)

        if review_sentiment == 'positive':
            positive_count += 1
        elif review_sentiment == 'negative':
            negative_count += 1
        else:
            neutral_count += 1

    # 긍정/부정 비율 계산 (중립은 긍정으로 처리)
    total_for_ratio = positive_count + negative_count + neutral_count
    positive_for_ratio = positive_count + neutral_count  # 중립은 긍정에 포함

    if total_for_ratio > 0:
        positive_ratio = (positive_for_ratio / total_for_ratio) * 100
        negative_ratio = (negative_count / total_for_ratio) * 100
    else:
        positive_ratio = 100.0
        negative_ratio = 0.0

    # 감정 통계 데이터
    summary_stats = {
        'positive_count': positive_for_ratio,
        'negative_count': negative_count,
        'positive_ratio': positive_ratio,
        'negative_ratio': negative_ratio
    }

    # 해당 기간 리뷰의 태그+감정 집계 (리뷰별로 이미 분류된 데이터 활용)
    tag_sentiment = {}
    reviews_with_tags = df[df['태그별감정'].fillna('') != '']

    for _, row in reviews_with_tags.iterrows():
        tag_sentiment_str = str(row['태그별감정'])
        keywords = [k.strip() for k in str(row['추출키워드']).split(',') if k.strip()]

        # 태그별감정 파싱: "고객응대(+), 차량상태(-)" 형식
        import re
        matches = re.findall(r'([^,()]+)\(([+\-0])\)', tag_sentiment_str)

        for tag, symbol in matches:
            tag = tag.strip()
            sentiment = 'positive' if symbol == '+' else ('negative' if symbol == '-' else 'neutral')

            if tag not in tag_sentiment:
                tag_sentiment[tag] = {'positive': [], 'negative': [], 'neutral': []}

            # 해당 태그와 관련된 키워드 추가
            for kw in keywords[:3]:  # 대표 키워드 3개
                if kw not in tag_sentiment[tag][sentiment]:
                    tag_sentiment[tag][sentiment].append(kw)

    # LLM 요약 생성
    try:
        from src.llm import get_provider
        from src.llm.prompts import PromptTemplates

        provider = get_provider()

        # 도움돼요 상위 리뷰 추출 (기간 내 상위 10개)
        top_helpful_reviews = []
        if '도움돼요수' in df.columns:
            # 도움돼요수 기준 상위 10개
            top_helpful_df = df.nlargest(10, '도움돼요수')
            for _, row in top_helpful_df.iterrows():
                helpful_count = int(row.get('도움돼요수', 0))
                # 도움돼요가 1개 이상인 리뷰만 포함
                if helpful_count >= 1:
                    top_helpful_reviews.append({
                        'review': str(row.get('리뷰내용', '')),
                        'helpful_count': helpful_count,
                        'tags': str(row.get('태그별감정', ''))
                    })

        # 도움돼요 리뷰가 부족하면 기존 방식 (head)으로 대체
        sample_reviews = None
        if len(top_helpful_reviews) < 3:
            sample_reviews = df['리뷰내용'].dropna().head(5).tolist()
            top_helpful_reviews = None

        system_prompt, user_prompt = PromptTemplates.build_summary_prompt_with_tags(
            keywords=top_keywords,
            review_count=len(df),
            tag_sentiment_data=tag_sentiment,
            representative_reviews=sample_reviews,
            branch_name=branch_name,
            summary_stats=summary_stats,
            top_helpful_reviews=top_helpful_reviews
        )

        response = provider.generate(user_prompt, system_prompt=system_prompt)

        if response.success:
            return response.content
        else:
            return f"(요약 생성 실패: {response.error})"

    except Exception as e:
        return f"(요약 생성 오류: {str(e)})"


def main():
    parser = argparse.ArgumentParser(description='단일 업체 상세 분석 엑셀 생성')
    parser.add_argument('--branch_id', type=int, default=2, help='지점번호 (기본: 2)')
    parser.add_argument('--input', type=str, default='data/리뷰_예약통합.xlsx', help='입력 파일')
    args = parser.parse_args()

    branch_id = args.branch_id
    input_file = args.input

    print("\n" + "="*70)
    print(f"📊 단일 업체 상세 분석 시작 (지점번호: {branch_id})")
    print("="*70)

    # 1. 데이터 로드
    print(f"\n[1/5] 데이터 로드: {input_file}")
    df_all = pd.read_excel(input_file)
    df = df_all[df_all['지점번호'] == branch_id].copy().reset_index(drop=True)

    if len(df) == 0:
        print(f"❌ 지점번호 {branch_id}에 해당하는 리뷰가 없습니다.")
        return

    # 업체명 결정 (컬럼명 호환성 처리)
    if '업체명' in df.columns:
        branch_name = df['업체명'].iloc[0]
    elif '예약_업체명' in df.columns and '예약_지점명' in df.columns:
        company = df['예약_업체명'].iloc[0]
        branch = df['예약_지점명'].iloc[0]
        branch_name = f"{company} {branch}"
    else:
        branch_name = f'지점{branch_id}'

    location = df['주소'].iloc[0] if '주소' in df.columns else ''
    review_count = len(df)

    print(f"   업체명: {branch_name}")
    print(f"   위치: {location}")
    print(f"   리뷰 수: {review_count:,}개")

    # 2. 키워드 추출
    print(f"\n[2/5] 키워드 추출 중...")
    extractor = KeywordExtractor()
    reviews = df['리뷰내용'].fillna('').tolist()
    all_keywords = extractor.extract_batch(reviews)

    # 키워드를 문자열로 변환
    df['추출키워드'] = [', '.join(kws[:10]) for kws in all_keywords]
    print(f"   ✓ {len(all_keywords):,}개 리뷰 키워드 추출 완료")

    # 3. 리뷰별 태그+감정 분류 → 지점 집계
    print(f"\n[3/5] 리뷰별 태그+감정 분류 중 (하이브리드 ABSA)...")
    classifier = HybridClassifier(lazy_load=True)

    # 리뷰별 태그+감정 분류 결과 저장
    review_tag_sentiments = []  # 리뷰별 태그:감정 리스트
    tag_sentiment_totals = {}  # 지점 전체 태그별 긍/부정 집계

    for i, (keywords, review_text) in enumerate(zip(all_keywords, reviews)):
        if (i + 1) % 500 == 0:
            print(f"   {i+1}/{len(all_keywords)} 처리 중...")

        # 하이브리드 분류 (리뷰 전체 + 키워드)
        result = classifier.classify_review(review_text, keywords[:10])

        # 결과에서 태그별 감정 추출
        tag_sentiment_str_parts = []
        for tag, sentiments in result.items():
            pos_count = len(sentiments.get('positive', []))
            neg_count = len(sentiments.get('negative', []))
            neu_count = len(sentiments.get('neutral', []))

            # 지점 전체 태그별 긍/부정 집계 (먼저 처리)
            if tag not in tag_sentiment_totals:
                tag_sentiment_totals[tag] = {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0}
            tag_sentiment_totals[tag]['positive'] += pos_count
            tag_sentiment_totals[tag]['negative'] += neg_count
            tag_sentiment_totals[tag]['neutral'] += neu_count
            tag_sentiment_totals[tag]['total'] += pos_count + neg_count + neu_count

            # 대표 감정 결정
            if pos_count > neg_count:
                symbol = '+'
            elif neg_count > pos_count:
                symbol = '-'
            else:
                # 중립(0)은 출력에서 숨김 - 긍정/부정만 표시
                continue

            tag_sentiment_str_parts.append(f"{tag}({symbol})")

        review_tag_sentiments.append(', '.join(tag_sentiment_str_parts))

    df['태그별감정'] = review_tag_sentiments

    # 태그 목록 (총 개수 + 긍정/부정 비율)
    sorted_tags = sorted(tag_sentiment_totals.items(), key=lambda x: x[1]['total'], reverse=True)
    tag_list_parts = []
    for tag, counts in sorted_tags:
        total = counts['total']
        pos = counts['positive']
        neg = counts['negative']
        tag_list_parts.append(f"{tag}({total}, +{pos}/-{neg})")
    tag_list = ', '.join(tag_list_parts)

    print(f"   ✓ 리뷰별 태그 분류 완료: {len(tag_sentiment_totals)}개 태그")

    # 4. 기간별 AI 요약 생성
    print(f"\n[4/5] 기간별 AI 요약 생성 중...")
    summaries = {}

    for period_name, days in PERIOD_CONFIGS.items():
        print(f"   - {period_name} 요약 생성 중...")
        period_df = filter_by_period(df, days)
        summary = generate_summary_for_period(period_df, classifier, branch_name)
        summaries[period_name] = summary
        print(f"     ✓ {period_name}: {len(period_df)}개 리뷰")

    # 5. 엑셀 출력
    print(f"\n[5/5] 엑셀 파일 생성 중...")

    # 파일명 생성 (특수문자 제거)
    safe_name = branch_name.replace('/', '_').replace('\\', '_').replace(' ', '_')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = f'output/{safe_name}_상세분석_{timestamp}.xlsx'
    os.makedirs('output', exist_ok=True)

    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = '분석결과'

    # 스타일 정의
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_font_white = Font(bold=True, size=11, color='FFFFFF')
    wrap_align = Alignment(wrap_text=True, vertical='top')
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # ===== 상단: 업체 요약 =====
    summary_headers = ['업체명', '위치', '리뷰수', '태그목록', '1개월요약', '3개월요약', '6개월요약', '1년요약', '전체요약']
    summary_data = [
        branch_name, location, review_count, tag_list,
        summaries.get('1개월', ''), summaries.get('3개월', ''),
        summaries.get('6개월', ''), summaries.get('1년', ''), summaries.get('전체', '')
    ]

    # 헤더 행 (1행)
    for col, header in enumerate(summary_headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = wrap_align
        cell.border = thin_border

    # 데이터 행 (2행)
    for col, value in enumerate(summary_data, 1):
        cell = ws.cell(row=2, column=col, value=value)
        cell.alignment = wrap_align
        cell.border = thin_border

    # 열 너비 설정
    ws.column_dimensions['A'].width = 20  # 업체명
    ws.column_dimensions['B'].width = 30  # 위치
    ws.column_dimensions['C'].width = 10  # 리뷰수
    ws.column_dimensions['D'].width = 50  # 태그목록
    ws.column_dimensions['E'].width = 40  # 1개월요약
    ws.column_dimensions['F'].width = 40  # 3개월요약
    ws.column_dimensions['G'].width = 40  # 6개월요약
    ws.column_dimensions['H'].width = 40  # 1년요약
    ws.column_dimensions['I'].width = 40  # 전체요약

    # 행 높이 설정
    ws.row_dimensions[2].height = 80

    # ===== 빈 행 (3행) =====
    # 구분용

    # ===== 하단: 리뷰 상세 =====
    review_headers = ['리뷰번호', '등록일시', '리뷰내용', '추출키워드', '태그별감정']
    start_row = 4

    # 리뷰 헤더 (4행)
    for col, header in enumerate(review_headers, 1):
        cell = ws.cell(row=start_row, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = wrap_align
        cell.border = thin_border

    # 리뷰 데이터 (5행부터)
    for i, (_, row) in enumerate(df.iterrows()):
        row_num = start_row + 1 + i
        ws.cell(row=row_num, column=1, value=row.get('리뷰번호', '')).border = thin_border
        ws.cell(row=row_num, column=2, value=str(row.get('등록일시', ''))).border = thin_border
        ws.cell(row=row_num, column=3, value=str(row.get('리뷰내용', ''))[:500]).border = thin_border
        ws.cell(row=row_num, column=4, value=row.get('추출키워드', '')).border = thin_border
        ws.cell(row=row_num, column=5, value=row.get('태그별감정', '')).border = thin_border

    wb.save(output_path)

    print(f"\n" + "="*70)
    print(f"✅ 완료!")
    print(f"="*70)
    print(f"출력 파일: {output_path}")
    print(f"\n📋 엑셀 구조:")
    print(f"   행 1: 업체 요약 (업체명/위치/리뷰수/태그목록/기간별요약)")
    print(f"   행 4~: 리뷰 상세 ({review_count:,}개)")

    return output_path


if __name__ == '__main__':
    main()
