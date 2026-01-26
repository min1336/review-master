/**
 * @fileoverview 대시보드 메인 컨트롤러
 * @module dashboard/index
 */

import { CONFIG, STATUS_CLASS_MAP, STATUS_LABEL_MAP, DEFAULT_TAGS, PERIOD_LABELS } from './config.js';
import * as state from './state.js';
import * as api from './api.js';
import * as ui from './ui.js';
import {
    debounce,
    formatDateForAPI,
    escapeHtml,
    showToast,
    injectToastStyles,
    getKeywordColor,
    getKeywordTextColor,
    getStarRating
} from './utils.js';

// ============================================================
// Initialization (초기화)
// ============================================================

/**
 * 대시보드 초기화
 */
export function init() {
    injectToastStyles();
    bindEvents();
    initDateRangePicker();

    // 초기 데이터 로드
    loadStats();
    loadRegionStats();
    loadSummaries();

    // 전역 핸들러 등록 (HTML onclick 이벤트용)
    registerGlobalHandlers();

    console.log('✅ Dashboard initialized');
}

/**
 * 전역 핸들러 등록 (HTML에서 onclick 사용 시)
 */
function registerGlobalHandlers() {
    window.dashboardHandlers = {
        showDetail,
        handleSort,
        prevPage,
        nextPage,
        toggleReviews,
        loadMoreReviews,
        applyFilters,
        enterEditMode,
        cancelEditMode,
        saveAllChanges,
        updateStatus,
        showSummaryTab,
        regenerateSummary,
        applyPendingSummary,
        discardPendingSummary,
        toggleTag,
        addCustomTag,
        removeCustomTag,
        closeModal,
        clearDateFilter,
        syncAffiliates
    };
}

/**
 * 이벤트 바인딩
 */
function bindEvents() {
    const searchInput = ui.getElement('search-input');
    const filterRegion = ui.getElement('filter-region');
    const filterStatus = ui.getElement('filter-status');
    const modal = ui.getElement('detail-modal');

    // 검색 입력 (디바운스)
    if (searchInput) {
        searchInput.addEventListener('input', debounce(() => {
            state.resetPage();
            loadSummaries();
        }, 300));
    }

    // 지역 필터
    if (filterRegion) {
        filterRegion.addEventListener('change', () => {
            state.resetPage();
            loadSummaries();
        });
    }

    // 상태 필터
    if (filterStatus) {
        filterStatus.addEventListener('change', () => {
            state.resetPage();
            loadSummaries();
        });
    }

    // 모달 외부 클릭 시 닫기
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-overlay')) {
                closeModal();
            }
        });
    }
}

/**
 * 날짜 선택기 초기화 (Flatpickr)
 */
function initDateRangePicker() {
    const picker = flatpickr('#filter-date-range', {
        mode: 'range',
        locale: 'ko',
        dateFormat: 'Y-m-d',
        maxDate: 'today',
        onChange: function (selectedDates) {
            if (selectedDates.length === 2) {
                state.setDateFilter(
                    formatDateForAPI(selectedDates[0]),
                    formatDateForAPI(selectedDates[1])
                );
                ui.getElement('btn-clear-date').style.display = 'inline-block';
                state.resetPage();
                loadSummaries();
            }
        },
        onClose: function (selectedDates) {
            if (selectedDates.length === 1) {
                const dateStr = formatDateForAPI(selectedDates[0]);
                state.setDateFilter(dateStr, dateStr);
                ui.getElement('btn-clear-date').style.display = 'inline-block';
                state.resetPage();
                loadSummaries();
            }
        }
    });

    state.setDatePicker(picker);
}

// ============================================================
// Data Loading (데이터 로드)
// ============================================================

/**
 * 통계 로드
 */
async function loadStats() {
    try {
        const stats = await api.fetchStats();
        ui.renderStats(stats);
    } catch (e) {
        console.error('Stats load error:', e);
    }
}

/**
 * 지역 통계 로드 (필터 드롭다운용)
 */
