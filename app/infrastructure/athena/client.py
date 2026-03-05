"""AWS Athena 클라이언트"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config as BotoConfig

from core.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_athena import AthenaClient as AthenaClientType

logger = logging.getLogger(__name__)

# 캐시 TTL (초)
_CACHE_TTL = 300  # 5분


# 리뷰 조회 쿼리 (원본 테이블 직접 JOIN - 파트너스/JEJU_API/GLOBAL_API 전체 지원)
REVIEW_QUERY = """
SELECT
    nrl.serial              AS review_id,
    nrl.reservation_idx     AS reservation_id,
    nrl.nrl_user_index      AS user_index,
    nrl.company_serial      AS company_id,
    nrl.branch_serial       AS branch_id,
    r."예약_업체명"         AS company_name,
    b."예약_지점명"         AS branch_name,
    b."주소"                AS address,
    nrl.branch_evaluation   AS rating_service,
    nrl.car_evaluation      AS rating_car,
    nrl.take_evaluation     AS rating_convenience,
    nrl.opinion             AS content,
    CASE TRY_CAST(nrl.include_bad_word AS INTEGER) WHEN 1 THEN true ELSE false END AS has_profanity,
    nrl.nrl_recommend       AS helpful_count,
    nrl.register_date       AS review_date,
    nrl.status              AS status,
    CASE TRY_CAST(nrl.nrl_affiliate_type AS INTEGER)
        WHEN 1 THEN '파트너스'
        WHEN 2 THEN 'JEJU_API'
        WHEN 3 THEN 'GLOBAL_API'
    END                     AS affiliate_type,
    r."차종"                AS car_type,
    r."차량모델"            AS car_model,
    r.rentType              AS rent_type
FROM carmore.new_review_list nrl
LEFT JOIN (
    -- 예약 정보 서브쿼리: 파트너스
    SELECT
        CAST(trl.f_reservationidx AS VARCHAR) AS reservationNumber,
        nrc.name AS "예약_업체명",
        CASE TRY_CAST(trl.trl_car_type_flag AS INTEGER)
            WHEN 0 THEN '경형'
            WHEN 1 THEN '소형'
            WHEN 2 THEN '준중형'
            WHEN 3 THEN '중형'
            WHEN 4 THEN '대형'
            WHEN 5 THEN '수입'
            WHEN 6 THEN 'RV'
            WHEN 7 THEN 'SUV'
            ELSE NULL
        END AS "차종",
        trl.trl_car_model AS "차량모델",
        CASE TRY_CAST(trl.reserv_rent_type AS INTEGER)
            WHEN 1 THEN 'SHORT'
            WHEN 2 THEN 'MONTH'
            ELSE 'SUBSCRIPTION'
        END AS rentType
    FROM carmore.tbl_reservation_list trl
    INNER JOIN carmore.new_rentCompany nrc
        ON trl.company_serial = nrc.serial

    UNION ALL

    -- 예약 정보 서브쿼리: JEJU_API
    SELECT
        CAST(wari_reserv_idx AS VARCHAR) AS reservationNumber,
        waa_name AS "예약_업체명",
        CASE TRY_CAST(wari.wari_car_type_flag AS INTEGER)
            WHEN 0 THEN '경형'
            WHEN 1 THEN '소형'
            WHEN 2 THEN '준중형'
            WHEN 3 THEN '중형'
            WHEN 4 THEN '대형'
            WHEN 5 THEN '수입'
            WHEN 6 THEN 'RV'
            WHEN 7 THEN 'SUV'
            ELSE NULL
        END AS "차종",
        wari.wari_car_name AS "차량모델",
        CASE
            WHEN date_diff('day', wari.wari_rental_start, wari.wari_rental_end) < 15 THEN 'SHORT'
            WHEN date_diff('day', wari.wari_rental_start, wari.wari_rental_end) < 30 THEN 'MONTH'
            ELSE 'SUBSCRIPTION'
        END AS rentType
    FROM carmore.workspace_api_reservation_inventory wari
    INNER JOIN carmore.workspace_api_affiliate
        ON wari_waa_idx = waa_idx

    UNION ALL

    -- 예약 정보 서브쿼리: GLOBAL_API
    SELECT
        CAST(cgar_reservation_number AS VARCHAR) AS reservationNumber,
        cgaa_name AS "예약_업체명",
        CASE TRY_CAST(cim.carinfomst_type AS INTEGER)
            WHEN 0 THEN '경형'
            WHEN 1 THEN '소형'
            WHEN 2 THEN '준중형'
            WHEN 3 THEN '중형'
            WHEN 4 THEN '대형'
            WHEN 5 THEN '수입'
            WHEN 6 THEN 'RV'
            WHEN 7 THEN 'SUV'
            ELSE NULL
        END AS "차종",
        cim.carinfomst_name AS "차량모델",
        CASE
            WHEN date_diff('day', cgar.cgar_rent_start_datetime, cgar.cgar_rent_end_datetime) < 15 THEN 'SHORT'
            WHEN date_diff('day', cgar.cgar_rent_start_datetime, cgar.cgar_rent_end_datetime) < 30 THEN 'MONTH'
            ELSE 'SUBSCRIPTION'
        END AS rentType
    FROM carmore.carmore_global_api_reservation cgar
    INNER JOIN carmore.carmore_global_api_affiliates
        ON cgar_cgaa_index = cgaa_index
    INNER JOIN carmore.carinfo_master cim
        ON cgar_cimaster_index = carinfo_idx
) r ON CAST(nrl.reservation_idx AS VARCHAR) = r.reservationNumber
LEFT JOIN (
    -- 지점 정보 서브쿼리: 파트너스
    SELECT
        branch.branchName AS "예약_지점명",
        CONCAT(branch.address, ' ', branch.detailAddress) AS "주소",
        CAST(branch.serial AS VARCHAR) AS serial,
        1 AS type
    FROM carmore.new_rentCompany_branch branch

    UNION ALL

    -- 지점 정보 서브쿼리: JEJU_API
    SELECT
        branch.waab_name AS "예약_지점명",
        CONCAT(branch.waab_main_address, ' ', branch.waab_sub_address) AS "주소",
        CAST(branch.waab_idx AS VARCHAR) AS serial,
        2 AS type
    FROM carmore.workspace_api_affiliate_branch branch

    UNION ALL

    -- 지점 정보 서브쿼리: GLOBAL_API
    SELECT
        CONCAT(branch.cgaa_name, ' ', branch.cgaa_location_name) AS "예약_지점명",
        '' AS "주소",
        CAST(branch.cgaa_index AS VARCHAR) AS serial,
        3 AS type
    FROM carmore.carmore_global_api_affiliates branch
) b ON CAST(nrl.branch_serial AS VARCHAR) = b.serial
    AND TRY_CAST(nrl.nrl_affiliate_type AS INTEGER) = b.type
