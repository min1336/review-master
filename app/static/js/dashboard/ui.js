/**
 * @fileoverview 대시보드 UI 렌더링 모듈
 * @module dashboard/ui
 */

import { STATUS_CLASS_MAP, STATUS_LABEL_MAP, DEFAULT_TAGS, PERIOD_LABELS } from './config.js';
import { getState, getEditMode, getPagination, getSort } from './state.js';
import {
    escapeHtml,
    formatDate,
    getKeywordColor,
    getKeywordTextColor,
    getStarRating,
    getSentimentIcon,
    isValidReviewId,
    buildCarmoreReviewUrl
} from './utils.js';

// ============================================================
// DOM Selectors (DOM 셀렉터)
// ============================================================

/**
 * DOM 요소 캐시
 * @type {Object.<string, HTMLElement|null>}
 */
const elements = {};

/**
 * DOM 요소 가져오기 (캐싱)
 * @param {string} id - 요소 ID
 * @returns {HTMLElement|null}
 */
export function getElement(id) {
    if (!elements[id]) {
        elements[id] = document.getElementById(id);
    }
    return elements[id];
}

/**
 * DOM 캐시 초기화
 */
export function clearElementCache() {
    Object.keys(elements).forEach(key => delete elements[key]);
}

// ============================================================
// Stats Rendering (통계 렌더링)
// ============================================================

/**
 * 전체 통계 카드 렌더링
 * @param {Object} stats - 통계 데이터
 */
export function renderStats(stats) {
    const statTotal = getElement('stat-total');
    const statReviews = getElement('stat-reviews');
    const statPublished = getElement('stat-published');
    const statusStats = getElement('status-stats');

    if (statTotal) statTotal.textContent = stats.total?.toLocaleString() || '0';
    if (statReviews) statReviews.textContent = stats.total_reviews?.toLocaleString() || '0';
    if (statPublished) statPublished.textContent = stats.published?.toLocaleString() || '0';

    if (statusStats) {
        const total = stats.total || 1;
        const draftPct = Math.round((stats.draft || 0) / total * 100);
        const publishedPct = Math.round((stats.published || 0) / total * 100);

        statusStats.innerHTML = renderStatusBars({
            draft: { count: stats.draft || 0, pct: draftPct },
            published: { count: stats.published || 0, pct: publishedPct }
        });
    }
}

/**
 * 상태별 프로그레스 바 HTML 생성
 * @param {Object} data - 상태별 데이터
 * @returns {string} HTML 문자열
 */
function renderStatusBars(data) {
    return `
        <div style="display: flex; flex-direction: column; gap: 20px; padding: 8px 0;">
            ${renderStatusBar('Draft', data.draft, '#999', '#666', '#f0f0f0')}
            ${renderStatusBar('Published', data.published, '#10b981', '#059669', '#d1fae5')}
        </div>
    `;
}

/**
 * 단일 상태 프로그레스 바 HTML 생성
 * @param {string} label - 상태 라벨
 * @param {Object} data - { count, pct }
 * @param {string} colorStart - 그라데이션 시작 색
 * @param {string} colorEnd - 그라데이션 끝 색
 * @param {string} bgColor - 배경 색
 * @returns {string} HTML 문자열
 */
function renderStatusBar(label, data, colorStart, colorEnd, bgColor) {
    const icons = {
        'Draft': `<svg width="16" height="16" fill="none" stroke="${colorStart}" stroke-width="2" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
        </svg>`,
        'Published': `<svg width="16" height="16" fill="none" stroke="${colorStart}" stroke-width="2" viewBox="0 0 24 24">
            <polyline points="20 6 9 17 4 12"></polyline>
        </svg>`
    };

    const badgeClass = label === 'Draft' ? 'badge-grey' : 'badge-success';

    return `
        <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    ${icons[label]}
                    <span style="font-weight: 500;">${label}</span>
                </div>
                <span class="badge ${badgeClass}">${data.count}</span>
            </div>
            <div style="background: ${bgColor}; height: 6px; border-radius: 3px; overflow: hidden;">
                <div style="background: linear-gradient(90deg, ${colorStart} 0%, ${colorEnd} 100%); height: 100%; width: ${data.pct}%; transition: width 0.6s ease;"></div>
            </div>
        </div>
    `;
}

// ============================================================
// Table Rendering (테이블 렌더링)
// ============================================================

/**
 * 요약 테이블 렌더링
 * @param {Array} data - 요약 목록
 * @param {Function} onDetailClick - 상세 버튼 클릭 핸들러
 */