async function loadRegionStats() {
    try {
        const data = await api.fetchRegionStats();
        state.setRegionStats(data);

        // 필터 드롭다운 채우기
        const select = ui.getElement('filter-region');
        if (select) {
            data.forEach(r => {
                if (r.region && r.region !== '미분류') {
                    const opt = document.createElement('option');
                    opt.value = r.region;
                    opt.textContent = `${r.region} (${r.count})`;
                    select.appendChild(opt);
                }
            });
        }

        // 총 리뷰 수 업데이트
        const totalReviews = data.reduce((sum, r) => sum + (r.total_reviews || 0), 0);
        const statReviews = ui.getElement('stat-reviews');
        if (statReviews) {
            statReviews.textContent = totalReviews.toLocaleString();
        }
    } catch (e) {
        console.error('Region stats error:', e);
    }
}

/**
 * 요약 목록 로드
 */
async function loadSummaries() {
    const filters = {
        keyword: ui.getElement('search-input')?.value || '',
        region: ui.getElement('filter-region')?.value || '',
        status: ui.getElement('filter-status')?.value || ''
    };

    ui.updateSortUI();

    try {
        let data = await api.fetchSummaries(filters);

        // 태그 일괄 로드
        const branchIds = data.map(d => d.branch_id).filter(Boolean);
        let tagsData = {};

        if (branchIds.length > 0) {
            try {
                tagsData = await api.fetchBranchTagsBatch(branchIds);
            } catch (e) {
                console.error('Tags load error:', e);
            }
        }

        // 태그 병합 (keywords 우선)
        data.forEach(row => {
            if (Array.isArray(row.keywords)) {
                row.top_tags = row.keywords.map(k => ({ name: k }));
            } else {
                row.top_tags = tagsData[String(row.branch_id)] || [];
            }
        });

        state.setSummaries(data);
        ui.renderTable(data, showDetail);
    } catch (e) {
        console.error('Summaries load error:', e);
        ui.showTableMessage('로드 실패', true);
    }
}

// ============================================================
// Sorting & Pagination (정렬 & 페이지네이션)
// ============================================================

/**
 * 정렬 처리
 * @param {string} field - 정렬 필드
 */
function handleSort(field) {
    state.setSort(field);
    state.resetPage();
    loadSummaries();
}

/**
 * 이전 페이지
 */
function prevPage() {
    const { pagination } = state.getState();
    if (pagination.currentPage > 0) {
        state.prevPage();
        loadSummaries();
    }
}

/**
 * 다음 페이지
 */
function nextPage() {
    const summaries = state.getSummaries();
    const { pagination } = state.getState();
    if (summaries.length === pagination.pageSize) {
        state.nextPage();
        loadSummaries();
    }
}

// ============================================================
// Date Filter (날짜 필터)
// ============================================================

/**
 * 날짜 필터 초기화
 */
function clearDateFilter() {
    const { dateFilter } = state.getState();
    if (dateFilter.picker) {
        dateFilter.picker.clear();
    }
    state.clearDateFilter();
    ui.getElement('btn-clear-date').style.display = 'none';
    state.resetPage();
    loadSummaries();
}

// ============================================================
// Modal Detail (모달 상세)
// ============================================================

/**
 * 상세 모달 표시
 * @param {number} branchId - 지점 ID
 */
async function showDetail(branchId) {
    ui.openModal();
    ui.showModalLoading();
    state.resetReviews();

    try {
        const data = await api.fetchSummaryDetail(branchId);
        ui.setModalTitle(data.branch_name || `지점 ${branchId}`);

        const modalHtml = buildDetailModalHtml(data);
        ui.getElement('modal-body').innerHTML = modalHtml;

        // 태그 로드
        await loadBranchTags(data, branchId);
    } catch (e) {
        console.error('Detail load error:', e);
        ui.showModalError();
    }
}

/**
 * 상세 모달 HTML 생성
 * @param {Object} data - 요약 상세 데이터
 * @returns {string} HTML 문자열
 */
