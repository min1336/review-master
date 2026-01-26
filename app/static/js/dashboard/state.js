/**
 * @fileoverview 대시보드 상태 관리
 * @module dashboard/state
 */

import { CONFIG } from './config.js';

/**
 * @typedef {Object} PaginationState
 * @property {number} currentPage - 현재 페이지 (0-indexed)
 * @property {number} pageSize - 페이지 크기
 */

/**
 * @typedef {Object} SortState
 * @property {string} field - 정렬 필드
 * @property {'asc'|'desc'} order - 정렬 방향
 */

/**
 * @typedef {Object} DateFilterState
 * @property {Object|null} picker - Flatpickr 인스턴스
 * @property {string|null} from - 시작일 (YYYY-MM-DD)
 * @property {string|null} to - 종료일 (YYYY-MM-DD)
 */

/**
 * @typedef {Object} EditModeState
 * @property {boolean} isActive - 수정 모드 활성화 여부
 * @property {string[]} selectedTags - 현재 선택된 태그
 * @property {string[]} originalTags - 원본 태그 (취소 시 복원용)
 * @property {string} currentPeriod - 현재 선택된 요약 기간
 */

/**
 * @typedef {Object} ReviewsState
 * @property {number} currentPage - 현재 페이지 (0-indexed)
 * @property {number} pageSize - 페이지 크기
 * @property {number} total - 전체 리뷰 수
 * @property {boolean} visible - 리뷰 섹션 표시 여부
 * @property {boolean} carModelsLoaded - 차량 모델 로드 완료 여부
 */

/**
 * @typedef {Object} DashboardState
 * @property {PaginationState} pagination - 페이지네이션 상태
 * @property {SortState} sort - 정렬 상태
 * @property {DateFilterState} dateFilter - 날짜 필터 상태
 * @property {EditModeState} editMode - 수정 모드 상태
 * @property {ReviewsState} reviews - 리뷰 목록 상태
 * @property {Array} summaries - 요약 데이터 목록
 * @property {Array} regionStats - 지역 통계 데이터
 */

/**
 * 대시보드 전역 상태 객체
 * @type {DashboardState}
 */
const state = {
    // 메인 테이블 페이지네이션
    pagination: {
        currentPage: 0,
        pageSize: CONFIG.PAGINATION.DEFAULT_PAGE_SIZE
    },

    // 정렬 상태
    sort: {
        field: 'review_count',
        order: 'desc'
    },

    // 날짜 필터
    dateFilter: {
        picker: null,
        from: null,
        to: null
    },

    // 수정 모드
    editMode: {
        isActive: false,
        selectedTags: [],
        originalTags: [],
        currentPeriod: 'all'
    },

    // 리뷰 목록 (모달 내)
    reviews: {
        currentPage: 0,
        pageSize: CONFIG.PAGINATION.REVIEWS_PAGE_SIZE,
        total: 0,
        visible: false,
        carModelsLoaded: false
    },

    // 데이터
    summaries: [],
    regionStats: []
};

// ============================================================
// State Getters (상태 조회)
// ============================================================

/**
 * 전체 상태 반환 (읽기 전용)
 * @returns {DashboardState} 현재 상태
 */
export function getState() {
    return state;
}

/**
 * 페이지네이션 상태 반환
 * @returns {PaginationState}
 */
export function getPagination() {
    return state.pagination;
}

/**
 * 정렬 상태 반환
 * @returns {SortState}
 */
export function getSort() {
    return state.sort;
}

/**
 * 날짜 필터 상태 반환
 * @returns {DateFilterState}
 */
export function getDateFilter() {
    return state.dateFilter;
}

/**
 * 수정 모드 상태 반환
 * @returns {EditModeState}
 */
export function getEditMode() {
    return state.editMode;
}

/**
 * 리뷰 상태 반환
 * @returns {ReviewsState}
 */
export function getReviews() {
    return state.reviews;
}

/**
 * 요약 목록 반환
 * @returns {Array}
 */
export function getSummaries() {
    return state.summaries;
}

/**
 * 지역 통계 반환
 * @returns {Array}
 */
export function getRegionStats() {
    return state.regionStats;
}

// ============================================================
// State Setters (상태 변경)
// ============================================================

/**
 * 페이지 번호 설정
 * @param {number} page - 페이지 번호 (0-indexed)
 */
export function setCurrentPage(page) {
    state.pagination.currentPage = Math.max(0, page);
}

/**
 * 페이지 증가
 */
export function nextPage() {
    state.pagination.currentPage++;
}

/**
 * 페이지 감소
 */
export function prevPage() {
    if (state.pagination.currentPage > 0) {
        state.pagination.currentPage--;
    }
}

/**
 * 페이지 리셋
 */
export function resetPage() {
    state.pagination.currentPage = 0;
}

/**
 * 정렬 상태 설정
 * @param {string} field - 정렬 필드
 * @param {'asc'|'desc'} [order] - 정렬 방향 (미지정 시 토글)
 */
