/**
 * @fileoverview 대시보드 유틸리티 함수
 * @module dashboard/utils
 */

import { CONFIG } from './config.js';

// ============================================================
// Validation (유효성 검증)
// ============================================================

/**
 * 리뷰 ID 유효성 검증 (빈 값만 체크)
 * @param {string|number|null|undefined} reviewId - 검증할 리뷰 ID
 * @returns {boolean} 유효 여부
 */
export function isValidReviewId(reviewId) {
    return reviewId !== null && reviewId !== undefined && reviewId !== '';
}

// ============================================================
// Date Formatting (날짜 포맷팅)
// ============================================================

/**
 * Date 객체를 API 형식(YYYY-MM-DD)으로 변환
 * @param {Date} date - Date 객체
 * @returns {string} YYYY-MM-DD 형식 문자열
 */
export function formatDateForAPI(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/**
 * 날짜 문자열을 한국어 형식으로 포맷
 * @param {string|null} dateStr - ISO 날짜 문자열
 * @returns {string} 포맷된 날짜 또는 '-'
 */
export function formatDate(dateStr) {
    if (!dateStr) return '-';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        });
    } catch {
        return dateStr;
    }
}

// ============================================================
// Security (보안 유틸리티)
// ============================================================

/**
 * HTML 특수문자 이스케이프 (XSS 방지)
 * @param {string|null} text - 이스케이프할 텍스트
 * @returns {string} 이스케이프된 텍스트
 */
export function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Carmore 리뷰 관리 URL 생성
 * @param {string} reservationId - 예약번호 (URL 인코딩된 값)
 * @returns {string} 전체 URL
 */
export function buildCarmoreReviewUrl(reservationId) {
    const today = new Date();
    const threeMonthsAgo = new Date(today);
    threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);

    const endDate = formatDateForAPI(today);
    const startDate = formatDateForAPI(threeMonthsAgo);

    const params = new URLSearchParams({
        sp: 'reservation_idx',
        ratingthan: '0',
        sv: reservationId,
        ratingless: '5',
        startdate: startDate,
        enddate: endDate
    });

    return `${CONFIG.EXTERNAL_URLS.CARMORE_REVIEW_BASE}?${params.toString()}`;
}

// ============================================================
// UI Helpers (UI 헬퍼)
// ============================================================

/**
 * 문자열 기반 HSL 파스텔 배경색 생성
 * @param {string|null} str - 입력 문자열
 * @returns {string} HSL 색상 값
 */
export function getKeywordColor(str) {
    if (!str) return '#e5e7eb';
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const h = Math.abs(hash) % 360;
    return `hsl(${h}, 70%, 85%)`;
}

/**
 * 문자열 기반 HSL 텍스트 색상 생성 (어두운 버전)
 * @param {string|null} str - 입력 문자열
 * @returns {string} HSL 색상 값
 */
export function getKeywordTextColor(str) {
    if (!str) return '#374151';
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const h = Math.abs(hash) % 360;
    return `hsl(${h}, 80%, 30%)`;
}

/**
 * 평점을 별 아이콘 HTML로 변환
 * @param {number|null|undefined} rating - 평점 (0-5)
 * @returns {string} 별 아이콘 HTML
 */
export function getStarRating(rating) {
    if (rating === undefined || rating === null) return '-';
    const numRating = Number(rating);
    if (isNaN(numRating)) return '-';

    const fullStars = Math.floor(numRating);
    const hasHalfStar = numRating % 1 >= 0.5;
    let html = '<div class="rating" style="display:inline-flex; align-items:center;">';

    for (let i = 0; i < 5; i++) {
        if (i < fullStars) {
            html += '<span class="rating-star" style="color:#F59E0B;">★</span>';
        } else if (i === fullStars && hasHalfStar) {
            html += '<span class="rating-star" style="background: linear-gradient(90deg, #F59E0B 50%, #DDDDDD 50%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">★</span>';
        } else {
            html += '<span class="rating-star" style="color:#DDDDDD;">★</span>';
        }
    }
    html += `<span style="margin-left: 4px; color: var(--grey-4); font-weight: normal; font-size: 12px;">(${numRating.toFixed(1)})</span>`;
    html += '</div>';
    return html;
}

/**
 * 감정 상태를 아이콘으로 변환
 * @param {string|null} sentiment - 감정 (positive, neutral, negative)
 * @returns {string} 이모지 아이콘
 */
export function getSentimentIcon(sentiment) {
    switch (sentiment) {
        case 'positive': return '😊';
        case 'negative': return '😞';
        case 'neutral': return '😐';
        default: return '';
    }
}

// ============================================================
// Function Helpers (함수 헬퍼)
// ============================================================

/**
 * 디바운스 함수 생성
 * @param {Function} fn - 실행할 함수
 * @param {number} ms - 지연 시간 (밀리초)
 * @returns {Function} 디바운스된 함수
 */
export function debounce(fn, ms) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

/**
 * 쓰로틀 함수 생성
 * @param {Function} fn - 실행할 함수
 * @param {number} ms - 최소 실행 간격 (밀리초)
 * @returns {Function} 쓰로틀된 함수
 */
export function throttle(fn, ms) {
    let lastTime = 0;
    return function (...args) {
        const now = Date.now();
        if (now - lastTime >= ms) {
            lastTime = now;
            fn.apply(this, args);
        }
    };
}

// ============================================================
// Toast Notification (토스트 알림)
// ============================================================

/**
 * 토스트 알림 표시
 * @param {string} message - 알림 메시지
 * @param {'info'|'success'|'error'} [type='info'] - 알림 타입
 * @param {number} [duration=3000] - 표시 시간 (밀리초)
 */
export function showToast(message, type = 'info', duration = 3000) {
    // 기존 토스트 제거
    const existingToast = document.querySelector('.toast-notification');
    if (existingToast) existingToast.remove();

    const bgColors = {
        success: '#10b981',
        error: '#ef4444',
        info: '#3b82f6'
    };

    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        padding: 16px 24px;
        background: ${bgColors[type] || bgColors.info};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 2000;
        animation: slideIn 0.3s ease;
        font-size: 14px;
        font-weight: 500;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// Toast 애니메이션 스타일 추가 (최초 1회)
let toastStyleInjected = false;

/**
 * 토스트 애니메이션 스타일 주입
 */
export function injectToastStyles() {
    if (toastStyleInjected) return;

    const toastStyle = document.createElement('style');
    toastStyle.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(toastStyle);
    toastStyleInjected = true;
}