export function renderTable(data, onDetailClick) {
    const tableEl = getElement('summaries-table');
    const paginationInfo = getElement('pagination-info');
    const { pagination } = getState();

    if (!tableEl) return;

    if (!data || data.length === 0) {
        tableEl.innerHTML = '<tr><td colspan="7" style="text-align:center; color: var(--grey-5);">데이터 없음</td></tr>';
        if (paginationInfo) paginationInfo.textContent = '0개 지점';
        return;
    }

    const html = data.map(row => renderTableRow(row, onDetailClick)).join('');
    tableEl.innerHTML = html;

    if (paginationInfo) {
        const start = pagination.currentPage * pagination.pageSize + 1;
        const end = start + data.length - 1;
        paginationInfo.textContent = `${start}-${end}개 표시`;
    }
}

/**
 * 테이블 행 HTML 생성
 * @param {Object} row - 요약 데이터
 * @param {Function} onDetailClick - 클릭 핸들러
 * @returns {string} HTML 문자열
 */
function renderTableRow(row, onDetailClick) {
    const summaryPreview = row.summary_all
        ? (row.summary_all.length > 60 ? row.summary_all.substring(0, 60) + '...' : row.summary_all)
        : '<span style="color: var(--grey-5); font-style: italic;">요약 없음</span>';

    const tags = row.top_tags || [];
    const tagsHtml = tags.length > 0
        ? tags.map(t => `<span class="keyword" style="background: ${getKeywordColor(t.name)}; color: ${getKeywordTextColor(t.name)};">${t.name}</span>`).join('')
        : '<span style="color: var(--grey-5); font-style: italic;">-</span>';

    return `
        <tr style="vertical-align: middle;">
            <td>
                <div style="font-weight: 600; margin-bottom: 4px;">${row.branch_name || '-'}</div>
                <div>${getStarRating(row.avg_rating)}</div>
            </td>
            <td style="font-size: 13px; color: var(--grey-3); line-height: 1.5;">${summaryPreview}</td>
            <td style="text-align: center; font-weight: 600; font-size: 15px;">${row.review_count?.toLocaleString() || 0}</td>
            <td>
                <div class="keywords" style="display: flex; flex-wrap: wrap; gap: 4px;">
                    ${tagsHtml}
                </div>
            </td>
            <td style="text-align: center;">
                <span class="badge ${row.status === 'published' ? 'badge-success' : 'badge-grey'}">
                    ${row.status || 'draft'}
                </span>
            </td>
            <td style="text-align: center;">
                <button class="btn btn-secondary btn-sm" onclick="window.dashboardHandlers.showDetail(${row.branch_id})">상세</button>
            </td>
        </tr>
    `;
}

/**
 * 정렬 UI 업데이트
 */
export function updateSortUI() {
    const { sort } = getState();

    document.querySelectorAll('.sort-icon').forEach(el => el.textContent = '');

    const iconEl = getElement(`sort-icon-${sort.field}`);
    if (iconEl) {
        iconEl.textContent = sort.order === 'asc' ? ' ↑' : ' ↓';
        iconEl.style.color = 'var(--primary)';
    }
}

// ============================================================
// Review Rendering (리뷰 렌더링)
// ============================================================

/**
 * 리뷰 링크 HTML 생성
 * @param {string|number} reviewId - 리뷰 ID
 * @returns {string} HTML 문자열
 */
export function createReviewLinkHtml(reviewId) {
    if (!isValidReviewId(reviewId)) {
        return '';
    }

    const encodedId = encodeURIComponent(String(reviewId));
    const escapedId = escapeHtml(String(reviewId));
    const reviewUrl = buildCarmoreReviewUrl(encodedId);

    return `<a href="${reviewUrl}" target="_blank" rel="noopener noreferrer" class="review-link" title="Carmore 관리자에서 리뷰 보기">#${escapedId}</a>`;
}

/**
 * 단일 리뷰 아이템 HTML 렌더링
 * @param {Object} reviewData - 리뷰 데이터
 * @param {number} index - 인덱스
 * @param {number} pageOffset - 페이지 오프셋
 * @returns {string} HTML 문자열
 */
export function renderReviewItem(reviewData, index, pageOffset) {
    const reviewLink = createReviewLinkHtml(reviewData.review_id)
        || `<span>#${pageOffset + index + 1}</span>`;
    const sentimentIcon = reviewData.sentiment
        ? getSentimentIcon(reviewData.sentiment)
        : '';
    const escapedContent = escapeHtml(reviewData.content || '-');
    const formattedDate = formatDate(reviewData.review_date);
    const footerHtml = renderReviewFooter(reviewData);

    return `
        <div class="review-item">
            <div class="review-item__header">
                <span class="review-item__meta">
                    ${reviewLink}
                    ${sentimentIcon ? `<span class="review-item__sentiment">${sentimentIcon}</span>` : ''}
                </span>
                <span class="review-item__meta">${formattedDate}</span>
            </div>
            <div class="review-item__content">${escapedContent}</div>
            ${footerHtml}
        </div>
    `;
}

