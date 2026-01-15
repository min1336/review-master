"""
지점별 키워드 집계 모듈
"""
from typing import Dict, List, Optional
from collections import Counter
import pandas as pd

from .extractor import KeywordExtractor
from .weight import WeightCalculator


class KeywordAggregator:
    """
    지점별 키워드 집계기

    리뷰 데이터에서 지점별 TOP N 키워드를 추출합니다.
    가중치 기반 또는 단순 빈도 기반 집계를 지원합니다.
    """

    def __init__(
        self,
        extractor: Optional[KeywordExtractor] = None,
        weight_calculator: Optional[WeightCalculator] = None,
        use_weights: bool = True
    ):
        """
        Args:
            extractor: 키워드 추출기 (기본값: 새로 생성)
            weight_calculator: 가중치 계산기 (기본값: 새로 생성)
            use_weights: 가중치 사용 여부 (기본값: True)
        """
        self.extractor = extractor or KeywordExtractor()
        self.weight_calculator = weight_calculator or WeightCalculator()
        self.use_weights = use_weights

    def aggregate(
        self,
        df: pd.DataFrame,
        branch_col: str = '지점번호',
        keywords_col: str = 'keywords',
        top_n: int = 10
    ) -> pd.DataFrame:
        """
        지점별 키워드 집계

        Args:
            df: 리뷰 데이터프레임 (keywords 컬럼 필요)
            branch_col: 지점 번호 컬럼명
            keywords_col: 키워드 컬럼명
            top_n: 상위 N개 키워드

        Returns:
            지점별 키워드 집계 결과 DataFrame
        """
        results = []
        weighted_data = []

        for branch_id in df[branch_col].unique():
            branch_df = df[df[branch_col] == branch_id]

            if self.use_weights:
                top_keywords, kw_data = self._aggregate_weighted(
                    branch_df, branch_id, keywords_col, top_n
                )
                weighted_data.extend(kw_data)
            else:
                top_keywords = self._aggregate_simple(
                    branch_df, keywords_col, top_n
                )

            results.append({
                'branch_id': branch_id,
                'review_count': len(branch_df),
                'keywords': top_keywords
            })

        result_df = pd.DataFrame(results)

        # 가중치 데이터 저장 (나중에 DB 저장용)
        if weighted_data:
            self._weighted_keywords_data = weighted_data

        return result_df

    def _aggregate_weighted(
        self,
        branch_df: pd.DataFrame,
        branch_id: int,
        keywords_col: str,
        top_n: int
    ) -> tuple:
        """가중치 기반 키워드 집계"""
        keyword_scores = {}
        keyword_counts = {}

        for _, row in branch_df.iterrows():
            keywords = row.get(keywords_col, [])
            if not keywords:
                continue

            # 리뷰별 가중치 계산
            weight = self.weight_calculator.calculate_from_dataframe_row(row)

            for kw in keywords:
                keyword_scores[kw] = keyword_scores.get(kw, 0) + weight
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

        # 가중치 점수로 정렬
        sorted_keywords = sorted(
            keyword_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        top_keywords = [kw for kw, _ in sorted_keywords[:top_n]]

        # DB 저장용 데이터
        weighted_data = [
            {
                'branch_id': branch_id,
                'keyword': kw,
                'raw_count': keyword_counts.get(kw, 0),
                'weighted_score': round(score, 2)
            }
            for kw, score in sorted_keywords
        ]

        return top_keywords, weighted_data

    def _aggregate_simple(
        self,
        branch_df: pd.DataFrame,
        keywords_col: str,
        top_n: int
    ) -> List[str]:
        """단순 빈도 기반 키워드 집계"""
        all_keywords = []
        for keywords in branch_df[keywords_col]:
            if keywords:
                all_keywords.extend(keywords)

        keyword_counts = Counter(all_keywords)
        return [kw for kw, _ in keyword_counts.most_common(top_n)]

    def extract_and_aggregate(
        self,
        df: pd.DataFrame,
        text_col: str = '리뷰내용',
        branch_col: str = '지점번호',
        top_n: int = 10
    ) -> pd.DataFrame:
        """
        키워드 추출 + 집계 한번에 수행

        Args:
            df: 리뷰 데이터프레임
            text_col: 리뷰 텍스트 컬럼명
            branch_col: 지점 번호 컬럼명
            top_n: 상위 N개 키워드

        Returns:
            지점별 키워드 집계 결과 DataFrame
        """
        # 키워드 추출
        df = df.copy()
        df['keywords'] = df[text_col].apply(
            lambda x: self.extractor.extract(str(x)) if pd.notna(x) else []
        )

        # 집계
        return self.aggregate(df, branch_col, 'keywords', top_n)

    def get_weighted_keywords_data(self) -> List[Dict]:
        """가중치 키워드 데이터 반환 (DB 저장용)"""
        return getattr(self, '_weighted_keywords_data', [])

    def export_to_excel(
        self,
        keywords_df: pd.DataFrame,
        output_path: str,
        top_n: int = 10
    ) -> str:
        """
        키워드 집계 결과 엑셀 출력

        Args:
            keywords_df: 키워드 집계 결과 DataFrame
            output_path: 출력 파일 경로
            top_n: 출력할 키워드 수

        Returns:
            저장된 파일 경로
        """
        rows = []
        for _, row in keywords_df.iterrows():
            kw = row['keywords']
            row_dict = {
                '지점번호': row['branch_id'],
                '리뷰수': row['review_count']
            }

            for i in range(top_n):
                row_dict[f'키워드{i+1}'] = kw[i] if len(kw) > i else ''

            rows.append(row_dict)

        pd.DataFrame(rows).to_excel(output_path, index=False)
        return output_path
