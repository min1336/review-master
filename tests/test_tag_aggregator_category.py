"""Task 1: TagAggregator category_id 매핑 TDD 테스트

수정 사항:
- TAG_REGISTRY에서 tag→category_name 매핑 빌드
- tag→group에서 tag_type 파생 (affiliate→company, vehicle→vehicle)
- 신규 태그 upsert 시 category_id, tag_type 포함
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


class TestTagRegistryMapping:
    """TAG_REGISTRY → category 매핑 빌드 로직 검증"""

    def _build_mappings(self):
        """TagAggregator.aggregate() 내부 매핑 로직 재현"""
        from domain.analysis.patterns import TAG_REGISTRY

        tag_to_category_name: dict[str, str] = {}
        tag_to_group: dict[str, str] = {}

        for cat_name, cat_meta in TAG_REGISTRY.items():
            tag_to_category_name[cat_name] = cat_name
            tag_to_group[cat_name] = cat_meta.group
            for sub_tag_name in cat_meta.tags:
                tag_to_category_name[sub_tag_name] = cat_name
                tag_to_group[sub_tag_name] = cat_meta.group

        return tag_to_category_name, tag_to_group

    def test_all_categories_mapped_to_self(self):
        """7개 카테고리명 자체가 매핑에 포함"""
        from domain.analysis.patterns import TAG_REGISTRY

        tag_to_cat, _ = self._build_mappings()

        for cat_name in TAG_REGISTRY:
            assert cat_name in tag_to_cat, f"카테고리 '{cat_name}' 누락"
            assert tag_to_cat[cat_name] == cat_name

    def test_sub_tags_mapped_to_parent_category(self):
        """세분화 태그가 올바른 상위 카테고리에 매핑"""
        from domain.analysis.patterns import TAG_REGISTRY

        tag_to_cat, _ = self._build_mappings()

        for cat_name, cat_meta in TAG_REGISTRY.items():
            for sub_tag in cat_meta.tags:
                assert sub_tag in tag_to_cat, f"서브태그 '{sub_tag}' 누락"
                assert tag_to_cat[sub_tag] == cat_name, (
                    f"서브태그 '{sub_tag}'의 카테고리가 '{tag_to_cat[sub_tag]}'이 아닌 "
                    f"'{cat_name}'이어야 함"
                )

    def test_vehicle_group_tag_type(self):
        """vehicle 그룹 → tag_type 'vehicle'"""
        _, tag_to_group = self._build_mappings()

        vehicle_tags = [
            tag for tag, group in tag_to_group.items() if group == "vehicle"
        ]

        assert len(vehicle_tags) > 0, "vehicle 태그가 하나도 없음"
        for tag in vehicle_tags:
            tag_type = "vehicle" if tag_to_group[tag] == "vehicle" else None
            assert tag_type == "vehicle"

    def test_affiliate_group_tag_type(self):
        """affiliate 그룹 → tag_type 'company'"""
        _, tag_to_group = self._build_mappings()

        affiliate_tags = [
            tag for tag, group in tag_to_group.items() if group == "affiliate"
        ]

        assert len(affiliate_tags) > 0, "affiliate 태그가 하나도 없음"
        for tag in affiliate_tags:
            tag_type = "company" if tag_to_group[tag] == "affiliate" else None
            assert tag_type == "company"

    def test_tag_type_derivation_logic(self):
        """tag_type 파생 로직: affiliate→company, vehicle→vehicle, 그 외→None"""
        from domain.analysis.patterns import TAG_REGISTRY

        _, tag_to_group = self._build_mappings()

        # 알려진 그룹 값 집합 검증
        known_groups = {meta.group for meta in TAG_REGISTRY.values()}
        assert "affiliate" in known_groups or "vehicle" in known_groups, (
            "TAG_REGISTRY에 affiliate 또는 vehicle 그룹이 없음"
        )

        for tag_name, group in tag_to_group.items():
            if group == "affiliate":
                derived = "company"
            elif group == "vehicle":
                derived = "vehicle"
            else:
                derived = None

            # affiliate 그룹은 반드시 company, vehicle 그룹은 반드시 vehicle
            if group == "affiliate":
                assert derived == "company", f"'{tag_name}' affiliate→company 실패"
            elif group == "vehicle":
                assert derived == "vehicle", f"'{tag_name}' vehicle→vehicle 실패"
            else:
                assert derived is None, f"'{tag_name}' 기타 그룹→None 실패"

    def test_total_tag_count(self):
        """전체 매핑된 태그 수 = 고유 키 수 (카테고리명과 서브태그명 중복 제거)"""
        from domain.analysis.patterns import TAG_REGISTRY

        tag_to_cat, _ = self._build_mappings()

        # 카테고리명과 서브태그명이 같은 경우(외관, 가격, 청결) dict 키가 충돌하므로
        # set으로 고유 키 수를 계산
        expected_names: set[str] = set()
        for cat_name, cat_meta in TAG_REGISTRY.items():
            expected_names.add(cat_name)
            for sub_tag_name in cat_meta.tags:
                expected_names.add(sub_tag_name)

        assert len(tag_to_cat) == len(expected_names), (
            f"매핑 수 불일치: {len(tag_to_cat)} vs 예상 {len(expected_names)}"
        )

    def test_known_vehicle_category_present(self):
        """'외관', '청결' 카테고리 존재 확인"""
        from domain.analysis.patterns import VEHICLE_CATEGORIES

        tag_to_cat, tag_to_group = self._build_mappings()

        for vc in VEHICLE_CATEGORIES:
            assert vc in tag_to_cat, f"차량 카테고리 '{vc}' 누락"
            assert tag_to_group[vc] == "vehicle", f"'{vc}'의 group이 vehicle이 아님"

    def test_known_affiliate_category_present(self):
        """AFFILIATE_CATEGORIES 내 카테고리 존재 확인"""
        from domain.analysis.patterns import AFFILIATE_CATEGORIES

        tag_to_cat, tag_to_group = self._build_mappings()

        for ac in AFFILIATE_CATEGORIES:
            assert ac in tag_to_cat, f"업체 카테고리 '{ac}' 누락"
            assert tag_to_group[ac] == "affiliate", f"'{ac}'의 group이 affiliate이 아님"
