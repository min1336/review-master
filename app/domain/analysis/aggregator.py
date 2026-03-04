"""
지점별 키워드 집계 모듈
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from .extractor import KeywordExtractor


class KeywordAggregator:
    """
    지점별 키워드 집계기

    리뷰 데이터에서 지점별 TOP N 키워드를 추출합니다.
    단순 빈도 기반 집계를 수행합니다.
    """

    def __init__(self, extractor: KeywordExtractor | None = None):
        """
        Args:
            extractor: 키워드 추출기 (기본값: 새로 생성)
        """
        self.extractor = extractor or KeywordExtractor()

    def aggregate(
        self,
        df: pd.DataFrame,
        branch_col: str = "지점번호",
        keywords_col: str = "keywords",
        top_n: int = 10,
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

        for branch_id in df[branch_col].unique():
            branch_df = df[df[branch_col] == branch_id]

            top_keywords = self._aggregate_simple(branch_df, keywords_col, top_n)

            results.append(
                {
                    "branch_id": branch_id,
                    "review_count": len(branch_df),
                    "keywords": top_keywords,
                }
            )

        return pd.DataFrame(results)

    def _aggregate_simple(
        self, branch_df: pd.DataFrame, keywords_col: str, top_n: int
    ) -> list[str]:
        """단순 빈도 기반 키워드 집계"""
        all_keywords = []
        for keywords in branch_df[keywords_col]:
            if keywords:
                all_keywords.extend(keywords)

        keyword_counts = Counter(all_keywords)
        return [kw for kw, _ in keyword_counts.most_common(top_n)]

    def export_to_excel(
        self, keywords_df: pd.DataFrame, output_path: str, top_n: int = 10
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
            kw = row["keywords"]
            row_dict = {"지점번호": row["branch_id"], "리뷰수": row["review_count"]}

            for i in range(top_n):
                row_dict[f"키워드{i + 1}"] = kw[i] if len(kw) > i else ""

            rows.append(row_dict)

        pd.DataFrame(rows).to_excel(output_path, index=False)
        return output_path
