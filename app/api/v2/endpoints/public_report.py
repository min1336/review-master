"""Public Report API v2 — HTML 렌더링 완료 응답

외부 프론트엔드 연동 플로우:
  1. POST /public/v2/report/{branch_id}/generate  → job_id 반환
  2. GET  /public/v2/report/{branch_id}/job/{job_id}  → 진행률 폴링
  3. GET  /public/v2/report/{branch_id}  → 완성된 HTML 리포트
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from core.timezone import date_to_utc
from schemas.common import ApiResponseModel, api_response, validate_date_range_d
from schemas.report import ReportRequest
from services.report_job_service import ReportJobService
from services.report_service import ReportService

from api.v1.endpoints.deps import get_report_job_service, get_report_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public-report-v2"])

# 태그명 → 사람이 읽을 수 있는 문장 매핑
_TAG_SENTENCE_MAP: dict[str, dict[str, str]] = {
    "직원친절": {"positive": "직원이 친절함", "negative": "직원이 불친절함"},
    "사고 처리": {"positive": "사고 처리를 잘해줌", "negative": "사고 처리를 잘 못해줌"},
    "배달/배차": {"positive": "배달/배차가 우수함", "negative": "배달/배차가 별로임"},
    "반납/픽업": {"positive": "반납/픽업이 원활함", "negative": "반납/픽업이 불편함"},
    "위치/접근성": {"positive": "위치/접근성이 좋음", "negative": "위치/접근성이 불편함"},
    "가격": {"positive": "가격이 저렴함", "negative": "가격이 비쌈"},
    "주유비": {"positive": "주유비 부담 없음", "negative": "주유비 부담 있음"},
    "외관": {"positive": "차량 외관이 좋음", "negative": "차량 외관이 안좋음"},
    "청결": {"positive": "차량이 청결함", "negative": "차량이 불결함"},
}


def _esc(text: str) -> str:
    """HTML 특수문자 이스케이프"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_tag_list_html(tags, sentiment: str) -> str:
    """태그 리스트 → HTML 문자열"""
    if not tags:
        return '<div style="color:#71717a;font-size:13px">데이터 부족</div>'
    color = "#dc2626" if sentiment == "negative" else "#16a34a"
    lines = []
    for i, t in enumerate(tags):
        tag_name = t.tag_name if hasattr(t, "tag_name") else t.get("tag_name", "")
        count = t.count if hasattr(t, "count") else t.get("count", 0)
        sentence = _TAG_SENTENCE_MAP.get(tag_name, {}).get(sentiment, tag_name)
        lines.append(
            f'<div style="color:#3f3f46;font-size:13px;padding:3px 0">'
            f'{i + 1}. {_esc(sentence)} '
            f'<span style="color:{color}">{count}건</span>'
            f'</div>'
        )
    return "".join(lines)


def _build_vehicle_list_html(vehicles, sentiment: str) -> str:
    """차량 리스트 → HTML 문자열"""
    if not vehicles:
        return '<div style="color:#71717a;font-size:13px">데이터 부족</div>'
    tag_color = "#dc2626" if sentiment == "disliked" else "#16a34a"
    lines = []
    for i, v in enumerate(vehicles):
        model = v.model if hasattr(v, "model") else v.get("model", "")
        tags = (v.tags if hasattr(v, "tags") else v.get("tags", []))[:3]
        tag_spans = ", ".join(
            f'<span style="color:{tag_color}">{_esc(t)}</span>' for t in tags
        )
        tag_part = f" {tag_spans}" if tags else ""
        lines.append(
            f'<div style="color:#3f3f46;font-size:13px;padding:3px 0">'
            f'{i + 1}. {_esc(model)}{tag_part}'
            f'</div>'
        )
    return "".join(lines)


