"""n8n 워크플로 스케줄러 관리 엔드포인트

n8n REST API(/api/v1/workflows)를 호출하여 워크플로의
크론 스케줄 변경, 활성화 토글, 수동 실행을 지원한다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from repository.orm_models import BranchSummaryORM, ScheduleGroupORM, SchedulerTargetORM
from schemas.common import ApiResponseModel, api_response

from .deps import get_db_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["n8n-scheduler"])

N8N_BASE = "https://n8n-cloud.carmore.kr"
N8N_API_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=5.0)
SEOUL_TZ = ZoneInfo("Asia/Seoul")

# 관리 대상 워크플로 메타데이터 (webhook 경로는 n8n API에서 반환하지 않음)
MANAGED_WORKFLOWS: dict[str, dict[str, str]] = {
    "3PSt6KzJValjPMO2": {
        "name": "Review Sync Job",
        "webhook": "/review-sync",
        "desc": "리뷰 데이터 동기화",
    },
    "xQTiHwJTH8JTFcn3": {
        "name": "Summary Generation Job",
        "webhook": "/generate-summary",
        "desc": "요약 리포트 생성",
    },
}


# ── 요청 모델 ──────────────────────────────────────────


class ScheduleRequest(BaseModel):
    workflow_id: str
    cron_expression: str


class ToggleRequest(BaseModel):
    workflow_id: str
    active: bool


class TriggerRequest(BaseModel):
    workflow_id: str


class CronValidateRequest(BaseModel):
    expression: str


class GroupCreateRequest(BaseModel):
    group_name: str
    cron_expression: str = "0 6 * * *"
    branch_ids: list[int] = []


class GroupUpdateRequest(BaseModel):
    group_name: str | None = None
    cron_expression: str | None = None
    branch_ids: list[int] | None = None


# ── 내부 헬퍼 ──────────────────────────────────────────


def _get_api_key() -> str:
    from core.config import get_settings

    key = get_settings().n8n_api_key.get_secret_value()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="N8N_API_KEY 환경변수가 설정되지 않았습니다",
        )
    return key


def _api_headers() -> dict[str, str]:
    return {
        "X-N8N-API-KEY": _get_api_key(),
        "Content-Type": "application/json",
    }


def _webhook_prefix() -> str:
    from core.config import get_settings

    return "/webhook-test" if get_settings().n8n_test_mode else "/webhook"


# n8n PUT API에 보내면 안 되는 읽기 전용 필드
# active도 PUT으로 변경 불가 → POST /activate, /deactivate 사용
_READONLY_FIELDS = {
    "id", "createdAt", "updatedAt", "versionId", "activeVersionId",
    "versionCounter", "triggerCount", "shared", "tags",
    "activeVersion", "meta", "isArchived", "active",
    "staticData", "pinData", "description",
}


def _strip_readonly(wf: dict[str, Any]) -> dict[str, Any]:
    """PUT 요청 전 읽기 전용 필드를 제거한다."""
    return {k: v for k, v in wf.items() if k not in _READONLY_FIELDS}


def _extract_cron(workflow: dict[str, Any]) -> str:
    """워크플로의 Schedule Trigger 노드에서 크론 표현식을 추출한다."""
    for node in workflow.get("nodes", []):
        if node.get("type") != "n8n-nodes-base.scheduleTrigger":
            continue
        intervals = (
            node.get("parameters", {}).get("rule", {}).get("interval", [])
        )
        if not intervals:
            continue
        interval = intervals[0]
        field = interval.get("field", "")
        if field == "cronExpression":
            return interval.get("expression", "")
    return ""


def _describe_cron(expr: str) -> str:
    """크론 표현식을 한국어로 설명한다."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return expr

    minute, hour, dom, month, dow = parts
    day_names = {
        "0": "일", "1": "월", "2": "화", "3": "수",
        "4": "목", "5": "금", "6": "토", "7": "일",
    }

    if dom == "*" and month == "*" and dow == "*":
        return f"매일 {hour}시 {minute}분"
    if dom != "*" and month == "*" and dow == "*":
        return f"매월 {dom}일 {hour}시 {minute}분"
    if dom == "*" and month == "*" and dow != "*":
        day = day_names.get(dow, dow)
        return f"매주 {day}요일 {hour}시 {minute}분"

    return expr


