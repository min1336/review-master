from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from schemas.common import ApiResponseModel, api_response
from schemas.jobs import (
    MarkReadRequest,
    ReviewInput,
    SyncRequest,
)

from .deps import (
    get_realtime_pipeline,
    get_sync_job_service,
    get_sync_service,
    get_upload_job_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])
realtime_router = APIRouter(tags=["realtime"])
upload_router = APIRouter(tags=["upload"])


@router.post("/reviews", status_code=202, response_model=ApiResponseModel[dict])
async def api_sync_reviews(
    body: SyncRequest | None = None,
    service=Depends(get_sync_job_service),
) -> dict[str, Any]:
    """비동기 리뷰 동기화 작업 제출 (날짜 범위 지정 가능)"""
    if body is None:
        body = SyncRequest()
    result = await service.submit_job(
        date_from=body.date_from,
        date_to=body.date_to,
    )
    return api_response(result.model_dump(mode="json"))


@router.get("/jobs/{job_id}", response_model=ApiResponseModel[dict])
async def api_get_sync_job_status(
    job_id: str,
    service=Depends(get_sync_job_service),
) -> dict[str, Any]:
    """동기화 작업 상태 조회"""
    result = service.get_job_status(job_id)

    if not result:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")

    return api_response(result.model_dump(mode="json"))


@router.delete("/jobs/{job_id}", response_model=ApiResponseModel[dict])
async def api_cancel_sync_job(
    job_id: str,
    service=Depends(get_sync_job_service),
) -> dict[str, Any]:
    """동기화 작업 취소"""
    cancelled = await service.cancel_job(job_id)

    if not cancelled:
        raise HTTPException(status_code=404, detail="취소할 수 있는 작업이 없습니다")

    return api_response({"message": "작업이 취소되었습니다"})


@router.post("/reviews/cleanup-ghosts", status_code=202, response_model=ApiResponseModel[dict])
async def api_cleanup_ghost_reviews(
    service=Depends(get_sync_job_service),
) -> dict[str, Any]:
    """Athena 비활성 ghost review 일괄 정리 (관리자용, 백그라운드)

    로컬 DB에만 존재하고 Athena에서 비활성(status!=1)인 리뷰를 삭제한다.
    백그라운드로 실행되며 GET /sync/jobs/{job_id}로 상태 폴링.
    """
    result = await service.submit_cleanup_job()
    return api_response(result.model_dump(mode="json"))


@router.post("/reviews/read", response_model=ApiResponseModel[dict])
async def api_mark_reviews_as_read(
    request: MarkReadRequest,
    sync_service=Depends(get_sync_service),
) -> dict[str, Any]:
    """리뷰 읽음 처리"""
    marked_count = await sync_service.mark_reviews_as_read(request.review_ids)
    return api_response({
        "marked_count": marked_count,
    })


# ============================================================
# Realtime (별도 prefix /realtime 로 등록)
# ============================================================


@realtime_router.post("/process", response_model=ApiResponseModel[dict])
async def api_process_review(
    review: ReviewInput,
    pipeline=Depends(get_realtime_pipeline),
) -> dict[str, Any]:
    """
    리뷰 1개 실시간 처리

    - 내용이 있으면: 형태소 분석 → 태그 매핑 → 감정 분석
    - 내용이 없으면: 별점으로만 감정 판단
    - 결과를 DB에 증분 저장
    """
    result = await pipeline.process(review.model_dump())

    return api_response({
        "branch_id": result.branch_id,
        "sentiment": result.sentiment,
        "tags": result.tags,
        "saved": result.saved,
        "error": result.error,
    })


# ============================================================
# Upload (별도 prefix /upload 로 등록)
# ============================================================

# 파일 크기 제한 (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".xlsx", ".csv"}


def _get_extension(filename: str | None) -> str:
    """파일 확장자 추출 (소문자)"""
    if not filename:
        return ""
    dot_idx = filename.rfind(".")
    if dot_idx == -1:
        return ""
    return filename[dot_idx:].lower()


@upload_router.post("/reviews", status_code=202, response_model=ApiResponseModel[dict])
async def api_upload_reviews(
    file: UploadFile,
    service=Depends(get_upload_job_service),
) -> dict[str, Any]:
    """엑셀/CSV 파일 업로드 → 비동기 파이프라인 처리

    multipart/form-data로 .xlsx 또는 .csv 파일을 업로드하면,
    기존 UnifiedPipeline을 통해 리뷰 분석을 비동기로 실행합니다.

    Returns:
        202 + job_id: 폴링으로 진행 상태 확인 가능
    """
    from services.upload_job_service import (
        parse_csv_content,
        parse_excel_content,
        parse_rows,
        validate_columns,
    )

    # 1. 확장자 검증
    ext = _get_extension(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다: '{ext}'. "
            f"허용: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # 2. 파일 크기 사전 검증 (메모리 로드 전 차단)
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                f"파일 크기 초과: "
                f"{file.size / 1024 / 1024:.1f}MB "
                f"(최대: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB)"
            ),
        )

    # 3. 파일 읽기 + 크기 재검증
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                f"파일 크기 초과: "
                f"{len(content) / 1024 / 1024:.1f}MB "
                f"(최대: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB)"
            ),
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="빈 파일입니다")

    # 4. 파싱 (파싱 후 content 해제로 메모리 절약)
    try:
        if ext == ".csv":
            raw_dicts = parse_csv_content(content)
        else:
            raw_dicts = parse_excel_content(content)
        del content
    except Exception as e:
        logger.warning("파일 파싱 실패: %s (%s)", file.filename, e)
        raise HTTPException(
            status_code=400,
            detail=f"파일 파싱에 실패했습니다: {e!s}",
        ) from e

    # 5. 필수 컬럼 검증
    col_error = validate_columns(raw_dicts)
    if col_error:
        raise HTTPException(status_code=422, detail=col_error)

    # 6. 한글→영문 매핑 + 행별 검증
    raw_rows, mapped_rows, row_errors = parse_rows(raw_dicts)

    if not raw_rows:
        error_summary = "; ".join(e.error for e in row_errors[:5])
        raise HTTPException(
            status_code=422,
            detail=f"유효한 데이터가 없습니다. 오류: {error_summary}",
        )

    # 7. 비동기 작업 제출
    result = await service.submit_job(
        raw_rows=raw_rows,
        mapped_rows=mapped_rows,
        total_rows=len(raw_dicts),
        filename=file.filename or "unknown",
    )
    return api_response(result.model_dump(mode="json"))


@upload_router.get("/jobs/{job_id}", response_model=ApiResponseModel[dict])
async def api_get_upload_job_status(
    job_id: str,
    service=Depends(get_upload_job_service),
) -> dict[str, Any]:
    """업로드 작업 상태 조회"""
    result = service.get_job_status(job_id)

    if not result:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")

    return api_response(result.model_dump(mode="json"))


@upload_router.delete("/jobs/{job_id}", response_model=ApiResponseModel[dict])
async def api_cancel_upload_job(
    job_id: str,
    service=Depends(get_upload_job_service),
) -> dict[str, Any]:
    """업로드 작업 취소"""
    cancelled = await service.cancel_job(job_id)

    if not cancelled:
        raise HTTPException(status_code=404, detail="취소할 수 있는 작업이 없습니다")

    return api_response({"message": "작업이 취소되었습니다"})
