/**
 * @fileoverview 대시보드 설정 상수
 * @module dashboard/config
 */

/**
 * 외부 URL 설정
 * @typedef {Object} ExternalUrls
 * @property {string} CARMORE_REVIEW_BASE - Carmore 리뷰 관리 페이지 기본 URL
 */

/**
 * 페이지네이션 설정
 * @typedef {Object} PaginationConfig
 * @property {number} DEFAULT_PAGE_SIZE - 기본 페이지 크기
 * @property {number} REVIEWS_PAGE_SIZE - 리뷰 목록 페이지 크기
 */

/**
 * 유효성 검증 설정
 * @typedef {Object} ValidationConfig
 * @property {RegExp} REVIEW_ID_PATTERN - 리뷰 ID 패턴
 */

/**
 * 대시보드 전역 설정
 * @type {Object}
 * @property {ExternalUrls} EXTERNAL_URLS - 외부 URL
 * @property {PaginationConfig} PAGINATION - 페이지네이션
 * @property {ValidationConfig} VALIDATION - 유효성 검증
 */
export const CONFIG = Object.freeze({
    EXTERNAL_URLS: {
        CARMORE_REVIEW_BASE: 'https://dev-admin.carmore.kr/partners/Reviewmanage'
    },
    PAGINATION: {
        DEFAULT_PAGE_SIZE: 500,
        REVIEWS_PAGE_SIZE: 20
    },
    VALIDATION: {
        REVIEW_ID_PATTERN: /^[a-zA-Z0-9_-]+$/
    }
});

/**
 * 상태 클래스 매핑
 * @type {Object.<string, string>}
 */
export const STATUS_CLASS_MAP = Object.freeze({
    'draft': 'grey',
    'published': 'success'
});

/**
 * 상태 라벨 매핑
 * @type {Object.<string, string>}
 */
export const STATUS_LABEL_MAP = Object.freeze({
    'draft': '보류',
    'published': '게시'
});

/**
 * 기본 태그 목록
 * @type {string[]}
 */
export const DEFAULT_TAGS = Object.freeze([
    '고객응대',
    '차량상태',
    '가성비',
    '반납/픽업',
    '위치/접근성',
    '서비스',
    '보험/보장'
]);

/**
 * 기간 라벨 매핑
 * @type {Object.<string, string>}
 */
export const PERIOD_LABELS = Object.freeze({
    'all': '전체',
    '1y': '1년',
    '6m': '6개월',
    '3m': '3개월',
    '1m': '1개월'
});