WHERE TRY_CAST(nrl.status AS INTEGER) = 1
  AND nrl.register_date > TIMESTAMP '{since}'
ORDER BY nrl.register_date DESC
"""


# 필터 검색 쿼리 (동적 WHERE 조건)
SEARCH_QUERY_BASE = """
SELECT
    nrl.serial              AS review_id,
    nrl.reservation_idx     AS reservation_id,
    nrl.company_serial      AS company_id,
    nrl.branch_serial       AS branch_id,
    r."예약_업체명"         AS company_name,
    b."예약_지점명"         AS branch_name,
    nrl.branch_evaluation   AS rating_service,
    nrl.car_evaluation      AS rating_car,
    nrl.take_evaluation     AS rating_convenience,
    nrl.opinion             AS content,
    nrl.register_date       AS review_date,
    nrl.status              AS status,
    r."차종"                AS car_type,
    r."차량모델"            AS car_model,
    COUNT(*) OVER()         AS total_count
FROM carmore.new_review_list nrl
LEFT JOIN (
    SELECT
        CAST(trl.f_reservationidx AS VARCHAR) AS reservationNumber,
        nrc.name AS "예약_업체명",
        CASE TRY_CAST(trl.trl_car_type_flag AS INTEGER)
            WHEN 0 THEN '경형' WHEN 1 THEN '소형' WHEN 2 THEN '준중형'
            WHEN 3 THEN '중형' WHEN 4 THEN '대형' WHEN 5 THEN '수입'
            WHEN 6 THEN 'RV' WHEN 7 THEN 'SUV' ELSE NULL
        END AS "차종",
        trl.trl_car_model AS "차량모델",
        CASE TRY_CAST(trl.reserv_rent_type AS INTEGER)
            WHEN 1 THEN 'SHORT' WHEN 2 THEN 'MONTH' ELSE 'SUBSCRIPTION'
        END AS rentType
    FROM carmore.tbl_reservation_list trl
    INNER JOIN carmore.new_rentCompany nrc ON trl.company_serial = nrc.serial

    UNION ALL

    SELECT
        CAST(wari_reserv_idx AS VARCHAR) AS reservationNumber,
        waa_name AS "예약_업체명",
        CASE TRY_CAST(wari.wari_car_type_flag AS INTEGER)
            WHEN 0 THEN '경형' WHEN 1 THEN '소형' WHEN 2 THEN '준중형'
            WHEN 3 THEN '중형' WHEN 4 THEN '대형' WHEN 5 THEN '수입'
            WHEN 6 THEN 'RV' WHEN 7 THEN 'SUV' ELSE NULL
        END AS "차종",
        wari.wari_car_name AS "차량모델",
        CASE
            WHEN date_diff('day', wari.wari_rental_start, wari.wari_rental_end) < 15 THEN 'SHORT'
            WHEN date_diff('day', wari.wari_rental_start, wari.wari_rental_end) < 30 THEN 'MONTH'
            ELSE 'SUBSCRIPTION'
        END AS rentType
    FROM carmore.workspace_api_reservation_inventory wari
    INNER JOIN carmore.workspace_api_affiliate ON wari_waa_idx = waa_idx

    UNION ALL

    SELECT
        CAST(cgar_reservation_number AS VARCHAR) AS reservationNumber,
        cgaa_name AS "예약_업체명",
        CASE TRY_CAST(cim.carinfomst_type AS INTEGER)
            WHEN 0 THEN '경형' WHEN 1 THEN '소형' WHEN 2 THEN '준중형'
            WHEN 3 THEN '중형' WHEN 4 THEN '대형' WHEN 5 THEN '수입'
            WHEN 6 THEN 'RV' WHEN 7 THEN 'SUV' ELSE NULL
        END AS "차종",
        cim.carinfomst_name AS "차량모델",
        CASE
            WHEN date_diff('day', cgar.cgar_rent_start_datetime, cgar.cgar_rent_end_datetime) < 15 THEN 'SHORT'
            WHEN date_diff('day', cgar.cgar_rent_start_datetime, cgar.cgar_rent_end_datetime) < 30 THEN 'MONTH'
            ELSE 'SUBSCRIPTION'
        END AS rentType
    FROM carmore.carmore_global_api_reservation cgar
    INNER JOIN carmore.carmore_global_api_affiliates ON cgar_cgaa_index = cgaa_index
    INNER JOIN carmore.carinfo_master cim ON cgar_cimaster_index = carinfo_idx
) r ON CAST(nrl.reservation_idx AS VARCHAR) = r.reservationNumber
LEFT JOIN (
    SELECT branch.branchName AS "예약_지점명",
        CONCAT(branch.address, ' ', branch.detailAddress) AS "주소",
        CAST(branch.serial AS VARCHAR) AS serial, 1 AS type
    FROM carmore.new_rentCompany_branch branch
    UNION ALL
    SELECT branch.waab_name AS "예약_지점명",
        CONCAT(branch.waab_main_address, ' ', branch.waab_sub_address) AS "주소",
        CAST(branch.waab_idx AS VARCHAR) AS serial, 2 AS type
    FROM carmore.workspace_api_affiliate_branch branch
    UNION ALL
    SELECT CONCAT(branch.cgaa_name, ' ', branch.cgaa_location_name) AS "예약_지점명",
        '' AS "주소",
        CAST(branch.cgaa_index AS VARCHAR) AS serial, 3 AS type
    FROM carmore.carmore_global_api_affiliates branch
) b ON CAST(nrl.branch_serial AS VARCHAR) = b.serial
    AND TRY_CAST(nrl.nrl_affiliate_type AS INTEGER) = b.type
