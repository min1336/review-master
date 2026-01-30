"""AWS Athena 클라이언트"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

import boto3

from core.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_athena import AthenaClient as AthenaClientType

logger = logging.getLogger(__name__)


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


class AthenaClient:
    """AWS Athena 클라이언트"""

    def __init__(self) -> None:
        settings = get_settings()
        self._client: AthenaClientType = boto3.client(
            "athena",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
            region_name=settings.aws_region,
        )
        self._database = settings.athena_database
        self._output_bucket = settings.athena_output_bucket

    def fetch_reviews_since(
        self, since: datetime, limit: int | None = None
    ) -> list[dict]:
        """
        특정 시점 이후의 리뷰 조회

        Args:
            since: 이 시점 이후 리뷰만 조회
            limit: 최대 조회 개수

        Returns:
            리뷰 딕셔너리 리스트
        """
        query = REVIEW_QUERY.format(since=since.strftime("%Y-%m-%d %H:%M:%S"))

        if limit:
            query += f"\nLIMIT {limit}"

        logger.info(f"Athena 쿼리 실행: since={since}")
        print(f"[DEBUG] Athena 쿼리:\n{query[:500]}...")

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
        while state in ("RUNNING", "QUEUED") and elapsed < timeout:
            time.sleep(2)
            elapsed += 2

            status = self._client.get_query_execution(
                QueryExecutionId=query_execution_id
            )
            state = status["QueryExecution"]["Status"]["State"]

            if elapsed % 10 == 0:
                logger.info(f"쿼리 상태: {state} ({elapsed}초 경과)")

        if state != "SUCCEEDED":
            error_msg = status["QueryExecution"]["Status"].get(
                "StateChangeReason", "Unknown error"
            )
            raise RuntimeError(f"Athena 쿼리 실패: {state} - {error_msg}")

        # 결과 조회
        return self._get_query_results(query_execution_id)

    def _get_query_results(self, query_execution_id: str) -> list[dict]:
        """쿼리 결과 조회 (페이지네이션 처리)"""
        results: list[dict] = []
        next_token = None
        columns: list[str] = []

        while True:
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