def _render_report_html(report) -> str:
    """ReportData → 완성된 HTML 문자열 (인라인 스타일 포함)"""
    data = report
    parts: list[str] = []

    # 래퍼 시작
    parts.append('<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;color:#18181b;line-height:1.6">')

    # 1. 분석 기간
    parts.append(
        f'<div style="margin-bottom:16px">'
        f'<span style="font-size:13px;color:#71717a">분석 기간: {_esc(data.period_start)} ~ {_esc(data.period_end)}</span>'
        f'</div>'
    )

    # 2. 요약
    summary_text = data.period_summary or "요약 정보가 없습니다."
    parts.append(
        f'<div style="margin-bottom:24px;padding:20px;background:#fafafa;border-radius:12px">'
        f'<div style="font-size:15px;font-weight:700;color:#18181b;margin-bottom:16px">요약</div>'
        f'<div style="background:white;padding:16px;border-radius:10px;border-left:4px solid #0d6ffc;line-height:1.7;font-size:14px">'
        f'{_esc(summary_text)}'
        f'</div></div>'
    )

    # 3. 업체 평가
    aff = data.affiliate_evaluation
    pos_html = _build_tag_list_html(aff.top_positive if aff else [], "positive")
    neg_html = _build_tag_list_html(aff.top_negative if aff else [], "negative")
    parts.append(
        f'<div style="margin-bottom:24px;padding:20px;background:#fafafa;border-radius:12px">'
        f'<div style="font-size:15px;font-weight:700;color:#18181b;margin-bottom:16px">업체 평가</div>'
        f'<div style="display:flex;gap:16px">'
        f'<div style="flex:1;background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.2);border-radius:8px;padding:12px">'
        f'<div style="font-weight:600;color:#16a34a;margin-bottom:8px;font-size:13px">잘한점</div>'
        f'{pos_html}'
        f'</div>'
        f'<div style="flex:1;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:12px">'
        f'<div style="font-weight:600;color:#dc2626;margin-bottom:8px;font-size:13px">개선점</div>'
        f'{neg_html}'
        f'</div></div></div>'
    )

    # 4. 차량 평가
    veh = data.vehicle_evaluation
    liked_html = _build_vehicle_list_html(veh.top_liked if veh else [], "liked")
    disliked_html = _build_vehicle_list_html(veh.top_disliked if veh else [], "disliked")
    parts.append(
        f'<div style="margin-bottom:24px;padding:20px;background:#fafafa;border-radius:12px">'
        f'<div style="font-size:15px;font-weight:700;color:#18181b;margin-bottom:16px">차량 평가</div>'
        f'<div style="display:flex;gap:16px">'
        f'<div style="flex:1;background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.2);border-radius:8px;padding:12px">'
        f'<div style="font-weight:600;color:#16a34a;margin-bottom:8px;font-size:13px">칭찬 차량</div>'
        f'{liked_html}'
        f'</div>'
        f'<div style="flex:1;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:12px">'
        f'<div style="font-weight:600;color:#dc2626;margin-bottom:8px;font-size:13px">불만 차량</div>'
        f'{disliked_html}'
        f'</div></div></div>'
    )

    # 5. 벤치마크
    bm = data.benchmark
    if bm:
        region_label = _esc(bm.region_name or "지역")
        bm_section = (
            f'<div style="margin-bottom:24px;padding:20px;background:#fafafa;border-radius:12px">'
            f'<div style="font-size:15px;font-weight:700;color:#18181b;margin-bottom:16px">벤치마크</div>'
            f'<div style="display:flex;gap:12px">'
            f'<div style="flex:1;background:#f4f4f5;border-radius:8px;padding:14px;text-align:center">'
            f'<div style="font-size:12px;color:#71717a;margin-bottom:6px">이 지점</div>'
            f'<div style="font-size:22px;font-weight:700;color:#f59e0b">{bm.branch_rating:.1f}</div>'
            f'</div>'
            f'<div style="flex:1;background:#f4f4f5;border-radius:8px;padding:14px;text-align:center">'
            f'<div style="font-size:12px;color:#71717a;margin-bottom:6px">{region_label} 평균</div>'
            f'<div style="font-size:22px;font-weight:700;color:#3f3f46">{bm.regional_avg_rating:.1f}</div>'
            f'<div style="font-size:11px;color:#71717a;margin-top:2px">상위 {bm.regional_rank_pct}% ({bm.total_branches_in_region}개 지점)</div>'
            f'</div></div>'
        )
        if bm.branch_rating > 0:
            is_above = bm.branch_rating >= bm.regional_avg_rating
            if is_above:
                msg = f"이 지점은 {region_label} 평균 이상의 평점을 유지하고 있습니다."
                msg_bg, msg_border = "rgba(16,185,129,0.06)", "rgba(16,185,129,0.2)"
            else:
                msg = f"이 지점은 {region_label} 평균보다 낮은 평점이므로, 개선 조치가 필요할 수 있습니다."
                msg_bg, msg_border = "rgba(239,68,68,0.06)", "rgba(239,68,68,0.2)"
            bm_section += (
                f'<div style="margin-top:12px;background:{msg_bg};border:1px solid {msg_border};'
                f'border-radius:8px;padding:10px 14px;font-size:13px;color:#3f3f46">{msg}</div>'
            )
        bm_section += '</div>'
        parts.append(bm_section)

    # 6. 부정 리뷰 목록
    if data.negative_reviews:
        th_style = 'text-align:center;padding:4px 2px;font-size:10px;color:#52525b;border-bottom:2px solid #e4e4e7;white-space:nowrap'
        rows_html = []
        for r in data.negative_reviews:
            content = _esc((r.content or "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n"))
            td_r = 'padding:4px 2px;font-size:10px;color:#dc2626;text-align:center;border-bottom:1px solid #e4e4e7;white-space:nowrap'
            rows_html.append(
                f'<tr>'
                f'<td style="padding:4px 4px;font-size:10px;color:#52525b;border-bottom:1px solid #e4e4e7;white-space:nowrap">{_esc(r.review_date or "")}</td>'
                f'<td style="{td_r}">{r.rating or ""}</td>'
                f'<td style="{td_r}">{r.rating_car or ""}</td>'
                f'<td style="{td_r}">{r.rating_convenience or ""}</td>'
                f'<td style="padding:4px 4px;font-size:10px;color:#52525b;border-bottom:1px solid #e4e4e7;max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_esc(r.vehicle_model or "-")}</td>'
                f'<td style="padding:4px 6px;font-size:12px;color:#3f3f46;border-bottom:1px solid #e4e4e7;line-height:1.5;white-space:pre-line">{content}</td>'
                f'</tr>'
            )
        parts.append(
            f'<div style="margin-bottom:24px;padding:20px;background:#fafafa;border-radius:12px">'
            f'<div style="font-size:15px;font-weight:700;color:#18181b;margin-bottom:16px">부정 리뷰 목록</div>'
            f'<table style="width:100%;border-collapse:collapse;table-layout:fixed">'
            f'<thead><tr>'
            f'<th style="{th_style};width:80px;text-align:left;padding:4px 4px">날짜</th>'
            f'<th style="{th_style};width:34px">서비스</th>'
            f'<th style="{th_style};width:28px">차량</th>'
            f'<th style="{th_style};width:28px">편의</th>'
            f'<th style="{th_style};width:90px;text-align:left;padding:4px 4px">차량모델</th>'
            f'<th style="{th_style};text-align:left;padding:4px 4px">리뷰 내용</th>'
            f'</tr></thead>'
            f'<tbody>{"".join(rows_html)}</tbody>'
            f'</table></div>'
        )

    # 7. 푸터
    generated = _esc(data.generated_at or "")
    parts.append(
        f'<div style="text-align:center;padding:8px 0;color:#71717a;font-size:12px;margin-top:16px;'
        f'border-top:1px solid #e4e4e7;padding-top:16px">'
        f'Generated by Carmore AI \u00B7 {generated}'
        f'</div>'
    )

    # 래퍼 종료
    parts.append('</div>')
    return "".join(parts)


