"""Pydantic 스키마 Contract Testing

경계값 분석(BVA), 등가 분할, 유효성 검증, model_validator 동작 확인
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from schemas.report import (
    BatchPdfRequest,
    PromptPresetCreate,
    ReportData,
    ReportOutputConfig,
    ReportDataConfig,
    ReportPromptConfig,
    ReportRequest,
    ResolvedReportConfig,
    VALID_FOCUS_AREAS,
)


# ── ReportOutputConfig BVA ────────────────────────────


class TestReportOutputConfigBoundary:
    """Boundary Value Analysis: summary_max_length, eval_max_length"""

    def test_summary_max_length_min_boundary(self):
        cfg = ReportOutputConfig(summary_max_length=150)
        assert cfg.summary_max_length == 150

    def test_summary_max_length_below_min_rejected(self):
        with pytest.raises(ValidationError):
            ReportOutputConfig(summary_max_length=149)

    def test_summary_max_length_max_boundary(self):
        cfg = ReportOutputConfig(summary_max_length=1000)
        assert cfg.summary_max_length == 1000

    def test_summary_max_length_above_max_rejected(self):
        with pytest.raises(ValidationError):
            ReportOutputConfig(summary_max_length=1001)

    def test_eval_max_length_min_boundary(self):
        cfg = ReportOutputConfig(eval_max_length=100)
        assert cfg.eval_max_length == 100

    def test_eval_max_length_below_min_rejected(self):
        with pytest.raises(ValidationError):
            ReportOutputConfig(eval_max_length=99)

    def test_eval_max_length_max_boundary(self):
        cfg = ReportOutputConfig(eval_max_length=400)
        assert cfg.eval_max_length == 400

    def test_eval_max_length_above_max_rejected(self):
        with pytest.raises(ValidationError):
            ReportOutputConfig(eval_max_length=401)


# ── ReportDataConfig BVA ──────────────────────────────


class TestReportDataConfigBoundary:
    def test_sample_review_count_min(self):
        cfg = ReportDataConfig(sample_review_count=5)
        assert cfg.sample_review_count == 5

    def test_sample_review_count_below_min(self):
        with pytest.raises(ValidationError):
            ReportDataConfig(sample_review_count=4)

    def test_sample_review_count_max(self):
        cfg = ReportDataConfig(sample_review_count=20)
        assert cfg.sample_review_count == 20

    def test_sample_review_count_above_max(self):
        with pytest.raises(ValidationError):
            ReportDataConfig(sample_review_count=21)


# ── ReportPromptConfig 등가분할 + Validator ───────────


class TestReportPromptConfigPartitioning:
    """Equivalence Partitioning: focus_areas 유효/무효 분할"""

    def test_valid_focus_areas_kept(self):
        cfg = ReportPromptConfig(focus_areas=["직원친절", "청결", "가격"])
        assert cfg.focus_areas == ["직원친절", "청결", "가격"]

    def test_invalid_focus_areas_filtered(self):
        cfg = ReportPromptConfig(focus_areas=["직원친절", "존재하지않는태그"])
        assert cfg.focus_areas == ["직원친절"]

    def test_all_invalid_becomes_empty(self):
        cfg = ReportPromptConfig(focus_areas=["invalid1", "invalid2"])
        assert cfg.focus_areas == []

    def test_empty_focus_areas(self):
        cfg = ReportPromptConfig(focus_areas=[])
        assert cfg.focus_areas == []

    def test_all_valid_focus_areas(self):
        cfg = ReportPromptConfig(focus_areas=VALID_FOCUS_AREAS.copy())
        assert len(cfg.focus_areas) == len(VALID_FOCUS_AREAS)

    def test_temperature_boundary_zero(self):
        cfg = ReportPromptConfig(temperature=0.0)
        assert cfg.temperature == 0.0

    def test_temperature_boundary_one(self):
        cfg = ReportPromptConfig(temperature=1.0)
        assert cfg.temperature == 1.0

    def test_temperature_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            ReportPromptConfig(temperature=-0.1)

    def test_temperature_above_one_rejected(self):
        with pytest.raises(ValidationError):
            ReportPromptConfig(temperature=1.1)

    def test_custom_instruction_stripped(self):
        cfg = ReportPromptConfig(custom_instruction="  test  ")
        assert cfg.custom_instruction == "test"

    def test_custom_instruction_max_length(self):
        cfg = ReportPromptConfig(custom_instruction="a" * 500)
        assert len(cfg.custom_instruction) == 500

    def test_custom_instruction_over_max_rejected(self):
        with pytest.raises(ValidationError):
            ReportPromptConfig(custom_instruction="a" * 501)

    @pytest.mark.parametrize("perspective", [
        "operational", "marketing", "executive",
        "customer_service", "investor", "comparative",
    ])
    def test_valid_analysis_perspectives(self, perspective):
        cfg = ReportPromptConfig(analysis_perspective=perspective)
        assert cfg.analysis_perspective == perspective

    def test_invalid_analysis_perspective_rejected(self):
        with pytest.raises(ValidationError):
            ReportPromptConfig(analysis_perspective="invalid")

    @pytest.mark.parametrize("tone", [
        "analytical", "friendly", "formal",
        "concise", "data_driven", "narrative",
    ])
    def test_valid_tones(self, tone):
        cfg = ReportPromptConfig(tone=tone)
        assert cfg.tone == tone


# ── ResolvedReportConfig model_validator ──────────────


class TestResolvedReportConfigValidator:
    """model_validator: 불가능 조합 자동 보정 검증"""

    def test_affiliate_eval_forces_tags_on(self):
        cfg = ResolvedReportConfig(
            output=ReportOutputConfig(include_affiliate_eval=True),
            data=ReportDataConfig(include_tags=False),
        )
        assert cfg.data.include_tags is True

    def test_vehicle_eval_forces_vehicles_on(self):
        cfg = ResolvedReportConfig(
            output=ReportOutputConfig(include_vehicle_eval=True),
            data=ReportDataConfig(include_vehicles=False),
        )
        assert cfg.data.include_vehicles is True

    def test_no_eval_respects_data_off(self):
        cfg = ResolvedReportConfig(
            output=ReportOutputConfig(
                include_affiliate_eval=False,
                include_vehicle_eval=False,
            ),
            data=ReportDataConfig(include_tags=False, include_vehicles=False),
        )
        assert cfg.data.include_tags is False
        assert cfg.data.include_vehicles is False


# ── ReportData 하위호환 validator ─────────────────────


class TestReportDataMigration:
    def test_top_keywords_migrated_to_top_tags(self):
        data = ReportData(
            branch_id=1,
            branch_name="테스트지점",
            affiliate_name="테스트업체",
            period_start="2026-01-01",
            period_end="2026-03-01",
            top_keywords=["친절", "깨끗"],
        )
        assert data.top_tags == ["친절", "깨끗"]

    def test_top_tags_used_directly(self):
        data = ReportData(
            branch_id=1,
            branch_name="테스트지점",
            affiliate_name="테스트업체",
            period_start="2026-01-01",
            period_end="2026-03-01",
            top_tags=["친절"],
        )
        assert data.top_tags == ["친절"]


# ── BatchPdfRequest BVA ───────────────────────────────


class TestBatchPdfRequestBoundary:
    def test_min_branch_ids(self):
        req = BatchPdfRequest(
            branch_ids=[1],
            start_date="2026-01-01",
            end_date="2026-03-01",
        )
        assert len(req.branch_ids) == 1

    def test_max_branch_ids(self):
        req = BatchPdfRequest(
            branch_ids=[1, 2, 3, 4, 5],
            start_date="2026-01-01",
            end_date="2026-03-01",
        )
        assert len(req.branch_ids) == 5

    def test_empty_branch_ids_rejected(self):
        with pytest.raises(ValidationError):
            BatchPdfRequest(
                branch_ids=[],
                start_date="2026-01-01",
                end_date="2026-03-01",
            )

    def test_over_max_branch_ids_rejected(self):
        with pytest.raises(ValidationError):
            BatchPdfRequest(
                branch_ids=[1, 2, 3, 4, 5, 6],
                start_date="2026-01-01",
                end_date="2026-03-01",
            )


# ── PromptPresetCreate BVA ────────────────────────────


class TestPromptPresetCreateBoundary:
    def test_name_min_length(self):
        preset = PromptPresetCreate(name="A")
        assert preset.name == "A"

    def test_name_empty_rejected(self):
        with pytest.raises(ValidationError):
            PromptPresetCreate(name="")

    def test_name_max_length(self):
        preset = PromptPresetCreate(name="A" * 100)
        assert len(preset.name) == 100

    def test_name_over_max_rejected(self):
        with pytest.raises(ValidationError):
            PromptPresetCreate(name="A" * 101)

    def test_focus_areas_filtered(self):
        preset = PromptPresetCreate(
            name="test",
            focus_areas=["직원친절", "invalid"],
        )
        assert preset.focus_areas == ["직원친절"]

# ── ReportRequest.to_resolved_config ──────────────────


class TestReportRequestResolve:
    def test_defaults_when_none(self):
        req = ReportRequest(start_date="2026-01-01", end_date="2026-03-01")
        cfg = req.to_resolved_config()
        assert cfg.output.summary_max_length == 300
        assert cfg.data.sample_review_count == 10
        assert cfg.prompt.temperature == 0.5

    def test_custom_config_preserved(self):
        req = ReportRequest(
            start_date="2026-01-01",
            end_date="2026-03-01",
            output_config=ReportOutputConfig(summary_max_length=500),
            prompt_config=ReportPromptConfig(temperature=0.8),
        )
        cfg = req.to_resolved_config()
        assert cfg.output.summary_max_length == 500
        assert cfg.prompt.temperature == 0.8