def _next_runs(expr: str, count: int = 3) -> list[str]:
    """크론 표현식의 다음 N회 실행 시각을 반환한다 (KST)."""
    try:
        now = datetime.now(SEOUL_TZ)
        cron = croniter(expr, now)
        runs: list[str] = []
        for _ in range(count):
            nxt = cron.get_next(datetime)
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=SEOUL_TZ)
            runs.append(nxt.strftime("%Y-%m-%d %H:%M (KST)"))
        return runs
    except Exception:
        return []


def _validate_workflow_id(workflow_id: str) -> None:
    if workflow_id not in MANAGED_WORKFLOWS:
        raise HTTPException(status_code=404, detail="관리 대상 워크플로가 아닙니다")


# ── API 엔드포인트 ─────────────────────────────────────


@router.get("/workflows", response_model=ApiResponseModel[list])
async def list_scheduler_workflows() -> dict[str, Any]:
    """관리 대상 워크플로 목록 + 현재 스케줄 조회"""

    async def _fetch_workflow(
        client: httpx.AsyncClient, wf_id: str, meta: dict[str, str]
    ) -> dict[str, Any]:
        try:
            resp = await client.get(
                f"{N8N_BASE}/api/v1/workflows/{wf_id}",
                headers=_api_headers(),
            )
            resp.raise_for_status()
            wf = resp.json()
            cron_expr = _extract_cron(wf)
            return {
                "id": wf_id,
                "name": wf.get("name", meta["name"]),
                "description": meta["desc"],
                "active": wf.get("active", False),
                "cron_expression": cron_expr,
                "cron_description": (
                    _describe_cron(cron_expr) if cron_expr else "스케줄 없음"
                ),
                "next_runs": _next_runs(cron_expr) if cron_expr else [],
                "updated_at": wf.get("updatedAt", ""),
            }
        except httpx.HTTPError as e:
            logger.error("n8n workflow fetch failed %s: %s", wf_id, e)
            return {
                "id": wf_id,
                "name": meta["name"],
                "description": meta["desc"],
                "active": None,
                "cron_expression": "",
                "cron_description": "조회 실패",
                "next_runs": [],
                "updated_at": "",
                "error": str(e),
            }

    async with httpx.AsyncClient(timeout=N8N_API_TIMEOUT) as client:
        results = await asyncio.gather(
            *[_fetch_workflow(client, wf_id, meta) for wf_id, meta in MANAGED_WORKFLOWS.items()]
        )

    return api_response(list(results))


@router.post("/schedule", response_model=ApiResponseModel[dict])
async def update_schedule(body: ScheduleRequest) -> dict[str, Any]:
    """워크플로의 크론 스케줄을 변경한다 (read-modify-write)."""
    _validate_workflow_id(body.workflow_id)

    expr = body.cron_expression.strip()
    parts = expr.split()
    if len(parts) != 5:
        raise HTTPException(
            status_code=400,
            detail="크론 표현식은 5개 필드가 필요합니다",
        )
    try:
        croniter(expr)
    except (ValueError, KeyError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 크론 표현식: {e}",
        ) from None

    try:
        async with httpx.AsyncClient(timeout=N8N_API_TIMEOUT) as client:
            # 1) GET 현재 워크플로
            resp = await client.get(
                f"{N8N_BASE}/api/v1/workflows/{body.workflow_id}",
                headers=_api_headers(),
            )
            resp.raise_for_status()
            wf = resp.json()

            # 2) Schedule Trigger 노드 수정
            nodes = wf.get("nodes", [])
            updated = False
            for node in nodes:
                if node.get("type") == "n8n-nodes-base.scheduleTrigger":
                    node["parameters"] = {
                        "rule": {
                            "interval": [
                                {"field": "cronExpression", "expression": expr}
                            ]
                        }
                    }
                    updated = True
                    break

            if not updated:
                raise HTTPException(
                    status_code=400,
                    detail="워크플로에 Schedule Trigger 노드가 없습니다",
                )

            # 3) PUT 업데이트 (n8n API는 PATCH 미지원)
            wf["nodes"] = nodes
            put_resp = await client.put(
                f"{N8N_BASE}/api/v1/workflows/{body.workflow_id}",
                headers=_api_headers(),
                json=_strip_readonly(wf),
            )
            put_resp.raise_for_status()

    except httpx.HTTPError as e:
        logger.error("n8n schedule update failed: %s", e)
        raise HTTPException(
            status_code=502, detail="n8n API 오류가 발생했습니다"
        ) from e

    return api_response({
        "message": f"스케줄이 '{_describe_cron(expr)}'(으)로 변경되었습니다",
        "cron_expression": expr,
        "cron_description": _describe_cron(expr),
        "next_runs": _next_runs(expr),
    })