export function setSort(field, order) {
    if (state.sort.field === field && !order) {
        // 같은 필드면 방향 토글
        state.sort.order = state.sort.order === 'asc' ? 'desc' : 'asc';
    } else {
        state.sort.field = field;
        // 지점명은 기본 오름차순, 나머지는 내림차순
        state.sort.order = order || (field === 'branch_name' ? 'asc' : 'desc');
    }
}

/**
 * 날짜 필터 설정
 * @param {string|null} from - 시작일
 * @param {string|null} to - 종료일
 */
export function setDateFilter(from, to) {
    state.dateFilter.from = from;
    state.dateFilter.to = to;
}

/**
 * 날짜 필터 초기화
 */
export function clearDateFilter() {
    state.dateFilter.from = null;
    state.dateFilter.to = null;
}

/**
 * Flatpickr 인스턴스 설정
 * @param {Object} picker - Flatpickr 인스턴스
 */
export function setDatePicker(picker) {
    state.dateFilter.picker = picker;
}

/**
 * 수정 모드 시작
 */
export function enterEditMode() {
    state.editMode.isActive = true;
    state.editMode.originalTags = [...state.editMode.selectedTags];
}

/**
 * 수정 모드 종료
 * @param {boolean} [restore=false] - 원본으로 복원 여부
 */
export function exitEditMode(restore = false) {
    state.editMode.isActive = false;
    if (restore) {
        state.editMode.selectedTags = [...state.editMode.originalTags];
    }
}

/**
 * 선택된 태그 설정
 * @param {string[]} tags - 태그 목록
 */
export function setSelectedTags(tags) {
    state.editMode.selectedTags = [...tags];
}

/**
 * 태그 토글 (선택/해제)
 * @param {string} tag - 태그명
 */
export function toggleTag(tag) {
    const idx = state.editMode.selectedTags.indexOf(tag);
    if (idx > -1) {
        state.editMode.selectedTags.splice(idx, 1);
    } else {
        state.editMode.selectedTags.push(tag);
    }
}

/**
 * 태그 추가
 * @param {string} tag - 태그명
 * @returns {boolean} 추가 성공 여부
 */
export function addTag(tag) {
    if (state.editMode.selectedTags.includes(tag)) {
        return false;
    }
    state.editMode.selectedTags.push(tag);
    return true;
}

/**
 * 태그 제거
 * @param {string} tag - 태그명
 */
export function removeTag(tag) {
    const idx = state.editMode.selectedTags.indexOf(tag);
    if (idx > -1) {
        state.editMode.selectedTags.splice(idx, 1);
    }
}

/**
 * 현재 요약 기간 설정
 * @param {string} period - 기간 코드 (all, 1y, 6m, 3m, 1m)
 */
export function setCurrentPeriod(period) {
    state.editMode.currentPeriod = period;
}

/**
 * 저장 후 원본 태그 업데이트
 */
export function commitTags() {
    state.editMode.originalTags = [...state.editMode.selectedTags];
}

/**
 * 리뷰 페이지 설정
 * @param {number} page - 페이지 번호
 */
export function setReviewsPage(page) {
    state.reviews.currentPage = Math.max(0, page);
}

/**
 * 리뷰 상태 리셋
 */
export function resetReviews() {
    state.reviews.currentPage = 0;
    state.reviews.total = 0;
    state.reviews.visible = false;
    state.reviews.carModelsLoaded = false;
}

/**
 * 리뷰 가시성 토글
 * @returns {boolean} 토글 후 가시성
 */
export function toggleReviewsVisibility() {
    state.reviews.visible = !state.reviews.visible;
    if (state.reviews.visible) {
        state.reviews.currentPage = 0;
        state.reviews.carModelsLoaded = false;
    }
    return state.reviews.visible;
}

/**
 * 리뷰 총 개수 설정
 * @param {number} total - 전체 개수
 */
export function setReviewsTotal(total) {
    state.reviews.total = total;
}

/**
 * 차량 모델 로드 완료 표시
 */
export function markCarModelsLoaded() {
    state.reviews.carModelsLoaded = true;
}

/**
 * 요약 데이터 설정
 * @param {Array} data - 요약 목록
 */
export function setSummaries(data) {
    state.summaries = data;
}

/**
 * 단일 요약 업데이트
 * @param {number} branchId - 지점 ID
 * @param {Object} updates - 업데이트할 필드
 */
export function updateSummary(branchId, updates) {
    const idx = state.summaries.findIndex(
        s => Number(s.branch_id) === Number(branchId)
    );
    if (idx > -1) {
        state.summaries[idx] = { ...state.summaries[idx], ...updates };
    }
}

/**
 * 지역 통계 설정
 * @param {Array} data - 지역 통계 목록
 */
export function setRegionStats(data) {
    state.regionStats = data;
}

// ============================================================
// Debug (디버깅용)
// ============================================================

/**
 * 현재 상태 콘솔 출력 (디버깅용)
 */
export function debugState() {
    console.log('📊 Dashboard State:', JSON.parse(JSON.stringify(state)));
}

// 개발 모드에서 전역으로 노출 (디버깅용)
if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
    window.__dashboardState = state;
    window.__debugState = debugState;
}