function buildDetailModalHtml(data) {
    const pendingSummaries = data.pending_summaries || {};

    return `
        <div class="modal-header-content" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px;">
            <div style="flex: 1;">
                <div style="font-size: 14px; color: var(--grey-5); margin-bottom: 4px;">ID: ${data.branch_id}</div>
                <h2 style="font-size: 24px; font-weight: 700; color: var(--grey-1); margin: 0;">${data.branch_name}</h2>
                <div id="region-display" style="font-size: 14px; color: var(--grey-3); margin-top: 4px;">${data.region || '지역 정보 없음'}</div>
                <input type="text" id="region-input" value="${data.region || ''}" placeholder="지역 입력 (예: 서울 강남구)"
                    style="display: none; margin-top: 8px; padding: 8px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 14px; width: 100%; max-width: 300px;">
            </div>
            <div>
                <span class="badge badge-${STATUS_CLASS_MAP[data.status] || 'grey'}" style="font-size: 14px; padding: 6px 12px;">
                    ${STATUS_LABEL_MAP[data.status] || data.status}
                </span>
            </div>
        </div>

        <!-- Tags -->
        <div style="margin-bottom: 24px;">
            <div style="font-size: 14px; font-weight: 600; color: var(--grey-3); margin-bottom: 8px;">태그</div>
            <div class="keywords" id="tags-display" style="display: flex; gap: 8px; flex-wrap: wrap;">
                <span class="summary-empty">로딩 중...</span>
            </div>
            <div id="edit-area-tags" style="display: none; margin-top: 12px;">
                <div style="font-size: 12px; color: var(--grey-5); margin-bottom: 8px;">클릭하여 선택/해제:</div>
                <div id="tag-selector" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;"></div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <input type="text" id="custom-tag-input" placeholder="커스텀 태그 입력"
                        style="padding: 6px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 13px; width: 150px;">
                    <button class="btn btn-secondary btn-sm" onclick="window.dashboardHandlers.addCustomTag()">+ 추가</button>
                </div>
            </div>
        </div>

        <!-- Stats Grid -->
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 32px;">
            <div style="background: var(--grey-9); padding: 16px; border-radius: var(--radius);">
                <div style="font-size: 13px; color: var(--grey-5);">총 리뷰 수</div>
                <div style="font-size: 20px; font-weight: 700; color: var(--grey-1); margin-top: 4px;">${data.review_count?.toLocaleString() || 0}건</div>
            </div>
            <div style="background: var(--grey-9); padding: 16px; border-radius: var(--radius);">
                <div style="font-size: 13px; color: var(--grey-5);">평균 평점</div>
                <div style="font-size: 20px; font-weight: 700; color: var(--grey-1); margin-top: 4px;">⭐ ${data.avg_rating?.toFixed(2) || '0.0'}</div>
            </div>
        </div>

        <!-- Summary Tabs -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <div class="tabs" style="display: flex; gap: 8px;">
                ${['all', '1y', '6m', '3m', '1m'].map((p, i) => `
                    <div class="tab ${i === 0 ? 'active' : ''}" onclick="window.dashboardHandlers.showSummaryTab(this, '${p}')"
                        style="padding: 8px 16px; cursor: pointer; font-weight: 500; font-size: 13px; border-radius: 20px;
                        background: ${i === 0 ? 'var(--grey-2)' : 'var(--grey-8)'}; color: ${i === 0 ? 'white' : 'var(--grey-3)'}; transition: all 0.2s;">
                        ${PERIOD_LABELS[p]}
                    </div>
                `).join('')}
            </div>
            <button class="btn-ai-summary" onclick="window.dashboardHandlers.regenerateSummary(${data.branch_id})" title="AI 요약 재생성">
                ✨ AI 요약
            </button>
        </div>

        <!-- Summary Content -->
        <div id="summary-content" style="min-height: 200px; background: white; border-radius: 0 0 var(--radius) var(--radius);">
            ${['all', '1y', '6m', '3m', '1m'].map((period, i) => {
        const hasPending = !!pendingSummaries[period];
        return `
                <div class="summary-panel" id="panel-${period}" style="display: ${i === 0 ? 'block' : 'none'};">
                    <div class="summary-text" id="summary-text-${period}" style="font-size: 15px; line-height: 1.7; color: var(--grey-2); white-space: pre-line;">
                        ${data['summary_' + period] || '<span class="summary-empty" style="color: var(--grey-5); font-style: italic;">작성된 요약이 없습니다.</span>'}
                    </div>
                    <textarea id="edit-summary-${period}" style="display: none; width: 100%; min-height: 120px; padding: 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 14px; line-height: 1.6; resize: vertical; font-family: inherit;">${data['summary_' + period] || ''}</textarea>

                    <div id="pending-section-${period}" class="pending-summary-section" style="display: ${hasPending ? 'block' : 'none'}; margin-top: 16px; padding: 16px; background: var(--primary-light); border: 2px dashed var(--primary); border-radius: var(--radius-sm);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span style="font-size: 13px; font-weight: 600; color: var(--primary);">✨ 신규 생성 요약</span>
                            <div style="display: flex; gap: 8px;">
                                <button class="btn btn-primary btn-sm" onclick="window.dashboardHandlers.applyPendingSummary(${data.branch_id}, '${period}')" style="font-size: 12px; padding: 4px 12px;">변경</button>
                                <button class="btn btn-secondary btn-sm" onclick="window.dashboardHandlers.discardPendingSummary(${data.branch_id}, '${period}')" style="font-size: 12px; padding: 4px 12px;">취소</button>
                            </div>
                        </div>
                        <div id="pending-text-${period}" style="font-size: 14px; line-height: 1.6; color: var(--grey-2); white-space: pre-line;">${pendingSummaries[period] || ''}</div>
                    </div>
                </div>
            `}).join('')}
        </div>

        <!-- Action Buttons -->
        <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--grey-8);">
            <div id="view-mode-buttons" style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; gap: 8px;">
                    <button class="btn btn-secondary" onclick="window.dashboardHandlers.enterEditMode()">✏️ 수정</button>
                    <button class="btn btn-secondary" onclick="window.dashboardHandlers.toggleReviews(${data.branch_id})" id="btn-toggle-reviews">📋 리뷰 보기</button>
                </div>
                <div style="display: flex; gap: 8px;">
                    <button class="btn btn-secondary btn-sm" onclick="window.dashboardHandlers.updateStatus(${data.branch_id}, 'draft')">보류</button>
                    <button class="btn btn-secondary btn-sm" onclick="window.dashboardHandlers.updateStatus(${data.branch_id}, 'approved')">승인</button>
                    <button class="btn btn-primary btn-sm" onclick="window.dashboardHandlers.updateStatus(${data.branch_id}, 'published')">게시</button>
                </div>
            </div>
            <div id="edit-mode-buttons" style="display: none; justify-content: flex-end; gap: 12px;">
                <button class="btn btn-secondary" onclick="window.dashboardHandlers.cancelEditMode()">취소</button>
                <button class="btn btn-primary" onclick="window.dashboardHandlers.saveAllChanges(${data.branch_id})">💾 저장</button>
            </div>
        </div>

        <!-- Reviews Section -->
        <div id="reviews-section" style="display: none; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--grey-8);">
            <div style="font-size: 14px; font-weight: 600; color: var(--grey-3); margin-bottom: 12px;">
                📋 리뷰 목록 <span id="reviews-count" style="font-weight: normal; color: var(--grey-5);"></span>
            </div>
            <div id="reviews-filters" style="display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;">
                <select id="filter-car-model" onchange="window.dashboardHandlers.applyFilters(${data.branch_id})" style="padding: 6px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 13px; background: white;">
                    <option value="">🚗 전체 차량</option>
                </select>
                <select id="filter-sentiment" onchange="window.dashboardHandlers.applyFilters(${data.branch_id})" style="padding: 6px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 13px; background: white;">
                    <option value="">💬 전체 감정</option>
                    <option value="positive">😊 긍정</option>
                    <option value="neutral">😐 중립</option>
                    <option value="negative">😞 부정</option>
                </select>
            </div>
            <div id="reviews-list" style="max-height: 400px; overflow-y: auto; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); background: var(--grey-9);">
                <div class="loading"><div class="spinner"></div>로딩 중...</div>
            </div>
            <div style="margin-top: 12px; display: flex; justify-content: center; gap: 8px;">
                <button class="btn btn-secondary btn-sm" onclick="window.dashboardHandlers.loadMoreReviews(${data.branch_id}, 'prev')" id="reviews-prev-btn" disabled>이전</button>
                <span id="reviews-page-info" style="font-size: 13px; color: var(--grey-5); line-height: 32px;">-</span>
                <button class="btn btn-secondary btn-sm" onclick="window.dashboardHandlers.loadMoreReviews(${data.branch_id}, 'next')" id="reviews-next-btn">다음</button>
            </div>
        </div>
    `;
}