@router.post("/toggle", response_model=ApiResponseModel[dict])
async def toggle_workflow(body: ToggleRequest) -> dict[str, Any]:
    """워크플로 활성/비활성 토글 (n8n 전용 엔드포인트 사용)"""
    _validate_workflow_id(body.workflow_id)

    action = "activate" if body.active else "deactivate"
    try:
        async with httpx.AsyncClient(timeout=N8N_API_TIMEOUT) as client:
            resp = await client.post(
                f"{N8N_BASE}/api/v1/workflows/{body.workflow_id}/{action}",
                headers=_api_headers(),
            )
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPError as e:
        logger.error("n8n toggle failed: %s", e)
        raise HTTPException(
            status_code=502, detail="n8n API 오류가 발생했습니다"
        ) from e

    status_text = "활성화" if body.active else "비활성화"
    return api_response({
        "message": f"워크플로가 {status_text}되었습니다",
        "active": result.get("active", body.active),
    })


@router.post("/trigger", response_model=ApiResponseModel[dict])
async def trigger_workflow(body: TriggerRequest) -> dict[str, Any]:
    """웹훅을 통해 워크플로를 수동 실행한다."""
    _validate_workflow_id(body.workflow_id)
    meta = MANAGED_WORKFLOWS[body.workflow_id]

    url = f"{N8N_BASE}{_webhook_prefix()}{meta['webhook']}"
    try:
        async with httpx.AsyncClient(timeout=N8N_API_TIMEOUT) as client:
            resp = await client.post(url)
            return api_response({
                "message": "워크플로가 수동 실행되었습니다",
                "status_code": resp.status_code,
            })
    except httpx.TimeoutException as e:
        logger.error("n8n trigger timeout: %s", url)
        raise HTTPException(
            status_code=504, detail="n8n 웹훅 응답 시간 초과"
        ) from e
    except httpx.HTTPError as e:
        logger.error("n8n trigger failed: %s", e)
        raise HTTPException(
            status_code=502, detail="n8n 웹훅 오류가 발생했습니다"
        ) from e


@router.post("/cron/validate", response_model=ApiResponseModel[dict])
async def validate_cron(body: CronValidateRequest) -> dict[str, Any]:
    """크론 표현식을 검증하고 다음 실행 시각을 반환한다."""
    expr = body.expression.strip()
    parts = expr.split()
    if len(parts) != 5:
        return api_response({
            "valid": False,
            "error": f"크론 표현식은 5개 필드가 필요합니다 (현재 {len(parts)}개)",
        })

    try:
        croniter(expr)
    except (ValueError, KeyError) as e:
        return api_response({"valid": False, "error": str(e)})

    return api_response({
        "valid": True,
        "description": _describe_cron(expr),
        "next_runs": _next_runs(expr, 5),
    })


# ── 지점 목록 조회 ────────────────────────────────────


