/**
 * shared-utils.js — 4개 HTML 템플릿 공통 유틸리티
 *
 * 포함 함수:
 *   escapeHtml, escapeAttr, formatDate, formatDateForAPI,
 *   debounce, showToast, apiRequest
 */

/* ============================================================
 * XSS 방어 유틸
 * ============================================================ */

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/'/g, '&#39;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

/* ============================================================
 * 날짜 포맷
 * ============================================================ */

function formatDate(dateStr) {
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

function formatDateForAPI(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/* ============================================================
 * 범용 유틸
 * ============================================================ */

function debounce(fn, ms) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

/* ============================================================
 * Toast 알림
 * ============================================================ */

function showToast(message, type, duration) {
    if (type === undefined) type = 'info';
    if (duration === undefined) duration = 3000;

    const existingToast = document.querySelector('.toast-notification');
    if (existingToast) existingToast.remove();

    const bgColors = {
        success: '#16a34a',
        error: '#dc2626',
        warning: '#ea580c',
        info: '#0d6ffc'
    };

    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        padding: 16px 24px;
        background: ${bgColors[type] || bgColors.info};
        color: ${type === 'warning' ? '#78350f' : 'white'};
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 2000;
        animation: slideIn 0.3s ease;
        font-size: 14px;
        font-weight: 500;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(function () {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(function () { toast.remove(); }, 300);
    }, duration);
}

/* ============================================================
 * fetch 503 재시도 래퍼 (drop-in replacement)
 * uvicorn --limit-concurrency 제한 시 503은 요청 미처리 거부이므로
 * 모든 HTTP 메서드에 대해 재시도가 안전함
 * ============================================================ */

async function fetchRetry(url, options) {
    if (!options) options = {};
    // 인증은 세션 쿠키(HttpOnly)로 자동 전송됨 — API 키를 JS에 노출하지 않음
    var maxRetries = 2;
    for (var attempt = 0; attempt <= maxRetries; attempt++) {
        var response = await fetch(url, options);
        if (response.status === 401) {
            // 세션 만료 → 로그인 페이지로 리다이렉트
            var basePath = window.__BASE_PATH__ || '';
            window.location.href = basePath + '/login?error=expired&next=' + encodeURIComponent(window.location.pathname);
            return response;
        }
        if ((response.status === 502 || response.status === 503) && attempt < maxRetries) {
            await new Promise(function (r) { setTimeout(r, 300 * (attempt + 1)); });
            continue;
        }
        return response;
    }
}

/* ============================================================
 * API 요청 래퍼
 * ============================================================ */

async function apiRequest(url, options) {
    if (!options) options = {};
    var headers = {
        'Content-Type': 'application/json',
    };
    Object.assign(headers, options.headers);
    var finalOptions = Object.assign({}, options);
    delete finalOptions.headers;
    var response = await fetchRetry(url, Object.assign({ headers: headers }, finalOptions));

    if (!response.ok) {
        var error = await response.json().catch(function () { return {}; });
        throw new Error(error.error || error.detail || 'HTTP ' + response.status);
    }

    return response.json();
}