/**
 * 지점 태그 로드
 * @param {Object} data - 요약 데이터
 * @param {number} branchId - 지점 ID
 */
async function loadBranchTags(data, branchId) {
    let tags = [];

    if (Array.isArray(data.keywords)) {
        tags = [...data.keywords];
    } else {
        try {
            const tagsData = await api.fetchBranchTagsBatch([branchId]);
            const branchTags = tagsData[String(branchId)] || [];
            tags = branchTags.map(t => t.name);
        } catch (e) {
            console.error('Tags load error:', e);
        }
    }

    state.setSelectedTags(tags);
    state.commitTags();
    ui.renderTagsDisplay(tags);
}

/**
 * 모달 닫기
 */
function closeModal() {
    ui.closeModal();
}

// ============================================================
// Edit Mode (수정 모드)
// ============================================================

/**
 * 수정 모드 진입
 */
function enterEditMode() {
    state.enterEditMode();
    ui.toggleEditModeUI(true);

    const { editMode } = state.getState();
    ui.renderTagSelector(editMode.selectedTags, toggleTag, removeCustomTag);
}

/**
 * 수정 모드 취소
 */
function cancelEditMode() {
    state.exitEditMode(true);
    ui.toggleEditModeUI(false);

    const { editMode } = state.getState();
    ui.renderTagsDisplay(editMode.selectedTags);
}