@router.get("/branches", response_model=ApiResponseModel[list])
async def list_available_branches(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """선택 가능한 전체 지점 목록 (branch_summaries 테이블)"""
    stmt = (
        select(
            BranchSummaryORM.branch_id,
            BranchSummaryORM.branch_name,
            BranchSummaryORM.region,
            BranchSummaryORM.review_count,
        )
        .order_by(BranchSummaryORM.branch_name)
    )
    result = await session.execute(stmt)
    rows = [
        {
            "branch_id": r.branch_id,
            "branch_name": r.branch_name,
            "region": r.region,
            "review_count": r.review_count,
        }
        for r in result.all()
    ]
    return api_response(rows)


# ── 스케줄 그룹 관리 엔드포인트 ───────────────────────


async def _resolve_branch_names(
    session: AsyncSession, branch_ids: list[int],
) -> dict[int, str]:
    """branch_id → branch_name 매핑을 반환한다."""
    if not branch_ids:
        return {}
    stmt = (
        select(BranchSummaryORM.branch_id, BranchSummaryORM.branch_name)
        .where(BranchSummaryORM.branch_id.in_(branch_ids))
    )
    result = await session.execute(stmt)
    return {
        r.branch_id: r.branch_name or ""
        for r in result.all()
    }


async def _replace_group_targets(
    session: AsyncSession, group_id: int, workflow_id: str, branch_ids: list[int],
) -> int:
    """그룹의 대상 지점을 교체한다 (ORM). 삽입된 행 수를 반환."""
    await session.execute(
        delete(SchedulerTargetORM).where(SchedulerTargetORM.group_id == group_id)
    )
    if not branch_ids:
        return 0
    name_map = await _resolve_branch_names(session, branch_ids)
    for bid in branch_ids:
        session.add(SchedulerTargetORM(
            workflow_id=workflow_id,
            group_id=group_id,
            branch_id=bid,
            branch_name=name_map.get(bid, ""),
        ))
    await session.flush()
    return len(branch_ids)


def _group_to_dict(group: ScheduleGroupORM) -> dict[str, Any]:
    """ORM 모델을 응답용 dict로 변환한다."""
    return {
        "id": group.id,
        "workflow_id": group.workflow_id,
        "group_name": group.group_name,
        "cron_expression": group.cron_expression,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
        "targets": [
            {"branch_id": t.branch_id, "branch_name": t.branch_name}
            for t in group.targets
        ],
        "target_count": len(group.targets),
        "cron_description": _describe_cron(group.cron_expression),
        "next_runs": _next_runs(group.cron_expression, 3),
    }


@router.get("/groups/{workflow_id}", response_model=ApiResponseModel[list])
async def list_groups(
    workflow_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """워크플로의 스케줄 그룹 목록 + 각 그룹의 대상 지점 조회"""
    _validate_workflow_id(workflow_id)

    stmt = (
        select(ScheduleGroupORM)
        .options(selectinload(ScheduleGroupORM.targets))
        .where(ScheduleGroupORM.workflow_id == workflow_id)
        .order_by(ScheduleGroupORM.created_at)
    )
    result = await session.execute(stmt)
    groups = [_group_to_dict(g) for g in result.scalars().all()]
    return api_response(groups)


@router.post("/groups/{workflow_id}", response_model=ApiResponseModel[dict])
async def create_group(
    workflow_id: str, body: GroupCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """새 스케줄 그룹 생성"""
    _validate_workflow_id(workflow_id)

    group = ScheduleGroupORM(
        workflow_id=workflow_id,
        group_name=body.group_name,
        cron_expression=body.cron_expression,
    )
    session.add(group)
    await session.flush()

    count = await _replace_group_targets(
        session, group.id, workflow_id, body.branch_ids,
    )

    await session.commit()
    return api_response({
        "message": f"'{body.group_name}' 그룹이 생성되었습니다 ({count}개 지점)",
        "group": {
            "id": group.id,
            "workflow_id": group.workflow_id,
            "group_name": group.group_name,
            "cron_expression": group.cron_expression,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        },
    })


@router.put("/groups/{group_id}", response_model=ApiResponseModel[dict])
async def update_group(
    group_id: int, body: GroupUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """스케줄 그룹 수정 (이름, 크론, 대상 지점)"""
    stmt = select(ScheduleGroupORM).where(ScheduleGroupORM.id == group_id)
    result = await session.execute(stmt)
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    if body.group_name is not None:
        group.group_name = body.group_name
    if body.cron_expression is not None:
        group.cron_expression = body.cron_expression

    target_count = None
    if body.branch_ids is not None:
        target_count = await _replace_group_targets(
            session, group_id, group.workflow_id, body.branch_ids,
        )

    await session.commit()

    msg = "그룹이 수정되었습니다"
    if target_count is not None:
        msg += f" ({target_count}개 지점)"

    return api_response({"message": msg})


@router.delete("/groups/{group_id}", response_model=ApiResponseModel[dict])
async def delete_group(
    group_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """스케줄 그룹 삭제 (CASCADE로 대상 지점도 삭제)"""
    stmt = select(ScheduleGroupORM).where(ScheduleGroupORM.id == group_id)
    result = await session.execute(stmt)
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    await session.delete(group)
    await session.commit()
    return api_response({"message": "그룹이 삭제되었습니다"})
