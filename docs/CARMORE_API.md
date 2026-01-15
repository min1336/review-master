# Carmore RentCar API 문서

> **Base URL**: `https://dev-rentcar-api.carmore.kr`
> **API Version**: v0.1
> **Swagger UI**: [https://dev-rentcar-api.carmore.kr/docs](https://dev-rentcar-api.carmore.kr/docs)

---

## 목차

1. [개요](#개요)
2. [공통 사항](#공통-사항)
3. [엔드포인트](#엔드포인트)
   - [기본](#1-기본-app)
   - [위치](#2-위치-locations)
   - [제휴사](#3-제휴사-affiliates)
   - [차량](#4-차량-cars)
   - [V2 차량](#5-v2-차량-v2vehicles)
   - [V2 업체](#6-v2-업체-v2companies)
   - [예약](#7-예약-reservation)
   - [예약 부가서비스](#8-예약-부가서비스-reservations)
   - [V2 예약](#9-v2-예약-v2reservations)
   - [리뷰](#10-리뷰-reviews)
   - [정책](#11-정책-policy)
   - [번역](#12-번역-translations)
   - [캐시](#13-캐시-cache)
   - [지점](#14-지점-branch)
   - [관리자](#15-관리자-admin)
4. [응답 형식](#응답-형식)
5. [에러 처리](#에러-처리)

---

## 개요

Carmore RentCar API는 렌터카 예약 플랫폼을 위한 RESTful API입니다.

### 주요 기능

- **차량 검색 및 예약**: 국내/해외 렌터카 검색, 가예약, 실예약
- **제휴사 관리**: 렌터카 업체 및 지점 정보 조회
- **리뷰 시스템**: 지점별 리뷰 및 평점 조회
- **다국어 지원**: Accept-Language 헤더를 통한 다국어 응답
- **관리자 기능**: 지점, 업체, 위치, 월구독 관리

### 지원 API 타입

| API 타입 | 설명 |
|----------|------|
| `PARTNERS` | 국내 파트너스 렌터카 |
| `JEJU` | 제주 렌터카 |
| `GLOBAL` | 해외 글로벌 렌터카 |

---

## 공통 사항

### 인증

API 요청 시 필요에 따라 인증 토큰이 필요할 수 있습니다.

### 공통 헤더

| 헤더 | 설명 | 예시 |
|------|------|------|
| `Accept-Language` | 응답 언어 설정 | `ko`, `en`, `ja` |
| `Content-Type` | 요청 본문 타입 | `application/json` |

### 공통 쿼리 파라미터

| 파라미터 | 타입 | 설명 | 예시 |
|----------|------|------|------|
| `startDateTime` | string | 대여 시작 일시 | `2024-01-15 10:00:00` |
| `endDateTime` | string | 반납 일시 | `2024-01-17 10:00:00` |
| `latitude` | number | 위도 | `33.4996` |
| `longitude` | number | 경도 | `126.5312` |
| `driverAge` | number | 운전자 나이 | `30` |
| `nationalCode` | string | 국가 코드 | `KR` |
| `cityCode` | string | 도시 코드 | `CJU` |

### 페이지네이션 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `page` | number | 1 | 페이지 번호 |
| `pageSize` | number | 10 | 페이지당 항목 수 |
| `isPagination` | boolean | true | 페이지네이션 사용 여부 |

---

## 엔드포인트

### 1. 기본 (App)

#### 헬스 체크

```
GET /
```

애플리케이션 상태를 확인합니다.

**응답**: `200 OK`

---

### 2. 위치 (Locations)

#### 2.1 모든 위치 정보 조회

```
POST /locations
```

모든 위치 정보를 조회합니다.

---

#### 2.2 위치 PlaceIds 업데이트

```
POST /locations/location/placeIds
```

위치의 Google Place ID를 업데이트합니다.

---

#### 2.3 카모아 지역 정보 조회

```
GET /locations/carmore
```

좌표 또는 코드로 카모아 지역 정보를 반환합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `lat` | number | 선택 | 위도 |
| `lng` | number | 선택 | 경도 |
| `c` | string | 선택 | 위치 코드 |

---

### 3. 제휴사 (Affiliates)

#### 3.1 모든 제휴사 조회

```
GET /affiliates
```

허용된 모든 제휴사 목록을 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `locationType` | string | **필수** | 위치 타입 |

---

#### 3.2 특정 제휴사 조회

```
GET /affiliates/{affiliateIndex}
```

특정 제휴사의 상세 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `affiliateIndex` | number | **필수** | 제휴사 인덱스 (Path) |

---

### 4. 차량 (Cars)

#### 4.1 차량 검색

```
GET /cars
```

조건에 맞는 차량을 검색합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `startDateTime` | string | **필수** | 대여 시작 일시 |
| `endDateTime` | string | **필수** | 반납 일시 |
| `latitude` | number | 선택 | 위도 |
| `longitude` | number | 선택 | 경도 |
| `driverAge` | number | 선택 | 운전자 나이 |
| `cityCode` | string | 선택 | 도시 코드 |
| `specialLocation` | string | 선택 | 특수 위치 |
| `limitDistance` | number | 선택 | 거리 제한 |
| `mp` | string | 선택 | MP 파라미터 |
| `uShip` | boolean | 선택 | 배송 여부 |
| `uShipTime` | string | 선택 | 배송 시간 |
| `uShipReturn` | boolean | 선택 | 반납 배송 여부 |
| `clientId` | string | 선택 | 클라이언트 ID |
| `mode` | string | 선택 | 모드 |
| `targets` | string | 선택 | 타겟 |
| `version` | string | 선택 | 버전 |

---

#### 4.2 차종 조회

```
GET /cars/models
```

이용 가능한 차종 목록을 조회합니다.

| 헤더 | 설명 |
|------|------|
| `Accept-Language` | 응답 언어 |

---

#### 4.3 차량 상세 (PHP & Global)

```
GET /cars/{rentCarSerial}
```

특정 차량의 상세 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `rentCarSerial` | string | **필수** | 차량 시리얼 (Path) |
| `startDateTime` | string | **필수** | 대여 시작 일시 |
| `endDateTime` | string | **필수** | 반납 일시 |
| `accessKey` | string | 선택 | 접근 키 |
| `type` | string | 선택 | 타입 |
| `areaCode` | string | 선택 | 지역 코드 |
| `driverAge` | number | 선택 | 운전자 나이 |
| `nationalCode` | string | 선택 | 국가 코드 |
| `pickupShopId` | string | 선택 | 픽업 지점 ID |
| `returnShopId` | string | 선택 | 반납 지점 ID |

---

#### 4.4 차량 상세 (InteractKey)

```
GET /cars/detail/{interactKey}
```

InteractKey로 차량 상세 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `interactKey` | string | **필수** | 인터랙트 키 (Path) |
| `driverAge` | number | 선택 | 운전자 나이 |
| `startDateTime` | string | 선택 | 대여 시작 일시 |
| `endDateTime` | string | 선택 | 반납 일시 |
| `nationalCode` | string | 선택 | 국가 코드 |
| `pickupShopId` | string | 선택 | 픽업 지점 ID |
| `returnShopId` | string | 선택 | 반납 지점 ID |

---

### 5. V2 차량 (V2/Vehicles)

#### 5.1 차량 조회

```
GET /v2/vehicles
```

V2 버전의 차량 검색 API입니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `startDateTime` | string | **필수** | 대여 시작 일시 |
| `endDateTime` | string | **필수** | 반납 일시 |
| `cityCode` | string | 선택 | 도시 코드 |
| `latitude` | number | 선택 | 위도 |
| `longitude` | number | 선택 | 경도 |
| `driverAge` | number | 선택 | 운전자 나이 |
| `currency` | string | 선택 | 통화 |
| `nationalCode` | string | 선택 | 국가 코드 |
| `uShip` | boolean | 선택 | 배송 여부 |
| `uShipTime` | string | 선택 | 배송 시간 |
| `uShipReturn` | boolean | 선택 | 반납 배송 여부 |
| `returnLatitude` | number | 선택 | 반납 위도 |
| `returnLongitude` | number | 선택 | 반납 경도 |
| `returnNationalCode` | string | 선택 | 반납 국가 코드 |
| `clientId` | string | 선택 | 클라이언트 ID |
| `mode` | string | 선택 | 모드 |
| `carModelIndex` | number | 선택 | 차종 인덱스 |

---

#### 5.2 차량 단일 조회

```
GET /v2/vehicles/{id}
```

특정 차량의 상세 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `id` | string | **필수** | 차량 ID (Path) |
| `startDateTime` | string | **필수** | 대여 시작 일시 |
| `endDateTime` | string | **필수** | 반납 일시 |
| `cityCode` | string | 선택 | 도시 코드 |
| `latitude` | number | 선택 | 위도 |
| `longitude` | number | 선택 | 경도 |
| `driverAge` | number | 선택 | 운전자 나이 |
| `nationalCode` | string | 선택 | 국가 코드 |
| `pickupShopId` | string | 선택 | 픽업 지점 ID |
| `returnShopId` | string | 선택 | 반납 지점 ID |
| `clientId` | string | 선택 | 클라이언트 ID |
| `mode` | string | 선택 | 모드 |

---

### 6. V2 업체 (V2/Companies)

#### 6.1 회사별 차종 조회

```
GET /v2/companies/{companyId}/cars
```

특정 회사의 차종 목록을 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `companyId` | string | **필수** | 회사 ID (Path) |
| `clientId` | string | **필수** | 클라이언트 ID |

---

#### 6.2 회사별 지점 목록 조회

```
GET /v2/companies/{companyId}/branches
```

특정 회사의 지점 목록을 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `companyId` | string | **필수** | 회사 ID (Path) |
| `clientId` | string | **필수** | 클라이언트 ID |

---

### 7. 예약 (Reservation)

#### 7.1 회원 예약 조회 (예약키)

```
GET /reservation/reservations
```

예약키로 예약 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservKey` | string | **필수** | 예약 키 |

---

#### 7.2 실예약

```
POST /reservation/reservations
```

실제 예약을 생성합니다.

**Request Body**:

```json
{
  "isApproved": true,
  "apiType": "PARTNERS",
  "rentCarId": "string",
  "reservationNumber": "string",
  "otaReservationNumber": "string",
  "paymentKey": "string",
  "paymentMethod": "string",
  "packageId": "string",
  "mid": "string",
  "useBilling": false,
  "encryptedCardId": "string",
  "clientId": "string"
}
```

---

#### 7.3 회원 예약 조회 (접근키)

```
GET /reservation/reservations/{accessKey}
```

접근키로 예약 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `accessKey` | string | **필수** | 접근 키 (Path) |

---

#### 7.4 회원 예약 조회 (패키지 포함)

```
GET /reservation/reservations/with-in-package/{accessKey}
```

패키지 정보를 포함한 예약을 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `accessKey` | string | **필수** | 접근 키 (Path) |

---

#### 7.5 가예약

```
POST /reservation/pre-reservation
```

가예약을 생성합니다.

**Request Body**:

```json
{
  "packageIndex": "string",
  "clientId": "string",
  "accessKey": "string",
  "apiType": "PARTNERS",
  "useBilling": false,
  "startDate": "string",
  "endDate": "string",
  "paymentAmount": 0,
  "principalAmount": 0,
  "usePointAmount": 0,
  "useCouponAmount": 0,
  "useCouponIndex": "string",
  "areaString": "string",
  "driverName": "string",
  "driverPhone": "string",
  "driverEmail": "string",
  "driverBirthday": "string",
  "driverGender": "M",
  "hasAddedDriver": false
}
```

---

#### 7.6 예약 상세 조회

```
GET /reservation/{reservKey}
```

예약 상세 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservKey` | string | **필수** | 예약 키 (Path) |
| `accessKey` | string | 선택 | 접근 키 |
| `apiType` | string | 선택 | API 타입 |

---

#### 7.7 글로벌 가예약

```
POST /reservation/pre-reservation/global
```

해외 렌터카 가예약을 생성합니다.

---

#### 7.8 파트너스 가예약

```
POST /reservation/pre-reservation/partners
```

파트너스 가예약을 생성합니다.

---

#### 7.9 예약 취소 (결제 무관)

```
PATCH /reservation/cancel
```

예약을 취소합니다 (결제와 무관).

**Request Body**:

```json
{
  "reservationNumber": "string",
  "principalAmount": 0,
  "cancelAmount": 0,
  "cancelPercent": 0,
  "reservKey": "string",
  "cancelType": "string",
  "cancelReason": "string",
  "accessKey": "string",
  "isAdmin": false
}
```

---

#### 7.10 예약 취소 (결제 관련)

```
PATCH /reservation/payment/cancel
```

결제 관련 예약 취소를 처리합니다.

**Request Body**: 7.9와 동일

---

#### 7.11 패키지 예약 전환

```
PUT /reservation/package
```

수기 예약을 패키지 예약으로 전환합니다.

**Request Body**:

```json
{
  "reservationNumber": "string",
  "packageIndex": "string"
}
```

---

### 8. 예약 부가서비스 (Reservations)

#### 8.1 보험 부가서비스 이관

```
POST /reservations/{reservationId}/addons/insurance/transfer
```

보험 부가서비스를 이관합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservationId` | string | **필수** | 예약 ID (Path) |

---

#### 8.2 보험 부가서비스 추가

```
POST /reservations/{reservationId}/addons/insurance
```

보험 부가서비스를 추가합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservationId` | string | **필수** | 예약 ID (Path) |

---

#### 8.3 보험 부가서비스 취소

```
DELETE /reservations/{reservationId}/addons/insurance
```

보험 부가서비스를 취소합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservationId` | string | **필수** | 예약 ID (Path) |

---

### 9. V2 예약 (V2/Reservations)

#### 9.1 예약 조회

```
GET /v2/reservations/{id}
```

V2 버전의 예약 조회 API입니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `id` | string | **필수** | 예약 ID (Path) |

---

### 10. 리뷰 (Reviews)

#### 10.1 리뷰 조회

```
GET /reviews/{affiliateBranchIndex}
```

특정 지점의 리뷰를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `affiliateBranchIndex` | number | **필수** | 제휴사 지점 인덱스 (Path) |
| `type` | string | **필수** | 리뷰 타입 |
| `page` | number | 선택 | 페이지 번호 |
| `pageSize` | number | 선택 | 페이지당 항목 수 |
| `isPagination` | boolean | 선택 | 페이지네이션 사용 여부 |
| `order` | string | 선택 | 정렬 순서 |
| `rentType` | string | 선택 | 렌트 타입 |

**예시 요청**:

```bash
curl -X GET "https://dev-rentcar-api.carmore.kr/reviews/123?type=ALL&page=1&pageSize=10"
```

---

### 11. 정책 (Policy)

#### 11.1 환불 정책 조회

```
GET /policy/refund/{reservationIndex}
```

특정 예약의 환불 정책을 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservationIndex` | number | **필수** | 예약 인덱스 (Path) |

---

#### 11.2 취소 정책 조회

```
GET /policy/cancel
```

취소 정책을 조회합니다.

---

### 12. 번역 (Translations)

#### 12.1 번역 API

```
POST /translations
```

텍스트를 번역합니다.

**Request Body**:

```json
{
  "language": "ko",
  "api": "string",
  "type": "string",
  "data": {}
}
```

---

### 13. 캐시 (Cache)

#### 13.1 지점 마스터 정보 등록

```
POST /cache
```

지점 마스터 정보를 캐시에 등록합니다.

**Request Body**:

```json
{
  "language": "ko",
  "type": "string",
  "masterId": "string",
  "data": {}
}
```

---

#### 13.2 지점 마스터 정보 조회

```
GET /cache
```

캐시된 지점 마스터 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `type` | string | **필수** | 캐시 타입 |
| `language` | string | **필수** | 언어 |
| `branchMaster` | string | **필수** | 지점 마스터 ID |

---

#### 13.3 업체 정보 등록

```
POST /cache/company
```

업체 정보를 캐시에 등록합니다.

---

#### 13.4 업체 정보 조회

```
GET /cache/company
```

캐시된 업체 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `type` | string | **필수** | 캐시 타입 |
| `language` | string | **필수** | 언어 |
| `companyMaster` | string | **필수** | 업체 마스터 ID |

---

#### 13.5 여러 업체 정보 등록

```
POST /cache/companies
```

여러 업체 정보를 일괄 등록합니다.

---

#### 13.6 번역된 지점 정보 조회

```
GET /cache/translations
```

번역된 지점 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `api` | string | **필수** | API 타입 |
| `type` | string | **필수** | 캐시 타입 |
| `language` | string | **필수** | 언어 |
| `ids` | string | **필수** | ID 목록 |

---

#### 13.7 번역된 지점 정보 등록

```
POST /cache/translations
```

번역된 지점 정보를 등록합니다.

**Request Body**:

```json
{
  "api": "string",
  "type": "string",
  "id": "string",
  "language": "ko",
  "data": {}
}
```

---

### 14. 지점 (Branch)

#### 14.1 업체 정보 포함 제휴사 조회

```
GET /branch
```

업체 정보를 포함한 제휴사 정보를 조회합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `type` | string | **필수** | 타입 |
| `language` | string | **필수** | 언어 |
| `branchMaster` | string | **필수** | 지점 마스터 ID |

---

### 15. 관리자 (Admin)

#### 15.1 지점 관리

##### 카테고리 조회

```
GET /admin/branch/category
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `type` | string | **필수** | 카테고리 타입 |

---

##### 지점 마스터 조회

```
GET /admin/branch/master
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `nationalId` | string | 선택 | 국가 ID |
| `page` | number | 선택 | 페이지 번호 |
| `pageSize` | number | 선택 | 페이지당 항목 수 |
| `isPagination` | boolean | 선택 | 페이지네이션 사용 여부 |
| `searchValue` | string | 선택 | 검색어 |
| `isActive` | boolean | 선택 | 활성 상태 필터 |

---

##### 지점 마스터 등록

```
POST /admin/branch/master
```

**Request Body**:

```json
{
  "affiliate": {},
  "informations": [],
  "matchedAffiliates": [],
  "updatedBy": "string"
}
```

---

##### 지점 마스터 수정

```
PATCH /admin/branch/master/{id}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `id` | string | **필수** | 지점 마스터 ID (Path) |

---

##### 지점 마스터 상세 조회

```
GET /admin/branch/master/{id}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `id` | string | **필수** | 지점 마스터 ID (Path) |
| `language` | string | 선택 | 언어 |
| `type` | string | 선택 | 타입 |

---

##### 지점 통합 조회

```
GET /admin/branch/integration
```

통합된 지점 목록을 조회합니다.

---

##### 지점 마스터 수정 기록

```
GET /admin/branch/history/{id}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `id` | string | **필수** | 지점 마스터 ID (Path) |
| `page` | number | 선택 | 페이지 번호 |
| `pageSize` | number | 선택 | 페이지당 항목 수 |
| `isPagination` | boolean | 선택 | 페이지네이션 사용 여부 |

---

##### 지점 상세정보 수정 기록

```
GET /admin/branch/history/information/{id}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `id` | string | **필수** | 지점 상세정보 ID (Path) |
| `page` | number | 선택 | 페이지 번호 |
| `pageSize` | number | 선택 | 페이지당 항목 수 |
| `isPagination` | boolean | 선택 | 페이지네이션 사용 여부 |

---

#### 15.2 업체 관리

##### 업체 조회

```
GET /admin/company
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `page` | number | 선택 | 페이지 번호 |
| `pageSize` | number | 선택 | 페이지당 항목 수 |
| `isPagination` | boolean | 선택 | 페이지네이션 사용 여부 |

---

##### 업체 등록

```
POST /admin/company
```

**Request Body**:

```json
{
  "companies": []
}
```

---

##### 업체 상세 조회

```
GET /admin/company/{id}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `id` | string | **필수** | 업체 ID (Path) |

---

##### 업체 수정

```
PATCH /admin/company/{id}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `id` | string | **필수** | 업체 ID (Path) |

---

#### 15.3 기타 관리

##### 국가 정보 조회

```
GET /admin/national
```

모든 국가 정보를 조회합니다.

---

##### 다국어 조회

```
GET /admin/language
```

지원 언어 목록을 조회합니다.

---

##### 예약 상세 조회 (관리자)

```
GET /admin/reservation/{reservKey}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservKey` | string | **필수** | 예약 키 (Path) |

---

#### 15.4 월구독 관리

##### 월구독 수기 연장

```
POST /admin/month/manual-extend/{reservationId}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservationId` | string | **필수** | 예약 ID (Path) |

**Request Body**:

```json
{
  "adminId": "string"
}
```

---

##### 월구독 예약번호 생성

```
POST /admin/month/reservation/{reservationId}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservationId` | string | **필수** | 예약 ID (Path) |

**Request Body**:

```json
{
  "reservationId": "string",
  "startDateTime": "string",
  "endDateTime": "string"
}
```

---

##### 월구독 정보 조회

```
GET /admin/month/reservation/{reservationId}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservationId` | string | **필수** | 예약 ID (Path) |
| `startDateTime` | string | 선택 | 시작 일시 |
| `endDateTime` | string | 선택 | 종료 일시 |

---

#### 15.5 위치 관리 (국내)

##### 국내 지역 카테고리

```
GET /admin/location/domestic/regions
```

국내 지역 카테고리를 조회합니다.

---

##### 국내 지역 목록

```
GET /admin/location/domestic
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `page` | number | **필수** | 페이지 번호 |
| `pageSize` | number | **필수** | 페이지당 항목 수 |
| `sortType` | string | **필수** | 정렬 타입 |
| `filterType` | string | 선택 | 필터 타입 |
| `parentCode` | string | 선택 | 상위 코드 |

---

##### 국내 인기 지역

```
GET /admin/location/domestic/popular/{code}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `code` | string | **필수** | 지역 코드 (Path) |

---

##### 국내 지역 정보 수정

```
PUT /admin/location/domestic/details/{code}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `code` | string | **필수** | 지역 코드 (Path) |

**Request Body**:

```json
{
  "badge": "string",
  "icon": "string"
}
```

---

##### 국내 지역 순서 수정

```
PUT /admin/location/domestic/order
```

**Request Body**: `string[]` (지역 코드 배열)

---

#### 15.6 위치 관리 (해외)

##### 해외 지역 카테고리

```
GET /admin/location/overseas/nations
```

해외 국가 목록을 조회합니다.

---

##### 해외 지역 목록

```
GET /admin/location/overseas
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `page` | number | **필수** | 페이지 번호 |
| `pageSize` | number | **필수** | 페이지당 항목 수 |
| `sortType` | string | **필수** | 정렬 타입 |
| `filterType` | string | 선택 | 필터 타입 |
| `parentCode` | string | 선택 | 상위 코드 |

---

##### 해외 인기 지역

```
GET /admin/location/overseas/popular/{code}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `code` | string | **필수** | 지역 코드 (Path) |

---

##### 해외 지역 정보 수정

```
PUT /admin/location/overseas/details/{code}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `code` | string | **필수** | 지역 코드 (Path) |

**Request Body**:

```json
{
  "badge": "string",
  "icon": "string",
  "isActivated": true,
  "name": "string",
  "memo": "string"
}
```

---

##### 해외 지역 순서 수정

```
PUT /admin/location/overseas/order
```

**Request Body**: `string[]` (지역 코드 배열)

---

##### 해외 지역 추가

```
POST /admin/location/overseas/location
```

**Request Body**:

```json
{
  "locationNameEn": "string",
  "locationNameKo": "string",
  "timezone": "string"
}
```

---

#### 15.7 외부 예약 (External)

##### 예약 조회 (예약번호)

```
GET /external/v1/reservations/{reservationNumber}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `reservationNumber` | string | **필수** | 예약 번호 (Path) |

---

## 응답 형식

모든 API 응답은 다음과 같은 표준 형식을 따릅니다.

### 성공 응답

```json
{
  "statusCode": 200,
  "timestamp": "2024-01-15T10:30:00.000Z",
  "path": "/cars",
  "result": {
    // 응답 데이터
  }
}
```

### 에러 응답

```json
{
  "statusCode": 400,
  "timestamp": "2024-01-15T10:30:00.000Z",
  "path": "/cars",
  "error": {
    "message": "에러 메시지",
    "stack": "스택 트레이스 (개발 환경)",
    "incident": "인시던트 ID"
  }
}
```

---

## 에러 처리

### HTTP 상태 코드

| 코드 | 설명 |
|------|------|
| `200` | 성공 |
| `201` | 생성 성공 |
| `204` | 내용 없음 (성공) |
| `400` | 잘못된 요청 (파라미터 오류) |
| `401` | 인증 실패 |
| `403` | 권한 없음 |
| `404` | 리소스를 찾을 수 없음 |
| `500` | 서버 내부 오류 |

### 일반적인 에러 메시지

| 에러 | 원인 | 해결 방법 |
|------|------|----------|
| `필수 파라미터 누락` | 필수 파라미터가 제공되지 않음 | 필수 파라미터 확인 후 재요청 |
| `잘못된 날짜 형식` | 날짜 형식이 올바르지 않음 | `YYYY-MM-DD HH:mm:ss` 형식 사용 |
| `유효하지 않은 예약` | 존재하지 않는 예약 | 예약 키/번호 확인 |

---

## 부록

### 날짜/시간 형식

```
YYYY-MM-DD HH:mm:ss
예: 2024-01-15 10:00:00
```

또는 ISO 8601 형식:

```
YYYY-MM-DDTHH:mm:ss.sssZ
예: 2024-01-15T10:00:00.000Z
```

### API 타입 상수

```
PARTNERS  - 국내 파트너스
JEJU      - 제주
GLOBAL    - 해외 글로벌
```

### 성별 코드

```
M - 남성
F - 여성
```

---

> **문서 생성일**: 2024-01-15
> **API 버전**: v0.1
> **참조**: [Swagger UI](https://dev-rentcar-api.carmore.kr/docs)