/**
 * 모든 변경사항 저장
 * @param {number} branchId - 지점 ID
 */
async function saveAllChanges(branchId) {
    const region = ui.getElement('region-input')?.value.trim() || '';
    const { editMode } = state.getState();

    const summariesData = {};
    ['all', '1y', '6m', '3m', '1m'].forEach(period => {
        const el = ui.getElement(`edit-summary-${period}`);
        if (el) summariesData[`summary_${period}`] = el.value;
    });

    try {
        const response = await api.updateSummary(branchId, {
            region,
            keywords: editMode.selectedTags,
            ...summariesData
        });

        if (response.success) {
            // UI 업데이트
            ui.getElement('region-display').textContent = region || '지역 정보 없음';

            ['all', '1y', '6m', '3m', '1m'].forEach(period => {
                const textEl = ui.getElement(`summary-text-${period}`);
                const editEl = ui.getElement(`edit-summary-${period}`);
                if (textEl && editEl) {
                    textEl.innerHTML = editEl.value || '<span class="summary-empty">작성된 요약이 없습니다.</span>';
                }
            });

            // 상태 업데이트
            state.commitTags();
            state.updateSummary(branchId, {
                region,
                top_tags: editMode.selectedTags.map(t => ({ name: t })),
                summary_all: summariesData.summary_all
            });

            // 테이블 재렌더링
            ui.renderTable(state.getSummaries(), showDetail);

            // 수정 모드 종료
            state.exitEditMode(false);
            ui.toggleEditModeUI(false);
            ui.renderTagsDisplay(editMode.selectedTags);

            showToast('✅ 저장되었습니다.', 'success');
        } else {
            showToast('저장 실패', 'error');
        }
    } catch (e) {
        console.error('Save error:', e);
        showToast('저장 중 오류 발생', 'error');
    }
}

// ============================================================
// Tags (태그)
// ============================================================

/**
 * 태그 토글
 * @param {string} tag - 태그명
 */
function toggleTag(tag) {
    state.toggleTag(tag);
    const { editMode } = state.getState();
    ui.renderTagSelector(editMode.selectedTags, toggleTag, removeCustomTag);
}

/**
 * 커스텀 태그 추가
 */
function addCustomTag() {
    const input = ui.getElement('custom-tag-input');
    const tagName = input?.value.trim();

    if (!tagName) return;

    if (!state.addTag(tagName)) {
        alert('이미 존재하는 태그입니다.');
        return;
    }

    input.value = '';
    const { editMode } = state.getState();
    ui.renderTagSelector(editMode.selectedTags, toggleTag, removeCustomTag);
}