# ============================================================
# 엔드포인트
# ============================================================


@router.get("/{branch_id}", response_model=ApiResponseModel[dict])
async def api_get_public_report_v2(
    branch_id: int,
    start_date: date = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """AI 리포트 조회 — 완성된 HTML 반환

    프론트엔드는 html 필드를 컨테이너에 넣기만 하면 됩니다.
    인라인 스타일 포함이라 별도 CSS 불필요.
    """
    validate_date_range_d(start_date, end_date)

    try:
        report, _is_new = await service.get_or_generate_report(
            branch_id=branch_id,
            start_date=date_to_utc(start_date),
            end_date=date_to_utc(end_date, end_of_day=True),
        )

        return api_response({
            "branch_id": report.branch_id,
            "branch_name": report.branch_name,
            "affiliate_name": report.affiliate_name,
            "total_reviews": report.total_reviews,
            "html": _render_report_html(report),
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{branch_id}/generate", status_code=202, response_model=ApiResponseModel[dict])
async def api_public_generate_report_v2(
    branch_id: int,
    data: ReportRequest,
    job_service: ReportJobService = Depends(get_report_job_service),
) -> dict[str, Any]:
    """AI 리포트 비동기 생성 요청

    즉시 job_id를 반환합니다. GET /job/{job_id}로 진행률을 폴링하세요.
    완료 후 GET /{branch_id}로 리포트를 조회할 수 있습니다.
    """
    validate_date_range_d(data.start_date, data.end_date)

    report_config = data.to_resolved_config()
    job_id = await job_service.submit_job(
        branch_id=branch_id,
        start_date=date_to_utc(data.start_date),
        end_date=date_to_utc(data.end_date, end_of_day=True),
        report_config=report_config,
    )
    return api_response({
        "job_id": job_id,
        "poll_url": f"/public/v2/report/{branch_id}/job/{job_id}",
    })


@router.get("/{branch_id}/job/{job_id}", response_model=ApiResponseModel[dict])
async def api_public_job_status_v2(
    branch_id: int,
    job_id: UUID = Path(..., description="작업 UUID"),
    job_service: ReportJobService = Depends(get_report_job_service),
) -> dict[str, Any]:
    """리포트 생성 작업 상태 조회 (폴링용)

    status: "processing" | "completed" | "failed"
    progress: 0~100
    """
    job_status = await job_service.get_job_status(str(job_id), branch_id=branch_id)

    if not job_status:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    return api_response(job_status)
