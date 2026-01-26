/**
 * @fileoverview 대시보드 API 호출 모듈
 * @module dashboard/api
 */

import { getState, getPagination, getSort, getDateFilter } from './state.js';

// ============================================================
// API Base (기본 API 함수)
// ============================================================

/**
 * API 요청 래퍼 함수
 * @param {string} url - 요청 URL
 * @param {RequestInit} [options={}] - fetch 옵션
 * @returns {Promise<any>} 응답 데이터
 * @throws {Error} 요청 실패 시
 */
async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        ...options
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

// ============================================================
// Stats API (통계)
// ============================================================

/**
 * 전체 통계 조회
 * @returns {Promise<Object>} 통계 데이터
 */
export async function fetchStats() {
    return apiRequest('/api/v2/stats');
}

/**
 * 지역별 통계 조회
 * @returns {Promise<Array>} 지역 통계 목록
 */
export async function fetchRegionStats() {
    return apiRequest('/api/v2/stats/region');
}

/**
 * 평점 분포 통계 조회
 * @returns {Promise<Object>} 평점 분포
 */
export async function fetchRatingStats() {
    return apiRequest('/api/v2/stats/rating');
}

// ============================================================
// Summaries API (요약)
// ============================================================

/**
 * 요약 목록 조회 파라미터 빌드
 * @param {Object} filters - 필터 옵션
 * @returns {URLSearchParams} URL 파라미터
 */
function buildSummariesParams(filters = {}) {
    const { pagination, sort, dateFilter } = getState();

    const params = new URLSearchParams({
        limit: pagination.pageSize,
        offset: pagination.currentPage * pagination.pageSize,
        sort_by: sort.field,
        order: sort.order,
        min_reviews: 0
    });

    if (filters.keyword) params.set('keyword', filters.keyword);
    if (filters.region) params.set('region', filters.region);
    if (filters.status) params.set('status', filters.status);
    if (dateFilter.from) params.set('review_date_from', dateFilter.from);
    if (dateFilter.to) params.set('review_date_to', dateFilter.to);

    return params;
}

/**
 * 요약 목록 조회
 * @param {Object} [filters={}] - 필터 옵션
 * @param {string} [filters.keyword] - 검색어
 * @param {string} [filters.region] - 지역
 * @param {string} [filters.status] - 상태
 * @returns {Promise<Array>} 요약 목록
 */
export async function fetchSummaries(filters = {}) {
    const params = buildSummariesParams(filters);
    return apiRequest(`/api/v2/summaries?${params}`);
}

/**
 * 요약 상세 조회
 * @param {number} branchId - 지점 ID
 * @returns {Promise<Object>} 요약 상세
 */
export async function fetchSummaryDetail(branchId) {
    return apiRequest(`/api/v2/summaries/${branchId}`);
}

/**
 * 요약 수정
 * @param {number} branchId - 지점 ID
 * @param {Object} data - 수정 데이터
 * @returns {Promise<Object>} 수정 결과
 */
export async function updateSummary(branchId, data) {
    return apiRequest(`/api/v2/summaries/${branchId}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    });
}

/**
 * 요약 상태 변경
 * @param {number} branchId - 지점 ID
 * @param {string} status - 새 상태 (draft, approved, published)
 * @returns {Promise<Object>} 변경 결과
 */
export async function updateStatus(branchId, status) {
    return apiRequest(`/api/v2/summaries/${branchId}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status })
    });
}

/**
 * AI 요약 재생성
 * @param {number} branchId - 지점 ID
 * @param {string} [period='all'] - 기간 (all, 1y, 6m, 3m, 1m)
 * @returns {Promise<Object>} 생성된 요약
 */
export async function regenerateSummary(branchId, period = 'all') {
    return apiRequest(`/api/v2/summaries/${branchId}/regenerate`, {
        method: 'POST',
        body: JSON.stringify({ period })
    });
}

/**
 * 대기 중인 요약 적용
 * @param {number} branchId - 지점 ID
 * @param {string} period - 기간
 * @returns {Promise<Object>} 적용 결과
 */
export async function applyPendingSummary(branchId, period) {
    return apiRequest(`/api/v2/summaries/${branchId}/apply-pending`, {
        method: 'POST',
        body: JSON.stringify({ period })
    });
}

/**
 * 대기 중인 요약 취소
 * @param {number} branchId - 지점 ID
 * @param {string} period - 기간
 * @returns {Promise<Object>} 취소 결과
 */
export async function discardPendingSummary(branchId, period) {
    return apiRequest(`/api/v2/summaries/${branchId}/discard-pending`, {
        method: 'POST',
        body: JSON.stringify({ period })
    });
}

// ============================================================
// Reviews API (리뷰)
// ============================================================

/**
 * 지점별 리뷰 목록 조회
 * @param {number} branchId - 지점 ID
 * @param {Object} [options={}] - 옵션
 * @param {number} [options.limit=20] - 조회 개수
 * @param {number} [options.offset=0] - 오프셋
 * @param {string} [options.carModel] - 차량 모델 필터
 * @param {string} [options.sentiment] - 감정 필터
 * @returns {Promise<Object>} 리뷰 목록 및 메타데이터
 */
export async function fetchBranchReviews(branchId, options = {}) {
    const { dateFilter } = getState();

    const params = new URLSearchParams({
        limit: options.limit || 20,
        offset: options.offset || 0
    });

    if (options.carModel) params.set('car_model', options.carModel);
    if (options.sentiment) params.set('sentiment', options.sentiment);
    if (dateFilter.from) params.set('review_date_from', dateFilter.from);
    if (dateFilter.to) params.set('review_date_to', dateFilter.to);

    return apiRequest(`/api/v2/summaries/${branchId}/reviews?${params}`);
}

// ============================================================
// Tags API (태그)
// ============================================================

/**
 * 지점별 태그 일괄 조회
 * @param {number[]} branchIds - 지점 ID 목록
 * @returns {Promise<Object>} 지점별 태그 맵
 */
export async function fetchBranchTagsBatch(branchIds) {
    if (!branchIds || branchIds.length === 0) {
        return {};
    }

    return apiRequest('/api/tags/batch', {
        method: 'POST',
        body: JSON.stringify({ branch_ids: branchIds })
    });
}

// ============================================================
// Carmore API (외부 연동)
// ============================================================

/**
 * Carmore 업체 동기화
 * @returns {Promise<Object>} 동기화 결과
 */
export async function syncAffiliates() {
    return apiRequest('/api/carmore/sync/affiliates', {
        method: 'POST'
    });
}

// ============================================================
// Error Handling (에러 처리 헬퍼)
// ============================================================

/**
 * API 호출 래퍼 (에러 처리 포함)
 * @param {Function} apiFunc - API 함수
 * @param {Object} [options={}] - 옵션
 * @param {Function} [options.onError] - 에러 콜백
 * @param {any} [options.fallback] - 에러 시 반환값
 * @returns {Promise<any>} 결과 또는 fallback
 */
export async function safeApiCall(apiFunc, options = {}) {
    try {
        return await apiFunc();
    } catch (error) {
        console.error('API Error:', error);
        if (options.onError) {
            options.onError(error);
        }
        return options.fallback;
    }
}