/**
 * 리뷰 푸터 HTML 렌더링
 * @param {Object} reviewData - 리뷰 데이터
 * @returns {string} HTML 문자열
 */
function renderReviewFooter(reviewData) {
    const metaParts = [];

    if (reviewData.rating_service) {
        metaParts.push(`친절: ${reviewData.rating_service}`);
    }
    if (reviewData.rating_car) {
        metaParts.push(`차량: ${reviewData.rating_car}`);
    }
    if (reviewData.car_model) {
        metaParts.push(escapeHtml(reviewData.car_model));
    }

    if (metaParts.length === 0) {
        return '';
    }

    return `<div class="review-item__footer">${metaParts.join(' | ')}</div>`;
}

/**
 * 리뷰 목록 렌더링
 * @param {Array} reviews - 리뷰 목록
 * @param {number} offset - 페이지 오프셋
 */
export function renderReviewsList(reviews, offset) {
    const listEl = getElement('reviews-list');
    if (!listEl) return;

    if (reviews.length === 0) {
        listEl.innerHTML = '<div class="review-item" style="text-align: center;">리뷰가 없습니다.</div>';
    } else {
        listEl.innerHTML = reviews.map((r, idx) => renderReviewItem(r, idx, offset)).join('');
    }
}

/**
 * 리뷰 페이지네이션 UI 업데이트
 * @param {number} currentPage - 현재 페이지
 * @param {number} totalPages - 전체 페이지
 */
export function updateReviewsPagination(currentPage, totalPages) {
    const pageInfo = getElement('reviews-page-info');
    const prevBtn = getElement('reviews-prev-btn');
    const nextBtn = getElement('reviews-next-btn');

    if (pageInfo) {
        pageInfo.textContent = `${currentPage + 1} / ${totalPages || 1}`;
    }
    if (prevBtn) {
        prevBtn.disabled = currentPage === 0;
    }
    if (nextBtn) {
        nextBtn.disabled = (currentPage + 1) >= totalPages;
    }
}

/**
 * 리뷰 개수 표시 업데이트
 * @param {number} total - 전체 개수
 */
export function updateReviewsCount(total) {
    const countEl = getElement('reviews-count');
    if (countEl) {
        countEl.textContent = `(총 ${total.toLocaleString()}건)`;
    }
}

/**
 * 차량 모델 드롭다운 업데이트
 * @param {string[]} carModels - 차량 모델 목록
 */
export function updateCarModelDropdown(carModels) {
    const carSelect = getElement('filter-car-model');
    if (carSelect && carModels.length > 0) {
        carSelect.innerHTML = '<option value="">🚗 전체 차량</option>' +
            carModels.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
    }
}

// ============================================================
// Tags Rendering (태그 렌더링)
// ============================================================

/**
 * 태그 표시 렌더링
 * @param {string[]} tags - 태그 목록
 */
export function renderTagsDisplay(tags) {
    const display = getElement('tags-display');
    if (!display) return;

    if (tags.length > 0) {
        display.innerHTML = tags.map(t =>
            `<span class="keyword" style="background: ${getKeywordColor(t)}; color: ${getKeywordTextColor(t)};">${t}</span>`
        ).join('');
    } else {
        display.innerHTML = '<span class="summary-empty">태그 없음</span>';
    }
}

/**
 * 태그 선택기 렌더링
 * @param {string[]} selectedTags - 선택된 태그
 * @param {Function} onToggle - 토글 핸들러
 * @param {Function} onRemove - 제거 핸들러
 */
export function renderTagSelector(selectedTags, onToggle, onRemove) {
    const selector = getElement('tag-selector');
    if (!selector) return;

    const allTags = [...new Set([...DEFAULT_TAGS, ...selectedTags])];

    selector.innerHTML = allTags.map(tag => {
        const isSelected = selectedTags.includes(tag);
        const isCustom = !DEFAULT_TAGS.includes(tag);
        const bg = isSelected ? getKeywordColor(tag) : 'var(--grey-8)';
        const color = isSelected ? getKeywordTextColor(tag) : 'var(--grey-3)';
        const border = isSelected ? '2px solid var(--primary)' : '2px solid transparent';
        const deleteBtn = isCustom
            ? `<span onclick="event.stopPropagation(); window.dashboardHandlers.removeCustomTag('${tag}')" style="margin-left: 4px; font-size: 10px;">✕</span>`
            : '';

        return `<span class="keyword" onclick="window.dashboardHandlers.toggleTag('${tag}')"
            style="background: ${bg}; color: ${color}; border: ${border}; cursor: pointer; user-select: none;"
            data-tag="${tag}">${tag}${deleteBtn}</span>`;
    }).join('');
}