WHERE TRY_CAST(nrl.status AS INTEGER) = 1
"""


class _SearchCache:
    """간단한 TTL 메모리 캐시"""

    def __init__(self, ttl: int = _CACHE_TTL) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _make_key(params: dict) -> str:
        raw = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, params: dict) -> Any | None:
        key = self._make_key(params)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.time() - ts > self._ttl:
                del self._store[key]
                return None
            return value

    def set(self, params: dict, value: Any) -> None:
        key = self._make_key(params)
        now = time.time()
        with self._lock:
            self._store = {
                k: v for k, v in self._store.items() if now - v[0] <= self._ttl
            }
            self._store[key] = (now, value)


_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value: str, name: str) -> str:
    """YYYY-MM-DD 형식 검증 (SQL Injection 방지)"""
    if not _DATE_PATTERN.match(value):
        raise ValueError(f"잘못된 날짜 형식 ({name}): {value!r} — YYYY-MM-DD 필요")
    # 실제 유효한 날짜인지 확인
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"유효하지 않은 날짜 ({name}): {value!r}")
    return value


class AthenaClient:
    """AWS Athena 클라이언트"""

    def __init__(self) -> None:
        settings = get_settings()
        self._client: AthenaClientType = boto3.client(
            "athena",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
            region_name=settings.aws_region,
            config=BotoConfig(
                connect_timeout=10,
                read_timeout=30,
                retries={"max_attempts": 2},
            ),
        )
        self._database = settings.athena_database
        self._output_bucket = settings.athena_output_bucket
        self._search_cache = _SearchCache()

    def fetch_reviews_with_filters(
        self,
        branch_ids: list[int] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "latest",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """
        필터 조건으로 리뷰 검색 (분석 페이지용)

        Args:
            branch_ids: 지점 ID 필터
            date_from: 시작일 (YYYY-MM-DD)
            date_to: 종료일 (YYYY-MM-DD)
            sort_by: 정렬 (latest, rating_low)
            limit: 조회 개수
            offset: 페이징 오프셋

        Returns:
            (리뷰 목록, 전체 개수)
        """
        cache_params = {
            "branch_ids": branch_ids,
            "date_from": date_from,
            "date_to": date_to,
            "sort_by": sort_by,
            "limit": limit,
            "offset": offset,
        }

        cached = self._search_cache.get(cache_params)
        if cached is not None:
            logger.info("Athena 검색 캐시 히트")
            return cached

        # 동적 WHERE 절 빌드 (입력값 검증으로 SQL Injection 방지)
        where_parts: list[str] = []

        if branch_ids:
            safe_ids = [int(bid) for bid in branch_ids]
            ids_str = ", ".join(str(bid) for bid in safe_ids)
            where_parts.append(f"AND nrl.branch_serial IN ({ids_str})")

        if date_from:
            safe_from = _validate_date(date_from, "date_from")
            where_parts.append(f"AND nrl.register_date >= TIMESTAMP '{safe_from} 00:00:00'")

        if date_to:
            safe_to = _validate_date(date_to, "date_to")
            where_parts.append(f"AND nrl.register_date < TIMESTAMP '{safe_to} 23:59:59'")

        # ORDER BY (화이트리스트)
        if sort_by == "rating_low":
            order_clause = "ORDER BY nrl.branch_evaluation ASC"
        else:
            order_clause = "ORDER BY nrl.register_date DESC"

        safe_limit = int(limit)
        safe_offset = int(offset)
        query = SEARCH_QUERY_BASE + "\n".join(where_parts) + f"\n{order_clause}\nOFFSET {safe_offset}\nLIMIT {safe_limit}"

        logger.info(f"Athena 필터 검색: branch_ids={branch_ids}, date={date_from}~{date_to}")

        try:
            rows = self._execute_query(query)

            total = 0
            if rows:
                total_val = rows[0].get("total_count")
                if total_val:
                    total = int(total_val)

            # total_count 컬럼 제거
            for row in rows:
                row.pop("total_count", None)

            result = (rows, total)
            self._search_cache.set(cache_params, result)
            logger.info(f"Athena 필터 검색 완료: {len(rows)}개 / 전체 {total}개")
            return result

        except Exception as e:
            logger.error(f"Athena 필터 검색 실패: {e}")
            raise

    def fetch_reviews_by_branch(
        self,
        branch_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "latest",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """단일 지점 리뷰 조회 (대시보드/분석 페이지용)

        fetch_reviews_with_filters의 단일 지점 편의 래퍼.

        Returns:
            (리뷰 목록, 전체 개수)
        """
        return self.fetch_reviews_with_filters(
            branch_ids=[branch_id],
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

    def fetch_sample_reviews(
        self,
        branch_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 10,
    ) -> list[str]:
        """LLM 프롬프트용 샘플 리뷰 content 목록 조회

        Returns:
            리뷰 content 문자열 리스트 (빈 content 제외)
        """
        reviews, _ = self.fetch_reviews_with_filters(
            branch_ids=[branch_id],
            date_from=date_from,
            date_to=date_to,
            sort_by="latest",
            limit=limit,
            offset=0,
        )
        return [
            r["content"] for r in reviews
            if r.get("content") and r["content"].strip()
        ]

    def fetch_reviews_since(
        self,
        since: datetime,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """
        특정 시점 이후(~이전)의 리뷰 조회

        Args:
            since: 이 시점 이후 리뷰만 조회
            until: 이 시점 이전 리뷰만 조회 (None이면 제한 없음)
            limit: 최대 조회 개수

        Returns:
            리뷰 딕셔너리 리스트
        """
        if not isinstance(since, datetime):
            raise TypeError(f"since must be datetime, got {type(since)}")
        if until is not None and not isinstance(until, datetime):
            raise TypeError(f"until must be datetime, got {type(until)}")
        safe_since = since.strftime("%Y-%m-%d %H:%M:%S")
        query = REVIEW_QUERY.format(since=safe_since)

        if until:
            safe_until = until.strftime("%Y-%m-%d %H:%M:%S")
            # ORDER BY 앞에 조건 삽입 (ORDER BY 뒤에 AND를 넣으면 SQL 에러)
            query = query.replace(
                "ORDER BY nrl.register_date DESC",
                f"AND nrl.register_date <= TIMESTAMP '{safe_until}'\nORDER BY nrl.register_date DESC",
            )

        if limit:
            query += f"\nLIMIT {int(limit)}"

        logger.info(f"Athena 쿼리 실행: since={since}, until={until}")
        logger.debug("Athena 쿼리 (처음 500자): %s...", query[:500])

        try:
            result = self._execute_query(query)
            logger.info(f"Athena 쿼리 완료: {len(result)}개 리뷰 조회")
            return result
        except Exception as e:
            logger.error(f"Athena 쿼리 실패: {e}")
            raise

    def _execute_query(self, query: str, timeout: int = 300) -> list[dict]:
        """
        Athena 쿼리 실행 및 결과 반환

        Args:
            query: SQL 쿼리
            timeout: 타임아웃 (초)

        Returns:
            결과 딕셔너리 리스트
        """
        # 쿼리 시작
        response = self._client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": self._database},
            ResultConfiguration={"OutputLocation": self._output_bucket},
        )

        query_execution_id = response["QueryExecutionId"]
        logger.info(f"쿼리 실행 ID: {query_execution_id}")

        # 쿼리 완료 대기
        state = "RUNNING"
        elapsed = 0
        status = None
        while state in ("RUNNING", "QUEUED") and elapsed < timeout:
            time.sleep(2)
            elapsed += 2

            try:
                status = self._client.get_query_execution(
                    QueryExecutionId=query_execution_id
                )
                state = status["QueryExecution"]["Status"]["State"]
            except Exception as e:
                logger.warning(f"쿼리 상태 조회 실패 ({elapsed}초): {e}")
                if elapsed >= timeout:
                    raise RuntimeError(
                        f"Athena 쿼리 상태 조회 실패 (타임아웃 {timeout}초): {e}"
                    )
                continue

            if elapsed % 10 == 0:
                logger.info(f"쿼리 상태: {state} ({elapsed}초 경과)")

        if state != "SUCCEEDED":
            error_msg = status["QueryExecution"]["Status"].get(
                "StateChangeReason", "Unknown error"
            )
            raise RuntimeError(f"Athena 쿼리 실패: {state} - {error_msg}")

        # 결과 조회
        return self._get_query_results(query_execution_id)

    def _get_query_results(
        self, query_execution_id: str, max_pages: int = 500
    ) -> list[dict]:
        """쿼리 결과 조회 (페이지네이션 처리, 최대 max_pages 페이지)"""
        results: list[dict] = []
        next_token = None
        columns: list[str] = []
        page_count = 0

        while page_count < max_pages:
            page_count += 1
            if next_token:
                response = self._client.get_query_results(
                    QueryExecutionId=query_execution_id,
                    NextToken=next_token,
                )
            else:
                response = self._client.get_query_results(
                    QueryExecutionId=query_execution_id
                )

            result_set = response["ResultSet"]

            # 첫 번째 페이지에서 컬럼명 추출
            if not columns:
                columns = [
                    col["Name"]
                    for col in result_set["ResultSetMetadata"]["ColumnInfo"]
                ]

            # 데이터 행 처리
            rows = result_set["Rows"]
            start_idx = 1 if not results else 0  # 첫 페이지는 헤더 제외

            for row in rows[start_idx:]:
                row_data = {}
                for i, cell in enumerate(row["Data"]):
                    value = cell.get("VarCharValue")
                    row_data[columns[i]] = value
                results.append(row_data)

            # 다음 페이지 확인
            next_token = response.get("NextToken")
            if not next_token:
                break

        return results

    def test_connection(self) -> bool:
        """연결 테스트"""
        try:
            self._client.list_databases(CatalogName="AwsDataCatalog", MaxResults=1)
            return True
        except Exception as e:
            logger.error(f"Athena 연결 테스트 실패: {e}")
            return False
