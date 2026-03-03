"""VehicleAnalyzer.build_vehicle_rankings 태그 표시 테스트

차량 평가에서 개별 태그명(외관, 청결 등)이 건수 기준 Top 2로
표시되는지 검증합니다.
"""

from __future__ import annotations

import pytest


class TestBuildVehicleRankingsTagDisplay:
    """build_vehicle_rankings가 개별 태그를 Top 2로 표시하는지 검증"""

    def _make_analyzer(self):
        from services.vehicle_analyzer import VehicleAnalyzer
        return VehicleAnalyzer()

    def _make_vehicle_tags_raw(self):
        """테스트용 vehicle_tags_raw 데이터 (서브태그 포함)"""
        return {
            "K3": {
                "total_positive": 15,
                "total_negative": 5,
                "total_count": 20,
                "tags": {
                    "외관": {
                        "positive": 5, "negative": 2, "total": 7,
                        "category_name": "외관",
                    },
                    "차량외관": {
                        "positive": 3, "negative": 1, "total": 4,
                        "category_name": "외관",
                    },
                    "신차": {
                        "positive": 2, "negative": 0, "total": 2,
                        "category_name": "외관",
                    },
                    "청결": {
                        "positive": 4, "negative": 1, "total": 5,
                        "category_name": "청결",
                    },
                    "실내": {
                        "positive": 1, "negative": 1, "total": 2,
                        "category_name": "청결",
                    },
                },
            },
        }

    def test_top2_positive_tags_displayed(self):
        """positive 건수 Top 2 서브태그만 표시되어야 한다"""
        analyzer = self._make_analyzer()
        raw = self._make_vehicle_tags_raw()

        top_liked, _ = analyzer.build_vehicle_rankings(raw, [])

        assert len(top_liked) == 1
        k3 = top_liked[0]

        # 서브태그만 사용 (name != category_name)
        # 서브태그 positive 순: 차량외관(3) > 신차(2) > 실내(1)
        assert len(k3.tags) == 2, f"Top 2만 표시해야 함: {k3.tags}"
        assert "차량외관(3건)" in k3.tags
        assert "신차(2건)" in k3.tags

    def test_top2_negative_tags_displayed(self):
        """negative 건수 Top 2 서브태그만 표시되어야 한다"""
        analyzer = self._make_analyzer()
        raw = self._make_vehicle_tags_raw()

        _, top_disliked = analyzer.build_vehicle_rankings(raw, [])

        assert len(top_disliked) == 1
        k3 = top_disliked[0]

        # 서브태그만 사용 (name != category_name)
        # 서브태그 negative 순: 차량외관(1)=실내(1)
        assert len(k3.tags) == 2, f"Top 2만 표시해야 함: {k3.tags}"
        assert "차량외관(1건)" in k3.tags
        assert "실내(1건)" in k3.tags

    def test_individual_tag_names_not_categories(self):
        """카테고리명이 아닌 개별 태그명이 표시되어야 한다"""
        analyzer = self._make_analyzer()
        raw = self._make_vehicle_tags_raw()

        top_liked, _ = analyzer.build_vehicle_rankings(raw, [])

        k3 = top_liked[0]
        tag_names = [t.split("(")[0] for t in k3.tags]

        # 개별 태그명이어야 함
        for name in tag_names:
            assert name not in ("외관", "청결"), (
                f"카테고리명이 아닌 태그명이어야 함: {k3.tags}"
            )

    def test_only_vehicle_category_tags_in_output(self):
        """비 차량 카테고리 태그가 결과에 포함되지 않아야 한다"""
        analyzer = self._make_analyzer()
        raw = {
            "아반떼": {
                "total_positive": 10,
                "total_negative": 3,
                "total_count": 13,
                "tags": {
                    "외관": {
                        "positive": 5, "negative": 1, "total": 6,
                        "category_name": "외관",
                    },
                    "친절": {
                        "positive": 4, "negative": 1, "total": 5,
                        "category_name": "직원친절",
                    },
                    "가격": {
                        "positive": 1, "negative": 1, "total": 2,
                        "category_name": "가격",
                    },
                },
            },
        }

        top_liked, _ = analyzer.build_vehicle_rankings(raw, [])

        assert len(top_liked) == 1
        avante = top_liked[0]
        tag_texts = " ".join(avante.tags)

        assert "친절" not in tag_texts, "업체 태그가 차량 평가에 포함됨"
        assert "가격" not in tag_texts, "업체 태그가 차량 평가에 포함됨"

    def test_total_counts_include_all_subtags(self):
        """ratio(정렬 기준)는 서브태그 전체의 합산이어야 한다"""
        analyzer = self._make_analyzer()
        raw = self._make_vehicle_tags_raw()

        top_liked, _ = analyzer.build_vehicle_rankings(raw, [])

        k3 = top_liked[0]
        # 서브태그 전체 positive: 차량외관(3)+신차(2)+실내(1) = 6
        assert k3.ratio == 6, f"서브태그 positive 합산이 6이어야 함: {k3.ratio}"

    def test_category_fallback_when_no_subtags(self):
        """서브태그가 없으면 카테고리명으로 fallback해야 한다 (기존 데이터 호환)"""
        analyzer = self._make_analyzer()
        raw = {
            "소나타": {
                "total_positive": 10,
                "total_negative": 3,
                "total_count": 13,
                "tags": {
                    "외관": {
                        "positive": 6, "negative": 1, "total": 7,
                        "category_name": "외관",
                    },
                    "청결": {
                        "positive": 4, "negative": 2, "total": 6,
                        "category_name": "청결",
                    },
                },
            },
        }

        top_liked, _ = analyzer.build_vehicle_rankings(raw, [])

        assert len(top_liked) == 1
        sonata = top_liked[0]
        # name == category_name → 서브태그 없음 → 카테고리 fallback
        assert "외관(6건)" in sonata.tags
        assert "청결(4건)" in sonata.tags

    def test_subtags_preferred_over_categories_in_mixed_data(self):
        """카테고리+서브태그 혼합 시 서브태그만 표시해야 한다"""
        analyzer = self._make_analyzer()
        raw = {
            "그랜저": {
                "total_positive": 12,
                "total_negative": 4,
                "total_count": 16,
                "tags": {
                    "외관": {
                        "positive": 8, "negative": 2, "total": 10,
                        "category_name": "외관",
                    },
                    "차량외관": {
                        "positive": 5, "negative": 1, "total": 6,
                        "category_name": "외관",
                    },
                    "신차": {
                        "positive": 3, "negative": 1, "total": 4,
                        "category_name": "외관",
                    },
                },
            },
        }

        top_liked, _ = analyzer.build_vehicle_rankings(raw, [])

        granger = top_liked[0]
        tag_names = [t.split("(")[0] for t in granger.tags]

        # 서브태그(차량외관, 신차)만 표시, 카테고리(외관)는 제외
        assert "외관" not in tag_names, (
            f"서브태그 존재 시 카테고리는 제외해야 함: {granger.tags}"
        )
        assert "차량외관" in tag_names
        assert "신차" in tag_names
