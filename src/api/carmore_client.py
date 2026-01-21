"""
Carmore RentCar API Client

API 문서: https://dev-rentcar-api.carmore.kr/docs
참조: docs/CARMORE_API.md
"""

import os
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    """API 응답 래퍼"""
    success: bool
    data: Any
    status_code: int
    error: Optional[str] = None


class CarmoreAPIClient:
    """
    Carmore RentCar API 클라이언트

    사용법:
        client = CarmoreAPIClient()

        # 리뷰 조회
        reviews = client.get_reviews(branch_id=123, page=1, page_size=100)

        # 업체 목록
        affiliates = client.get_affiliates(location_type="PARTNERS")

        # 차종 목록
        car_models = client.get_car_models()
    """

    BASE_URL = "https://dev-rentcar-api.carmore.kr"
    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_BACKOFF = 0.5

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_key: Optional[str] = None
    ):
        """
        Args:
            base_url: API 기본 URL (기본값: dev 서버)
            timeout: 요청 타임아웃 (초)
            api_key: API 키 (필요시)
        """
        self.base_url = base_url or os.getenv("CARMORE_API_URL", self.BASE_URL)
        self.timeout = timeout
        self.api_key = api_key or os.getenv("CARMORE_API_KEY")

        # 세션 설정 (연결 재사용 + 재시도)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """재시도 로직이 포함된 세션 생성"""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=self.RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _get_headers(self, language: str = "ko") -> Dict[str, str]:
        """공통 헤더 생성"""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": language
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        language: str = "ko"
    ) -> APIResponse:
        """
        API 요청 실행

        Args:
            method: HTTP 메서드 (GET, POST, etc.)
            endpoint: API 엔드포인트 (/reviews/123 등)
            params: 쿼리 파라미터
            data: 요청 본문
            language: 응답 언어

        Returns:
            APIResponse 객체
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(language)

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data,
                timeout=self.timeout
            )

            response.raise_for_status()

            result = response.json()

            # Carmore API 응답 형식: {"statusCode": 200, "result": {...}}
            if isinstance(result, dict) and "result" in result:
                return APIResponse(
                    success=True,
                    data=result["result"],
                    status_code=response.status_code
                )

            return APIResponse(
                success=True,
                data=result,
                status_code=response.status_code
            )

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP 에러: {e}")
            error_msg = str(e)
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    error_msg = error_data["error"].get("message", str(e))
            except:
                pass
            return APIResponse(
                success=False,
                data=None,
                status_code=e.response.status_code if e.response else 500,
                error=error_msg
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"요청 에러: {e}")
            return APIResponse(
                success=False,
                data=None,
                status_code=0,
                error=str(e)
            )

    # =========================================================================
    # 리뷰 API
    # =========================================================================

    def get_reviews(
        self,
        branch_id: int,
        review_type: str = "PARTNERS",
        page: int = 1,
        page_size: int = 100,
        order: Optional[str] = None,
        rent_type: Optional[str] = None
    ) -> APIResponse:
        """
        지점별 리뷰 조회

        Args:
            branch_id: 제휴사 지점 인덱스 (affiliateBranchIndex)
            review_type: API 타입 (PARTNERS, JEJU, GLOBAL)
            page: 페이지 번호
            page_size: 페이지당 항목 수
            order: 정렬 순서
            rent_type: 렌트 타입 (SHORT, LONG, MONTH 등)

        Returns:
            APIResponse with reviews list
        """
        params = {
            "type": review_type,
            "page": page,
            "pageSize": page_size,
            "isPagination": True
        }

        if order:
            params["order"] = order
        if rent_type:
            params["rentType"] = rent_type

        return self._request("GET", f"/reviews/{branch_id}", params=params)

    def get_all_reviews(
        self,
        branch_id: int,
        review_type: str = "PARTNERS",
        max_pages: int = 100
    ) -> List[Dict]:
        """
        지점의 모든 리뷰 조회 (페이지네이션 자동 처리)

        Args:
            branch_id: 지점 인덱스
            review_type: API 타입 (PARTNERS, JEJU, GLOBAL)
            max_pages: 최대 페이지 수 (무한 루프 방지)

        Returns:
            전체 리뷰 리스트
        """
        all_reviews = []
        page = 1

        while page <= max_pages:
            response = self.get_reviews(
                branch_id=branch_id,
                review_type=review_type,
                page=page,
                page_size=100
            )

            if not response.success:
                logger.error(f"리뷰 조회 실패 (branch={branch_id}, page={page}): {response.error}")
                break

            data = response.data
            if not data:
                break

            # Carmore API 응답 형식: {"reviews": [...], "pagination": {...}}
            if isinstance(data, dict):
                reviews = data.get("reviews", [])
                if not reviews:
                    break
                all_reviews.extend(reviews)

                # 페이지네이션 확인
                pagination = data.get("pagination")
                if pagination:
                    total_pages = pagination.get("totalPages", page)
                    if page >= total_pages:
                        break
                else:
                    # 페이지네이션 정보가 없으면 리뷰가 있는 동안 계속
                    if len(reviews) < 100:  # page_size보다 적으면 마지막 페이지
                        break

            elif isinstance(data, list):
                if not data:
                    break
                all_reviews.extend(data)
                if len(data) < 100:
                    break

            page += 1
            time.sleep(0.1)  # Rate limiting

        logger.info(f"지점 {branch_id}: 총 {len(all_reviews)}개 리뷰 조회 완료")
        return all_reviews

    # =========================================================================
    # 제휴사/업체 API
    # =========================================================================

    def get_affiliates(
        self,
        location_type: str = "PARTNERS"
    ) -> APIResponse:
        """
        모든 제휴사 목록 조회

        Args:
            location_type: 위치 타입 (PARTNERS, JEJU, GLOBAL)

        Returns:
            APIResponse with affiliates list
        """
        params = {"locationType": location_type}
        return self._request("GET", "/affiliates", params=params)

    def get_affiliate(self, affiliate_index: int) -> APIResponse:
        """
        특정 제휴사 상세 정보 조회

        Args:
            affiliate_index: 제휴사 인덱스

        Returns:
            APIResponse with affiliate details
        """
        return self._request("GET", f"/affiliates/{affiliate_index}")

    def get_company_branches(
        self,
        company_id: str,
        client_id: str
    ) -> APIResponse:
        """
        회사별 지점 목록 조회 (V2)

        Args:
            company_id: 회사 ID
            client_id: 클라이언트 ID

        Returns:
            APIResponse with branches list
        """
        params = {"clientId": client_id}
        return self._request("GET", f"/v2/companies/{company_id}/branches", params=params)

    # =========================================================================
    # 차량 API
    # =========================================================================

    def get_car_models(self, language: str = "ko") -> APIResponse:
        """
        차종 목록 조회

        Args:
            language: 응답 언어

        Returns:
            APIResponse with car models list
        """
        return self._request("GET", "/cars/models", language=language)

    def search_cars(
        self,
        start_datetime: str,
        end_datetime: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        city_code: Optional[str] = None,
        driver_age: int = 30,
        **kwargs
    ) -> APIResponse:
        """
        차량 검색

        Args:
            start_datetime: 대여 시작 일시 (YYYY-MM-DD HH:mm:ss)
            end_datetime: 반납 일시
            latitude: 위도
            longitude: 경도
            city_code: 도시 코드 (예: CJU)
            driver_age: 운전자 나이
            **kwargs: 추가 파라미터

        Returns:
            APIResponse with cars list
        """
        params = {
            "startDateTime": start_datetime,
            "endDateTime": end_datetime,
            "driverAge": driver_age
        }

        if latitude is not None:
            params["latitude"] = latitude
        if longitude is not None:
            params["longitude"] = longitude
        if city_code:
            params["cityCode"] = city_code

        params.update(kwargs)

        return self._request("GET", "/cars", params=params)

    def search_vehicles_v2(
        self,
        start_datetime: str,
        end_datetime: str,
        city_code: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        driver_age: int = 30,
        currency: str = "KRW",
        national_code: str = "KR",
        **kwargs
    ) -> APIResponse:
        """
        V2 차량 검색

        Args:
            start_datetime: 대여 시작 일시
            end_datetime: 반납 일시
            city_code: 도시 코드
            latitude: 위도
            longitude: 경도
            driver_age: 운전자 나이
            currency: 통화
            national_code: 국가 코드
            **kwargs: 추가 파라미터

        Returns:
            APIResponse with vehicles list
        """
        params = {
            "startDateTime": start_datetime,
            "endDateTime": end_datetime,
            "driverAge": driver_age,
            "currency": currency,
            "nationalCode": national_code
        }

        if city_code:
            params["cityCode"] = city_code
        if latitude is not None:
            params["latitude"] = latitude
        if longitude is not None:
            params["longitude"] = longitude

        params.update(kwargs)

        return self._request("GET", "/v2/vehicles", params=params)

    def get_vehicle_detail(
        self,
        vehicle_id: str,
        start_datetime: str,
        end_datetime: str,
        **kwargs
    ) -> APIResponse:
        """
        V2 차량 상세 조회

        Args:
            vehicle_id: 차량 ID
            start_datetime: 대여 시작 일시
            end_datetime: 반납 일시
            **kwargs: 추가 파라미터

        Returns:
            APIResponse with vehicle details
        """
        params = {
            "startDateTime": start_datetime,
            "endDateTime": end_datetime
        }
        params.update(kwargs)

        return self._request("GET", f"/v2/vehicles/{vehicle_id}", params=params)

    # =========================================================================
    # 유틸리티 메서드
    # =========================================================================

    def health_check(self) -> bool:
        """API 서버 상태 확인"""
        response = self._request("GET", "/")
        return response.success and response.data == {"ok": True}

    def get_branch_info_with_reviews(
        self,
        branch_id: int,
        include_all_reviews: bool = False
    ) -> Dict:
        """
        지점 정보와 리뷰를 함께 조회

        Args:
            branch_id: 지점 ID
            include_all_reviews: 전체 리뷰 조회 여부

        Returns:
            지점 정보 + 리뷰 데이터
        """
        result = {
            "branch_id": branch_id,
            "affiliate": None,
            "reviews": [],
            "review_count": 0
        }

        # 업체 정보 조회
        affiliate_response = self.get_affiliate(branch_id)
        if affiliate_response.success:
            result["affiliate"] = affiliate_response.data

        # 리뷰 조회
        if include_all_reviews:
            result["reviews"] = self.get_all_reviews(branch_id)
        else:
            review_response = self.get_reviews(branch_id, page=1, page_size=10)
            if review_response.success:
                data = review_response.data
                if isinstance(data, list):
                    result["reviews"] = data
                elif isinstance(data, dict):
                    result["reviews"] = data.get("items", [])
                    result["review_count"] = data.get("total", len(result["reviews"]))

        result["review_count"] = len(result["reviews"])

        return result


# 싱글톤 인스턴스 (선택적 사용)
_client_instance: Optional[CarmoreAPIClient] = None


def get_carmore_client() -> CarmoreAPIClient:
    """싱글톤 클라이언트 인스턴스 반환"""
    global _client_instance
    if _client_instance is None:
        _client_instance = CarmoreAPIClient()
    return _client_instance