// ============================================================
// Modal Rendering (모달 렌더링)
// ============================================================

/**
 * 모달 열기
 */
export function openModal() {
    const modal = getElement('detail-modal');
    if (modal) modal.classList.add('active');
}

/**
 * 모달 닫기
 */
export function closeModal() {
    const modal = getElement('detail-modal');
    if (modal) modal.classList.remove('active');
}

/**
 * 모달 로딩 표시
 */
export function showModalLoading() {
    const body = getElement('modal-body');
    if (body) {
        body.innerHTML = '<div class="loading"><div class="spinner"></div>로딩 중...</div>';
    }
}

/**
 * 모달 에러 표시
 * @param {string} [message='로드 실패'] - 에러 메시지
 */
export function showModalError(message = '로드 실패') {
    const body = getElement('modal-body');
    if (body) {
        body.innerHTML = `<div style="color: var(--error);">${escapeHtml(message)}</div>`;
    }
}

/**
 * 모달 제목 설정
 * @param {string} title - 제목
 */
export function setModalTitle(title) {
    const titleEl = getElement('modal-title');
    if (titleEl) titleEl.textContent = title;
}

// ============================================================
// Edit Mode UI (수정 모드 UI)
// ============================================================

/**
 * 수정 모드 UI 전환
 * @param {boolean} isEditMode - 수정 모드 여부
 */
export function toggleEditModeUI(isEditMode) {
    const viewButtons = getElement('view-mode-buttons');
    const editButtons = getElement('edit-mode-buttons');
    const regionDisplay = getElement('region-display');
    const regionInput = getElement('region-input');
    const tagsDisplay = getElement('tags-display');
    const editAreaTags = getElement('edit-area-tags');

    if (viewButtons) viewButtons.style.display = isEditMode ? 'none' : 'flex';
    if (editButtons) editButtons.style.display = isEditMode ? 'flex' : 'none';
    if (regionDisplay) regionDisplay.style.display = isEditMode ? 'none' : 'block';
    if (regionInput) regionInput.style.display = isEditMode ? 'block' : 'none';
    if (tagsDisplay) tagsDisplay.style.display = isEditMode ? 'none' : 'flex';
    if (editAreaTags) editAreaTags.style.display = isEditMode ? 'block' : 'none';

    // 요약 텍스트/에디터 전환
    ['all', '1y', '6m', '3m', '1m'].forEach(period => {
        const textEl = getElement(`summary-text-${period}`);
        const editEl = getElement(`edit-summary-${period}`);
        if (textEl) textEl.style.display = isEditMode ? 'none' : 'block';
        if (editEl) editEl.style.display = isEditMode ? 'block' : 'none';
    });
}

/**
 * 요약 탭 전환
 * @param {HTMLElement} tabEl - 탭 요소
 * @param {string} period - 기간
 */
export function showSummaryTab(tabEl, period) {
    // 모든 탭 비활성화
    document.querySelectorAll('.tabs .tab').forEach(t => {
        t.classList.remove('active');
        t.style.background = 'var(--grey-8)';
        t.style.color = 'var(--grey-3)';
    });

    // 선택된 탭 활성화
    if (tabEl) {
        tabEl.classList.add('active');
        tabEl.style.background = 'var(--grey-2)';
        tabEl.style.color = 'white';
    }

    // 패널 전환
    document.querySelectorAll('.summary-panel').forEach(p => p.style.display = 'none');
    const panel = getElement(`panel-${period}`);
    if (panel) panel.style.display = 'block';
}

// ============================================================
// Loading States (로딩 상태)
// ============================================================

/**
 * 리뷰 목록 로딩 표시
 */
export function showReviewsLoading() {
    const listEl = getElement('reviews-list');
    if (listEl) {
        listEl.innerHTML = '<div class="loading"><div class="spinner"></div>로딩 중...</div>';
    }
}

/**
 * 테이블 로딩/에러 표시
 * @param {string} message - 메시지
 * @param {boolean} [isError=false] - 에러 여부
 */
export function showTableMessage(message, isError = false) {
    const tableEl = getElement('summaries-table');
    if (tableEl) {
        const style = isError ? 'color: var(--error);' : 'color: var(--grey-5);';
        tableEl.innerHTML = `<tr><td colspan="7" style="text-align:center; ${style}">${escapeHtml(message)}</td></tr>`;
    }
}