/**
 * 커스텀 태그 제거
 * @param {string} tag - 태그명
 */
function removeCustomTag(tag) {
    state.removeTag(tag);
    const { editMode } = state.getState();
    ui.renderTagSelector(editMode.selectedTags, toggleTag, removeCustomTag);
}

// ============================================================
// Summary Tabs & AI (요약 탭 & AI)
// ============================================================

/**
 * 요약 탭 전환
 * @param {HTMLElement} tabEl - 탭 요소
 * @param {string} period - 기간
 */
function showSummaryTab(tabEl, period) {
    state.setCurrentPeriod(period);
    ui.showSummaryTab(tabEl, period);
}

/**
 * AI 요약 재생성
 * @param {number} branchId - 지점 ID
 */
async function regenerateSummary(branchId) {
    const { editMode } = state.getState();
    const period = editMode.currentPeriod;

    if (!confirm(`[${PERIOD_LABELS[period]}] 기간의 요약을 AI로 재생성하시겠습니까?\n\n새 요약이 생성되며, "변경" 버튼을 눌러야 적용됩니다.`)) {
        return;
    }

    const btn = event.target;
    const originalText = btn.innerHTML;

    try {
        btn.innerHTML = '⏳ 생성 중...';
        btn.disabled = true;

        const result = await api.regenerateSummary(branchId, period);

        if (result.success) {
            const pendingSection = ui.getElement(`pending-section-${period}`);
            const pendingText = ui.getElement(`pending-text-${period}`);

            if (pendingSection && pendingText) {
                pendingText.innerHTML = result.summary;
                pendingSection.style.display = 'block';
            }

            showToast(`✨ [${PERIOD_LABELS[period]}] 새 요약이 생성되었습니다.`, 'success');
        } else {
            throw new Error(result.error || '요약 생성 실패');
        }
    } catch (error) {
        console.error('Regenerate error:', error);
        showToast('❌ 요약 생성 실패: ' + error.message, 'error');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

/**
 * 대기 요약 적용
 * @param {number} branchId - 지점 ID
 * @param {string} period - 기간
 */
async function applyPendingSummary(branchId, period) {
    if (!confirm(`[${PERIOD_LABELS[period]}] 새 요약을 적용하시겠습니까?`)) {
        return;
    }

    try {
        const result = await api.applyPendingSummary(branchId, period);

        if (result.success) {
            const textEl = ui.getElement(`summary-text-${period}`);
            const editEl = ui.getElement(`edit-summary-${period}`);
            const pendingSection = ui.getElement(`pending-section-${period}`);

            if (textEl) textEl.innerHTML = result.applied;
            if (editEl) editEl.value = result.applied;
            if (pendingSection) pendingSection.style.display = 'none';

            showToast(`✅ [${PERIOD_LABELS[period]}] 요약이 적용되었습니다`, 'success');
        }
    } catch (error) {
        console.error('Apply error:', error);
        showToast('❌ 적용 실패: ' + error.message, 'error');
    }
}

/**
 * 대기 요약 취소
 * @param {number} branchId - 지점 ID
 * @param {string} period - 기간
 */
async function discardPendingSummary(branchId, period) {
    if (!confirm(`[${PERIOD_LABELS[period]}] 새 요약을 취소하시겠습니까?`)) {
        return;
    }

    try {
        const result = await api.discardPendingSummary(branchId, period);

        if (result.success) {
            const pendingSection = ui.getElement(`pending-section-${period}`);
            if (pendingSection) pendingSection.style.display = 'none';

            showToast(`🗑️ [${PERIOD_LABELS[period]}] 새 요약이 취소되었습니다`, 'success');
        }
    } catch (error) {
        console.error('Discard error:', error);
        showToast('❌ 취소 실패: ' + error.message, 'error');
    }
}

// ============================================================
// Status Update (상태 변경)
// ============================================================

/**
 * 요약 상태 변경
 * @param {number} branchId - 지점 ID
 * @param {string} status - 새 상태
 */
async function updateStatus(branchId, status) {
    try {
        const result = await api.updateStatus(branchId, status);

        if (result.success) {
            showToast(`✅ 상태가 ${STATUS_LABEL_MAP[status] || status}로 변경되었습니다.`, 'success');
            closeModal();
            await loadStats();
            await loadSummaries();
        }
    } catch (e) {
        console.error('Status update error:', e);
        showToast('❌ 상태 변경 실패: ' + e.message, 'error');
    }
}

// ============================================================
// Reviews (리뷰)
// ============================================================

/**
 * 리뷰 섹션 토글
 * @param {number} branchId - 지점 ID
 */
async function toggleReviews(branchId) {
    const section = ui.getElement('reviews-section');
    const btn = ui.getElement('btn-toggle-reviews');
    const visible = state.toggleReviewsVisibility();

    if (section) section.style.display = visible ? 'block' : 'none';
    if (btn) btn.textContent = visible ? '📋 리뷰 숨기기' : '📋 리뷰 보기';

    if (visible) {
        // 필터 초기화
        const carSelect = ui.getElement('filter-car-model');
        const sentSelect = ui.getElement('filter-sentiment');
        if (carSelect) carSelect.value = '';
        if (sentSelect) sentSelect.value = '';

        await loadReviews(branchId);
    }
}

/**
 * 리뷰 필터 적용
 * @param {number} branchId - 지점 ID
 */
function applyFilters(branchId) {
    state.setReviewsPage(0);
    loadReviews(branchId);
}

/**
 * 리뷰 로드
 * @param {number} branchId - 지점 ID
 */
async function loadReviews(branchId) {
    ui.showReviewsLoading();

    const { reviews: reviewsState } = state.getState();
    const offset = reviewsState.currentPage * reviewsState.pageSize;

    try {
        const result = await api.fetchBranchReviews(branchId, {
            limit: reviewsState.pageSize,
            offset,
            carModel: ui.getElement('filter-car-model')?.value || '',
            sentiment: ui.getElement('filter-sentiment')?.value || ''
        });

        // 디버깅 로그
        console.log('📋 리뷰 API 응답:', result);
        console.log('📋 첫 번째 리뷰 데이터:', result.reviews?.[0]);
        console.log('📋 review_id 필드:', result.reviews?.[0]?.review_id);

        state.setReviewsTotal(result.total || 0);

        // 차량 모델 드롭다운 (최초 1회)
        if (!reviewsState.carModelsLoaded && result.car_models?.length > 0) {
            ui.updateCarModelDropdown(result.car_models);
            state.markCarModelsLoaded();
        }

        ui.updateReviewsCount(result.total || 0);
        ui.renderReviewsList(result.reviews || [], offset);

        const totalPages = Math.ceil((result.total || 0) / reviewsState.pageSize);
        ui.updateReviewsPagination(reviewsState.currentPage, totalPages);

    } catch (e) {
        console.error('Reviews load error:', e);
        ui.getElement('reviews-list').innerHTML = '<div style="padding: 24px; text-align: center; color: var(--error);">로드 실패</div>';
    }
}

/**
 * 리뷰 페이지 이동
 * @param {number} branchId - 지점 ID
 * @param {'prev'|'next'} direction - 방향
 */
function loadMoreReviews(branchId, direction) {
    const { reviews: reviewsState } = state.getState();

    if (direction === 'prev' && reviewsState.currentPage > 0) {
        state.setReviewsPage(reviewsState.currentPage - 1);
    } else if (direction === 'next') {
        state.setReviewsPage(reviewsState.currentPage + 1);
    }

    loadReviews(branchId);
}

// ============================================================
// External Sync (외부 동기화)
// ============================================================

/**
 * Carmore 업체 동기화
 */
async function syncAffiliates() {
    if (!confirm('Carmore API에서 업체 정보를 동기화하시겠습니까?')) {
        return;
    }

    try {
        const result = await api.syncAffiliates();

        if (result.success) {
            showToast(`동기화 완료: ${result.success}개 업체`, 'success');
            loadSummaries();
        } else {
            showToast('동기화 실패: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (e) {
        showToast('동기화 실패: ' + e.message, 'error');
    }
}

// ============================================================
// Auto Initialize (자동 초기화)
// ============================================================

// DOM 로드 시 자동 초기화
if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}
