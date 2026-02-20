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
        success: '#10b981',
        error: '#ef4444',
        warning: '#f59e0b',
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
 * API 요청 래퍼
 * ============================================================ */

async function apiRequest(url, options) {
    if (!options) options = {};
    const response = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        ...options
    });

    if (!response.ok) {
        const error = await response.json().catch(function () { return {}; });
        throw new Error(error.error || error.detail || 'HTTP ' + response.status);
    }

    return response.json();
}
