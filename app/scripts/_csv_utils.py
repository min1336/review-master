"""CSV 로드 공통 유틸리티

import_from_csv.py, run_full_pipeline.py에서 공유하는
HTML 정리 + CSV 로드 + 영어 키 매핑 로직을 모아둔 모듈.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# 리뷰 상태 변환 맵 (한국어 -> 영어)
STATUS_MAP = {
    "정상": "normal",
    "블라인드": "blind",
    "삭제": "deleted",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_null(text: str) -> str:
    """PostgreSQL이 거부하는 null byte(\\x00) 제거"""
    return text.replace("\x00", "") if text else text


def strip_html(text: str) -> str:
    """<br> 등 HTML 태그 + null byte 제거 후 공백 정리"""
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = cleaned.replace("\x00", "")
    # 연속 공백 축소
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _map_row(row: dict) -> dict:
    """CSV 한국어 키 row를 파이프라인용 영어 키 dict로 변환"""
    status_kr = (row.get("리뷰상태") or "").strip()
    status_en = STATUS_MAP.get(status_kr, status_kr)
    content_clean = strip_html(row.get("리뷰내용") or "")

    return {
        "review_id": row.get("리뷰번호", "").strip(),
        "branch_id": row.get("지점번호", "").strip(),
        "content": content_clean,
        "branch_name": (row.get("예약_지점명") or "").strip(),
        "company_name": (row.get("예약_업체명") or "").strip(),
        "rating_service": (row.get("지점평점(친절/편의성)") or "").strip(),
        "rating_car": (row.get("차량평점") or "").strip(),
        "rating_convenience": (row.get("인수/반납편의성") or "").strip(),
        "helpful_count": (row.get("도움돼요수") or "0").strip(),
        "review_date": (row.get("등록일시") or "").strip(),
        "status": status_en,
        "car_type": (row.get("차량모델") or "").strip(),
        "rent_type": (row.get("렌트타입") or "").strip(),
    }


def load_csv(
    path: Path,
    *,
    include_raw: bool = False,
) -> list[dict] | tuple[list[dict], list[dict]]:
    """CSV를 읽어 파이프라인용 영어 키 rows를 반환.

    Args:
        path: CSV 파일 경로
        include_raw: True이면 (raw_rows, mapped_rows) 튜플 반환.
                     raw_rows는 한국어 키 원본 (null byte만 제거).

    Returns:
        include_raw=False: mapped_rows (list[dict])
        include_raw=True:  (raw_rows, mapped_rows)
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV 파일 없음: {path}")

    raw_rows: list[dict] = []
    mapped_rows: list[dict] = []

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if include_raw:
                raw_rows.append(
                    {k: strip_null(v) if isinstance(v, str) else v for k, v in row.items()}
                )
            mapped_rows.append(_map_row(row))

    logger.info("CSV 로드 완료: %d건 (%s)", len(mapped_rows), path.name)

    if include_raw:
        return raw_rows, mapped_rows
    return mapped_rows
