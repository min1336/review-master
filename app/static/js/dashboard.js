// ============================================================
// Constants (상수)
// ============================================================
const CONFIG = {
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
};

// ============================================================
// Validation (유효성 검증)
// ============================================================

/**
 * 리뷰 ID 유효성 검증 (빈 값만 체크)
 * @param {string|number|null|undefined} reviewId - 검증할 리뷰 ID
 * @returns {boolean} 유효 여부
 */
function isValidReviewId(reviewId) {
    if (reviewId === null || reviewId === undefined || reviewId === '') {
        return false;
    }
    return true;
}

// ============================================================
// Security (보안 유틸리티)
// ============================================================

/**
 * 외부 리뷰 링크 HTML 생성 (XSS/URL 인젝션 방지)
 * @param {string|number} reviewId - 리뷰 ID (예약번호)
 * @returns {string} 안전한 HTML 앵커 태그 또는 빈 문자열
 */
function createReviewLinkHtml(reviewId) {
    if (!isValidReviewId(reviewId)) {
        return '';
    }

    const encodedId = encodeURIComponent(String(reviewId));
    const escapedId = escapeHtml(String(reviewId));
    const reviewUrl = buildCarmoreReviewUrl(encodedId);

    return `<a href="${reviewUrl}" target="_blank" rel="noopener noreferrer" class="review-link" title="Carmore 관리자에서 리뷰 보기">#${escapedId}</a>`;
}

/**
 * Carmore 리뷰 관리 URL 생성
 * @param {string} reservationId - 예약번호 (URL 인코딩된 값)
 * @returns {string} 전체 URL
 */
function buildCarmoreReviewUrl(reservationId) {
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
// Render (렌더링)
// ============================================================

/**
 * 단일 리뷰 아이템 HTML 렌더링
 * @param {Object} reviewData - 리뷰 데이터 객체
 * @param {string} [reviewData.review_id] - 리뷰 ID
 * @param {string} [reviewData.content] - 리뷰 내용
 * @param {string} [reviewData.sentiment] - 감정 (positive/neutral/negative)
 * @param {string} [reviewData.review_date] - 리뷰 작성일
 * @param {number} [reviewData.rating_service] - 서비스 평점
 * @param {number} [reviewData.rating_car] - 차량 평점
 * @param {string} [reviewData.car_model] - 차량 모델
 * @param {number} index - 현재 인덱스
 * @param {number} pageOffset - 페이지 오프셋
 * @returns {string} 렌더링된 HTML 문자열
 */
function renderReviewItem(reviewData, index, pageOffset) {
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
 * 리뷰 푸터 (평점, 차량 정보) HTML 렌더링
 * @param {Object} reviewData - 리뷰 데이터 객체
 * @returns {string} 푸터 HTML 또는 빈 문자열
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

// ============================================================
// State (전역 상태)
// ============================================================
let currentPage = 0;
const pageSize = CONFIG.PAGINATION.DEFAULT_PAGE_SIZE;
let summaries = [];
let regionStats = [];

let currentSortField = 'review_count';
let currentSortOrder = 'desc'; // asc or desc

// 날짜 필터 상태 변수
let dateRangePicker = null;
let selectedDateFrom = null;
let selectedDateTo = null;

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadRegionStats();  // 지역 필터 드롭다운용
    loadSummaries();
    initDateRangePicker();  // 날짜 선택기 초기화

    // Event listeners - 필터 변경 시 페이지 리셋
    document.getElementById('search-input').addEventListener('input', debounce(() => { currentPage = 0; loadSummaries(); }, 300));
    document.getElementById('filter-region').addEventListener('change', () => { currentPage = 0; loadSummaries(); });
    document.getElementById('filter-status').addEventListener('change', () => { currentPage = 0; loadSummaries(); });
});

// Debounce helper
function debounce(fn, ms) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

/**
 * 날짜 선택기 초기화
 * - Flatpickr 범위 선택 모드 사용
 * - 한국어 로케일
 * - 최대 날짜: 오늘
 */
function initDateRangePicker() {
    dateRangePicker = flatpickr('#filter-date-range', {
        mode: 'range',
        locale: 'ko',
        dateFormat: 'Y-m-d',
        maxDate: 'today',
        onChange: function(selectedDates, dateStr) {
            if (selectedDates.length === 2) {
                selectedDateFrom = formatDateForAPI(selectedDates[0]);
                selectedDateTo = formatDateForAPI(selectedDates[1]);
                document.getElementById('btn-clear-date').style.display = 'inline-block';
                currentPage = 0;
                loadSummaries();
            }
        },
        onClose: function(selectedDates) {
            // 단일 날짜 선택 시 해당 날짜만 필터링
            if (selectedDates.length === 1) {
                selectedDateFrom = formatDateForAPI(selectedDates[0]);
                selectedDateTo = selectedDateFrom;
                document.getElementById('btn-clear-date').style.display = 'inline-block';
                currentPage = 0;
                loadSummaries();
            }
        }
    });
}

/**
 * Date 객체를 API 형식(YYYY-MM-DD)으로 변환
 */
function formatDateForAPI(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/**
 * 날짜 필터 초기화
 * - 선택된 날짜 제거
 * - 초기화 버튼 숨김
 * - 목록 새로고침
 */
function clearDateFilter() {
    if (dateRangePicker) {
        dateRangePicker.clear();
    }
    selectedDateFrom = null;
    selectedDateTo = null;
    document.getElementById('btn-clear-date').style.display = 'none';
    currentPage = 0;
    loadSummaries();
}

// Load Stats
async function loadStats() {
    console.log('loadStats 시작');
    try {
        const response = await fetch('/api/v2/stats');
        console.log('stats response:', response.status);
        const stats = await response.json();
        console.log('stats data:', stats);

        document.getElementById('stat-total').textContent = stats.total?.toLocaleString() || '0';
        document.getElementById('stat-reviews').textContent = stats.total_reviews?.toLocaleString() || '0';
        document.getElementById('stat-published').textContent = stats.published?.toLocaleString() || '0';

        // Status stats with progress bars
        const total = stats.total || 1;
        const draftPct = Math.round((stats.draft || 0) / total * 100);
        const approvedPct = Math.round((stats.approved || 0) / total * 100);
        const publishedPct = Math.round((stats.published || 0) / total * 100);

        document.getElementById('status-stats').innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 20px; padding: 8px 0;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <svg width="16" height="16" fill="none" stroke="#999" stroke-width="2" viewBox="0 0 24 24">
                                <circle cx="12" cy="12" r="10"></circle>
                                <polyline points="12 6 12 12 16 14"></polyline>
                            </svg>
                            <span style="font-weight: 500;">Draft</span>
                        </div>
                        <span class="badge badge-grey">${stats.draft || 0}</span>
                    </div>
                    <div style="background: #f0f0f0; height: 6px; border-radius: 3px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #999 0%, #666 100%); height: 100%; width: ${draftPct}%; transition: width 0.6s ease;"></div>
                    </div>
                </div>
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <svg width="16" height="16" fill="none" stroke="#f59e0b" stroke-width="2" viewBox="0 0 24 24">
                                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                                <polyline points="22 4 12 14.01 9 11.01"></polyline>
                            </svg>
                            <span style="font-weight: 500;">Approved</span>
                        </div>
                        <span class="badge badge-warning">${stats.approved || 0}</span>
                    </div>
                    <div style="background: #fef3c7; height: 6px; border-radius: 3px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #f59e0b 0%, #d97706 100%); height: 100%; width: ${approvedPct}%; transition: width 0.6s ease;"></div>
                    </div>
                </div>
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <svg width="16" height="16" fill="none" stroke="#10b981" stroke-width="2" viewBox="0 0 24 24">
                                <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                            <span style="font-weight: 500;">Published</span>
                        </div>
                        <span class="badge badge-success">${stats.published || 0}</span>
                    </div>
                    <div style="background: #d1fae5; height: 6px; border-radius: 3px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #10b981 0%, #059669 100%); height: 100%; width: ${publishedPct}%; transition: width 0.6s ease;"></div>
                    </div>
                </div>
            </div>
        `;
        console.log('loadStats 완료');
    } catch (e) {
        console.error('Stats load error:', e);
    }
}

// Load Region Stats (for filter dropdown only)
async function loadRegionStats() {
    try {
        const data = await fetch('/api/v2/stats/region').then(r => r.json());
        regionStats = data;

        // Update filter dropdown
        const select = document.getElementById('filter-region');
        data.forEach(r => {
            if (r.region && r.region !== '미분류') {
                const opt = document.createElement('option');
                opt.value = r.region;
                opt.textContent = `${r.region} (${r.count})`;
                select.appendChild(opt);
            }
        });

        // Calculate total reviews
        const totalReviews = data.reduce((sum, r) => sum + (r.total_reviews || 0), 0);
        document.getElementById('stat-reviews').textContent = totalReviews.toLocaleString();
    } catch (e) {
        console.error('Region stats error:', e);
    }
}

// Load Rating Stats
async function loadRatingStats() {
    try {
        const data = await fetch('/api/v2/stats/rating').then(r => r.json());
        const dist = data.distribution || {};
        const total = data.total || 1;

        const html = Object.entries(dist).map(([range, count]) => {
            const pct = (count / total * 100).toFixed(1);
            return `
                <div class="region-bar">
                    <span class="region-name">${range}</span>
                    <div class="region-bar-container">
                        <div class="region-bar-fill" style="width: ${pct}%; background: ${range.includes('4.5') ? '#10b981' : range.includes('4.0') ? '#3b82f6' : '#f59e0b'}"></div>
                    </div>
                    <span class="region-count">${count}개</span>
                </div>
            `;
        }).join('');

        document.getElementById('rating-chart').innerHTML = `
            <div style="margin-bottom: 16px; display: flex; gap: 20px; font-size: 14px;">
                <span>최저: <strong>${data.min?.toFixed(2) || '-'}</strong></span>
                <span>평균: <strong>${data.avg?.toFixed(2) || '-'}</strong></span>
                <span>최고: <strong>${data.max?.toFixed(2) || '-'}</strong></span>
            </div>
            ${html}
        `;
    } catch (e) {
        console.error('Rating stats error:', e);
    }
}

// Load Summaries
async function loadSummaries() {
    const keyword = document.getElementById('search-input').value;
    const region = document.getElementById('filter-region').value;
    const status = document.getElementById('filter-status').value;

    const params = new URLSearchParams({
        limit: pageSize,
        offset: currentPage * pageSize
    });

    if (keyword) params.set('keyword', keyword);
    if (region) params.set('region', region);
    if (status) params.set('status', status);

    // 날짜 범위 필터
    if (selectedDateFrom) params.set('review_date_from', selectedDateFrom);
    if (selectedDateTo) params.set('review_date_to', selectedDateTo);

    // 전체 지점 표시 (필터 없음)
    params.set('min_reviews', 0);

    // 정렬 파라미터 적용
    params.set('sort_by', currentSortField);
    params.set('order', currentSortOrder);
    updateSortUI();

    try {

        let data = await fetch(`/api/v2/summaries?${params}`).then(r => r.json());

        // 클라이언트 사이드 정렬 로직 제거됨 (서버 사이드 정렬 사용)

        // 지점별 top3 태그 로드
        const branchIdList = data.map(d => d.branch_id).filter(id => id);
        let tagsData = {};
        if (branchIdList.length > 0) {
            try {
                tagsData = await fetch('/api/tags/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ branch_ids: branchIdList })
                }).then(r => r.json());
            } catch (e) {
                console.error('Tags load error:', e);
            }
        }

        // 태그 데이터 병합 (keywords 우선, 없으면 branch_tags)
        data.forEach(row => {
            if (Array.isArray(row.keywords)) {
                // 수동 설정된 태그 사용
                row.top_tags = row.keywords.map(k => ({ name: k }));
            } else {
                // 자동 분류 태그 사용
                row.top_tags = tagsData[String(row.branch_id)] || [];
            }
        });

        summaries = data;
        renderTable(data);
    } catch (e) {
        console.error('Summaries load error:', e);
        document.getElementById('summaries-table').innerHTML = '<tr><td colspan="7" style="text-align:center;">로드 실패</td></tr>';
    }
}

// Sorting Handler
function handleSort(field) {
    if (currentSortField === field) {
        // Toggle order
        currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
        // New field
        currentSortField = field;
        currentSortOrder = 'desc'; // Default to desc for most things
        if (field === 'branch_name') currentSortOrder = 'asc'; // Exception for name
    }
    currentPage = 0;
    loadSummaries();
}

function updateSortUI() {
    // Reset all icons
    document.querySelectorAll('.sort-icon').forEach(el => el.textContent = '');

    // Set current icon
    const iconEl = document.getElementById(`sort-icon-${currentSortField}`);
    if (iconEl) {
        iconEl.textContent = currentSortOrder === 'asc' ? ' ↑' : ' ↓';
        iconEl.style.color = 'var(--primary)';
    }
}

// Helper: Get pastel color from string
function getKeywordColor(str) {
    if (!str) return '#e5e7eb'; // default grey
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    // Generate pastel color (high lightness and saturation)
    const h = Math.abs(hash) % 360;
    return `hsl(${h}, 70%, 85%)`;
}

// Helper: Get text color (darker version of pastel)
function getKeywordTextColor(str) {
    if (!str) return '#374151';
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const h = Math.abs(hash) % 360;
    return `hsl(${h}, 80%, 30%)`; // Darker for text
}

// Helper: Render stars
function getStarRating(rating) {
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

function renderTable(data) {
    if (!data.length) {
        document.getElementById('summaries-table').innerHTML = '<tr><td colspan="7" style="text-align:center; color: var(--grey-5);">데이터 없음</td></tr>';
        document.getElementById('pagination-info').textContent = '0개 지점';
        return;
    }

    const html = data.map(row => {
        // 요약 미리보기 (60자 제한)
        const summaryPreview = row.summary_all
            ? (row.summary_all.length > 60 ? row.summary_all.substring(0, 60) + '...' : row.summary_all)
            : '<span style="color: var(--grey-5); font-style: italic;">요약 없음</span>';

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
                    ${(() => {
                const tags = row.top_tags || [];
                if (!tags.length) {
                    return '<span style="color: var(--grey-5); font-style: italic;">-</span>';
                }
                return tags.map(t =>
                    `<span class="keyword" style="background: ${getKeywordColor(t.name)}; color: ${getKeywordTextColor(t.name)};">${t.name}</span>`
                ).join('');
            })()}
                </div>
            </td>
            <td style="text-align: center;">
                <span class="badge ${row.status === 'published' ? 'badge-success' : row.status === 'approved' ? 'badge-warning' : 'badge-grey'}">
                    ${row.status || 'draft'}
                </span>
            </td>
            <td style="text-align: center;">
                <button class="btn btn-secondary btn-sm" onclick="showDetail(${row.branch_id})">상세</button>
            </td>
        </tr>
    `;
    }).join('');

    document.getElementById('summaries-table').innerHTML = html;
    document.getElementById('pagination-info').textContent = `${currentPage * pageSize + 1}-${currentPage * pageSize + data.length}개 표시`;
}

// Pagination
function prevPage() {
    if (currentPage > 0) {
        currentPage--;
        loadSummaries();
    }
}

function nextPage() {
    if (summaries.length === pageSize) {
        currentPage++;
        loadSummaries();
    }
}

// Status mappings
const statusClassMap = {
    'draft': 'grey',
    'approved': 'warning',
    'published': 'success'
};
const statusLabelMap = {
    'draft': '보류',
    'approved': '승인',
    'published': '게시'
};

// Show Detail Modal
async function showDetail(branchId) {
    document.getElementById('detail-modal').classList.add('active');
    document.getElementById('modal-body').innerHTML = '<div class="loading"><div class="spinner"></div>로딩 중...</div>';

    try {
        const data = await fetch(`/api/v2/summaries/${branchId}`).then(r => r.json());

        document.getElementById('modal-title').textContent = `${data.branch_name || '지점 ' + branchId}`;

        const html = `
            <div class="modal-header-content" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px;">
                <div style="flex: 1;">
                    <div style="font-size: 14px; color: var(--grey-5); margin-bottom: 4px;">ID: ${data.branch_id}</div>
                    <h2 style="font-size: 24px; font-weight: 700; color: var(--grey-1); margin: 0;">${data.branch_name}</h2>
                    <!-- 지역 표시/수정 -->
                    <div id="region-display" style="font-size: 14px; color: var(--grey-3); margin-top: 4px;">${data.region || '지역 정보 없음'}</div>
                    <input type="text" id="region-input" value="${data.region || ''}" placeholder="지역 입력 (예: 서울 강남구)"
                        style="display: none; margin-top: 8px; padding: 8px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 14px; width: 100%; max-width: 300px;">
                </div>
                <div>
                    <span class="badge badge-${statusClassMap[data.status] || 'grey'}" style="font-size: 14px; padding: 6px 12px;">
                        ${statusLabelMap[data.status] || data.status}
                    </span>
                </div>
            </div>

            <!-- Tags -->
            <div style="margin-bottom: 24px;">
                <div style="font-size: 14px; font-weight: 600; color: var(--grey-3); margin-bottom: 8px;">태그</div>
                <div class="keywords" id="tags-display" style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <span class="summary-empty">로딩 중...</span>
                </div>
                <!-- 태그 수정 영역 -->
                <div id="edit-area-tags" style="display: none; margin-top: 12px;">
                    <div style="font-size: 12px; color: var(--grey-5); margin-bottom: 8px;">클릭하여 선택/해제 (선택 안해도 됨):</div>
                    <div id="tag-selector" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;"></div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <input type="text" id="custom-tag-input" placeholder="커스텀 태그 입력"
                            style="padding: 6px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 13px; width: 150px;">
                        <button class="btn btn-secondary btn-sm" onclick="addCustomTag()">+ 추가</button>
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

            <!-- Summary Tabs with AI Button -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <div class="tabs" style="display: flex; gap: 8px;">
                    <div class="tab active" onclick="showSummaryTab(this, 'all')" style="padding: 8px 16px; cursor: pointer; font-weight: 500; font-size: 13px; border-radius: 20px; background: var(--grey-2); color: white; transition: all 0.2s;">전체</div>
                    <div class="tab" onclick="showSummaryTab(this, '1y')" style="padding: 8px 16px; cursor: pointer; font-weight: 500; font-size: 13px; border-radius: 20px; background: var(--grey-8); color: var(--grey-3); transition: all 0.2s;">1년</div>
                    <div class="tab" onclick="showSummaryTab(this, '6m')" style="padding: 8px 16px; cursor: pointer; font-weight: 500; font-size: 13px; border-radius: 20px; background: var(--grey-8); color: var(--grey-3); transition: all 0.2s;">6개월</div>
                    <div class="tab" onclick="showSummaryTab(this, '3m')" style="padding: 8px 16px; cursor: pointer; font-weight: 500; font-size: 13px; border-radius: 20px; background: var(--grey-8); color: var(--grey-3); transition: all 0.2s;">3개월</div>
                    <div class="tab" onclick="showSummaryTab(this, '1m')" style="padding: 8px 16px; cursor: pointer; font-weight: 500; font-size: 13px; border-radius: 20px; background: var(--grey-8); color: var(--grey-3); transition: all 0.2s;">1개월</div>
                </div>
                <button class="btn-ai-summary" onclick="regenerateSummary(${data.branch_id})" title="현재 선택된 기간의 요약을 AI로 재생성합니다">
                    ✨ AI 요약
                </button>
            </div>

            <!-- Summary Content -->
            <div id="summary-content" style="min-height: 200px; background: white; border-radius: 0 0 var(--radius) var(--radius);">
                ${['all', '1y', '6m', '3m', '1m'].map(period => {
                    const pendingSummaries = data.pending_summaries || {};
                    const hasPending = !!pendingSummaries[period];
                    return `
                    <div class="summary-panel" id="panel-${period}" style="display: ${period === 'all' ? 'block' : 'none'};">
                        <!-- 현재 요약 -->
                        <div class="summary-text" id="summary-text-${period}" style="font-size: 15px; line-height: 1.7; color: var(--grey-2); white-space: pre-wrap;">${data['summary_' + period] || '<span class="summary-empty" style="color: var(--grey-5); font-style: italic;">작성된 요약이 없습니다.</span>'}</div>
                        <textarea id="edit-summary-${period}" style="display: none; width: 100%; min-height: 120px; padding: 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 14px; line-height: 1.6; resize: vertical; font-family: inherit;">${data['summary_' + period] || ''}</textarea>

                        <!-- 신규 생성 요약 (pending) -->
                        <div id="pending-section-${period}" class="pending-summary-section" style="display: ${hasPending ? 'block' : 'none'}; margin-top: 16px; padding: 16px; background: var(--primary-light); border: 2px dashed var(--primary); border-radius: var(--radius-sm);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <span style="font-size: 13px; font-weight: 600; color: var(--primary);">✨ 신규 생성 요약</span>
                                <div style="display: flex; gap: 8px;">
                                    <button class="btn btn-primary btn-sm" onclick="applyPendingSummary(${data.branch_id}, '${period}')" style="font-size: 12px; padding: 4px 12px;">변경</button>
                                    <button class="btn btn-secondary btn-sm" onclick="discardPendingSummary(${data.branch_id}, '${period}')" style="font-size: 12px; padding: 4px 12px;">취소</button>
                                </div>
                            </div>
                            <div id="pending-text-${period}" style="font-size: 14px; line-height: 1.6; color: var(--grey-2); white-space: pre-wrap;">${pendingSummaries[period] || ''}</div>
                        </div>
                    </div>
                `}).join('')}
            </div>

            <!-- 하단 버튼 영역 -->
            <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--grey-8);">
                <!-- 보기 모드: 수정/리뷰 버튼 + 상태 버튼 -->
                <div id="view-mode-buttons" style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-secondary" onclick="enterEditMode()">✏️ 수정</button>
                        <button class="btn btn-secondary" onclick="toggleReviews(${data.branch_id})" id="btn-toggle-reviews">📋 리뷰 보기</button>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-secondary btn-sm" onclick="updateStatus(${data.branch_id}, 'draft')">보류</button>
                        <button class="btn btn-secondary btn-sm" onclick="updateStatus(${data.branch_id}, 'approved')">승인</button>
                        <button class="btn btn-primary btn-sm" onclick="updateStatus(${data.branch_id}, 'published')">게시</button>
                    </div>
                </div>
                <!-- 수정 모드: 저장/취소 버튼 -->
                <div id="edit-mode-buttons" style="display: none; justify-content: flex-end; gap: 12px;">
                    <button class="btn btn-secondary" onclick="cancelEditMode()">취소</button>
                    <button class="btn btn-primary" onclick="saveAllChanges(${data.branch_id})">💾 저장</button>
                </div>
            </div>

            <!-- 리뷰 목록 (버튼 클릭 시 확장) -->
            <div id="reviews-section" style="display: none; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--grey-8);">
                <div style="font-size: 14px; font-weight: 600; color: var(--grey-3); margin-bottom: 12px;">
                    📋 리뷰 목록 <span id="reviews-count" style="font-weight: normal; color: var(--grey-5);"></span>
                </div>
                <!-- 필터 영역 -->
                <div id="reviews-filters" style="display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;">
                    <select id="filter-car-model" onchange="applyFilters(${data.branch_id})" style="padding: 6px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 13px; background: white;">
                        <option value="">🚗 전체 차량</option>
                    </select>
                    <select id="filter-sentiment" onchange="applyFilters(${data.branch_id})" style="padding: 6px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 13px; background: white;">
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
                    <button class="btn btn-secondary btn-sm" onclick="loadMoreReviews(${data.branch_id}, 'prev')" id="reviews-prev-btn" disabled>이전</button>
                    <span id="reviews-page-info" style="font-size: 13px; color: var(--grey-5); line-height: 32px;">-</span>
                    <button class="btn btn-secondary btn-sm" onclick="loadMoreReviews(${data.branch_id}, 'next')" id="reviews-next-btn">다음</button>
                </div>
            </div>
`;

        document.getElementById('modal-body').innerHTML = html;

        // 태그 로드 (data 객체 전달, branch_tags fallback 포함)
        loadBranchTags(data, branchId);
    } catch (e) {
        document.getElementById('modal-body').innerHTML = '<div style="color: var(--error);">로드 실패</div>';
    }
}

// 전역 변수
let currentSelectedTags = [];
let originalTags = [];
let isEditMode = false;
let currentSummaryPeriod = 'all';  // 현재 선택된 요약 기간
const DEFAULT_TAGS = ['고객응대', '차량상태', '가성비', '반납/픽업', '위치/접근성', '서비스', '보험/보장'];

// 지점 태그 로드
// - 기본: branch_tags (자동 분류)
// - 수정됨: keywords 배열 (수동 선택)
async function loadBranchTags(data, branchId) {
    // 1. keywords가 명시적으로 설정된 경우 (수동 태그)
    if (Array.isArray(data.keywords)) {
        currentSelectedTags = [...data.keywords];
    }
    // 2. 기본: branch_tags에서 자동 분류 태그 로드
    else {
        try {
            const tagsData = await fetch('/api/tags/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ branch_ids: [branchId] })
            }).then(r => r.json());
            const tags = tagsData[String(branchId)] || [];
            currentSelectedTags = tags.map(t => t.name);
        } catch (e) {
            currentSelectedTags = [];
        }
    }

    originalTags = [...currentSelectedTags];
    updateTagsDisplay();
}

// 태그 표시 업데이트
function updateTagsDisplay() {
    const display = document.getElementById('tags-display');
    if (currentSelectedTags.length > 0) {
        display.innerHTML = currentSelectedTags.map(t =>
            `<span class="keyword" style="background: ${getKeywordColor(t)}; color: ${getKeywordTextColor(t)};">${t}</span>`
        ).join('');
    } else {
        display.innerHTML = '<span class="summary-empty">태그 없음</span>';
    }
}

// 수정 모드 진입
function enterEditMode() {
    isEditMode = true;
    originalTags = [...currentSelectedTags];

    // 버튼 전환
    document.getElementById('view-mode-buttons').style.display = 'none';
    document.getElementById('edit-mode-buttons').style.display = 'flex';

    // 지역 수정 활성화
    document.getElementById('region-display').style.display = 'none';
    document.getElementById('region-input').style.display = 'block';

    // 태그 수정 활성화
    document.getElementById('tags-display').style.display = 'none';
    document.getElementById('edit-area-tags').style.display = 'block';
    renderTagSelector();

    // 요약 수정 활성화 (현재 보이는 패널만)
    ['all', '1y', '6m', '3m', '1m'].forEach(period => {
        const textEl = document.getElementById('summary-text-' + period);
        const editEl = document.getElementById('edit-summary-' + period);
        if (textEl) textEl.style.display = 'none';
        if (editEl) editEl.style.display = 'block';
    });
}

// 수정 모드 취소 (원래 값으로 복원)
function cancelEditMode() {
    isEditMode = false;
    currentSelectedTags = [...originalTags];
    exitEditModeUI();
}

// 수정 모드 UI만 종료 (값 유지)
function exitEditModeUI() {
    isEditMode = false;

    // 버튼 전환
    document.getElementById('view-mode-buttons').style.display = 'flex';
    document.getElementById('edit-mode-buttons').style.display = 'none';

    // 지역 표시 복원
    document.getElementById('region-display').style.display = 'block';
    document.getElementById('region-input').style.display = 'none';

    // 태그 표시 복원
    document.getElementById('tags-display').style.display = 'flex';
    document.getElementById('edit-area-tags').style.display = 'none';
    updateTagsDisplay();

    // 요약 표시 복원
    ['all', '1y', '6m', '3m', '1m'].forEach(period => {
        const textEl = document.getElementById('summary-text-' + period);
        const editEl = document.getElementById('edit-summary-' + period);
        if (textEl) textEl.style.display = 'block';
        if (editEl) editEl.style.display = 'none';
    });
}

// 태그 선택기 렌더링 (기본 태그 + 커스텀 태그)
function renderTagSelector() {
    const selector = document.getElementById('tag-selector');

    // 모든 태그 (기본 + 커스텀)
    const allTags = [...new Set([...DEFAULT_TAGS, ...currentSelectedTags])];

    selector.innerHTML = allTags.map(tag => {
        const isSelected = currentSelectedTags.includes(tag);
        const isCustom = !DEFAULT_TAGS.includes(tag);
        const bg = isSelected ? getKeywordColor(tag) : 'var(--grey-8)';
        const color = isSelected ? getKeywordTextColor(tag) : 'var(--grey-3)';
        const border = isSelected ? '2px solid var(--primary)' : '2px solid transparent';
        const deleteBtn = isCustom ? `<span onclick="event.stopPropagation(); removeCustomTag('${tag}')" style="margin-left: 4px; font-size: 10px;">✕</span>` : '';
        return `<span class="keyword" onclick="toggleTag('${tag}')"
            style="background: ${bg}; color: ${color}; border: ${border}; cursor: pointer; user-select: none;"
            data-tag="${tag}">${tag}${deleteBtn}</span>`;
    }).join('');
}

// 태그 토글 (선택/해제)
function toggleTag(tagName) {
    const idx = currentSelectedTags.indexOf(tagName);
    if (idx > -1) {
        currentSelectedTags.splice(idx, 1);
    } else {
        currentSelectedTags.push(tagName);
    }
    renderTagSelector();
}

// 커스텀 태그 추가
function addCustomTag() {
    const input = document.getElementById('custom-tag-input');
    const tagName = input.value.trim();
    if (!tagName) return;
    if (currentSelectedTags.includes(tagName)) {
        alert('이미 존재하는 태그입니다.');
        return;
    }
    currentSelectedTags.push(tagName);
    input.value = '';
    renderTagSelector();
}

// 커스텀 태그 삭제
function removeCustomTag(tagName) {
    const idx = currentSelectedTags.indexOf(tagName);
    if (idx > -1) {
        currentSelectedTags.splice(idx, 1);
    }
    renderTagSelector();
}

// 모든 변경사항 저장
async function saveAllChanges(branchId) {
    const region = document.getElementById('region-input').value.trim();
    const summaries_data = {};
    ['all', '1y', '6m', '3m', '1m'].forEach(period => {
        const el = document.getElementById('edit-summary-' + period);
        if (el) summaries_data['summary_' + period] = el.value;
    });

    try {
        const response = await fetch(`/api/v2/summaries/${branchId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                region: region,
                keywords: currentSelectedTags,
                ...summaries_data
            })
        });

        if (response.ok) {
            // 모달 UI 업데이트
            document.getElementById('region-display').textContent = region || '지역 정보 없음';
            updateTagsDisplay();
            ['all', '1y', '6m', '3m', '1m'].forEach(period => {
                const textEl = document.getElementById('summary-text-' + period);
                const editEl = document.getElementById('edit-summary-' + period);
                if (textEl && editEl) {
                    textEl.innerHTML = editEl.value || '<span class="summary-empty" style="color: var(--grey-5); font-style: italic;">작성된 요약이 없습니다.</span>';
                }
            });

            // 대시보드 테이블 즉시 업데이트 (타입 변환 포함)
            const rowIdx = summaries.findIndex(r => Number(r.branch_id) === Number(branchId));
            if (rowIdx > -1) {
                summaries[rowIdx].region = region;
                summaries[rowIdx].top_tags = currentSelectedTags.map(t => ({ name: t }));
                summaries[rowIdx].summary_all = summaries_data.summary_all;
                renderTable(summaries);
            }

            // 저장된 태그를 원본으로 설정
            originalTags = [...currentSelectedTags];

            // 수정 모드 UI 종료 (값 유지)
            exitEditModeUI();

            alert('✅ 저장되었습니다.');
        } else {
            alert('저장 실패');
        }
    } catch (e) {
        console.error('Save error:', e);
        alert('저장 중 오류 발생');
    }
}

function showSummaryTab(el, period) {
    // 현재 선택된 기간 업데이트
    currentSummaryPeriod = period;

    // 모든 탭 비활성화 스타일
    document.querySelectorAll('.tabs .tab').forEach(t => {
        t.classList.remove('active');
        t.style.background = 'var(--grey-8)';
        t.style.color = 'var(--grey-3)';
    });

    // 선택된 탭 활성화 스타일
    el.classList.add('active');
    el.style.background = 'var(--grey-2)';
    el.style.color = 'white';

    // 패널 전환
    document.querySelectorAll('.summary-panel').forEach(p => p.style.display = 'none');
    const panel = document.getElementById('panel-' + period);
    if (panel) panel.style.display = 'block';
}

// AI 요약 재생성
async function regenerateSummary(branchId) {
    const btn = event.target;
    const originalText = btn.innerHTML;
    const periodLabels = {
        'all': '전체',
        '1y': '1년',
        '6m': '6개월',
        '3m': '3개월',
        '1m': '1개월'
    };

    // 확인 대화상자
    if (!confirm(`[${periodLabels[currentSummaryPeriod]}] 기간의 요약을 AI로 재생성하시겠습니까?\n\n새 요약이 생성되며, "변경" 버튼을 눌러야 적용됩니다.`)) {
        return;
    }

    try {
        // 로딩 상태
        btn.innerHTML = '⏳ 생성 중...';
        btn.disabled = true;
        btn.style.opacity = '0.7';

        const response = await fetch(`/api/v2/summaries/${branchId}/regenerate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ period: currentSummaryPeriod })
        });

        const result = await response.json();

        if (result.success) {
            // pending 섹션에 새 요약 표시
            const pendingSection = document.getElementById(`pending-section-${currentSummaryPeriod}`);
            const pendingText = document.getElementById(`pending-text-${currentSummaryPeriod}`);

            if (pendingSection && pendingText) {
                pendingText.innerHTML = result.summary;
                pendingSection.style.display = 'block';
            }

            showToast(`✨ [${periodLabels[currentSummaryPeriod]}] 새 요약이 생성되었습니다. "변경" 버튼으로 적용하세요.`, 'success');
        } else {
            throw new Error(result.error || '요약 생성 실패');
        }
    } catch (error) {
        console.error('Regenerate error:', error);
        showToast('❌ 요약 생성 실패: ' + error.message, 'error');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';
    }
}

// 대기 중인 요약 적용
async function applyPendingSummary(branchId, period) {
    const periodLabels = { 'all': '전체', '1y': '1년', '6m': '6개월', '3m': '3개월', '1m': '1개월' };

    if (!confirm(`[${periodLabels[period]}] 새 요약을 적용하시겠습니까?\n\n기존 요약이 새 요약으로 대체됩니다.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/v2/summaries/${branchId}/apply-pending`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ period })
        });

        const result = await response.json();

        if (result.success) {
            // 메인 요약 업데이트
            const textEl = document.getElementById(`summary-text-${period}`);
            const editEl = document.getElementById(`edit-summary-${period}`);
            const pendingSection = document.getElementById(`pending-section-${period}`);

            if (textEl) textEl.innerHTML = result.applied;
            if (editEl) editEl.value = result.applied;
            if (pendingSection) pendingSection.style.display = 'none';

            showToast(`✅ [${periodLabels[period]}] 요약이 적용되었습니다`, 'success');
        } else {
            throw new Error(result.error || '적용 실패');
        }
    } catch (error) {
        console.error('Apply error:', error);
        showToast('❌ 적용 실패: ' + error.message, 'error');
    }
}

// 대기 중인 요약 취소
async function discardPendingSummary(branchId, period) {
    const periodLabels = { 'all': '전체', '1y': '1년', '6m': '6개월', '3m': '3개월', '1m': '1개월' };

    if (!confirm(`[${periodLabels[period]}] 새 요약을 취소하시겠습니까?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/v2/summaries/${branchId}/discard-pending`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ period })
        });

        const result = await response.json();

        if (result.success) {
            const pendingSection = document.getElementById(`pending-section-${period}`);
            if (pendingSection) pendingSection.style.display = 'none';

            showToast(`🗑️ [${periodLabels[period]}] 새 요약이 취소되었습니다`, 'success');
        } else {
            throw new Error(result.error || '취소 실패');
        }
    } catch (error) {
        console.error('Discard error:', error);
        showToast('❌ 취소 실패: ' + error.message, 'error');
    }
}

function closeModal() {
    document.getElementById('detail-modal').classList.remove('active');
}

// 기간별 수정 모드 토글
function togglePeriodEdit(period) {
    const textEl = document.getElementById('summary-text-' + period);
    const editArea = document.getElementById('edit-area-' + period);
    const editBtn = document.getElementById('edit-btn-' + period);

    if (editArea.style.display === 'none') {
        textEl.style.display = 'none';
        editArea.style.display = 'block';
        editBtn.textContent = '📖 보기';
    } else {
        cancelPeriodEdit(period);
    }
}

// 기간별 수정 취소
function cancelPeriodEdit(period) {
    const textEl = document.getElementById('summary-text-' + period);
    const editArea = document.getElementById('edit-area-' + period);
    const editBtn = document.getElementById('edit-btn-' + period);

    textEl.style.display = 'block';
    editArea.style.display = 'none';
    editBtn.textContent = '✏️ 수정';
}

// 기간별 요약 저장
async function savePeriodSummary(branchId, period) {
    const textarea = document.getElementById('edit-summary-' + period);
    const editedSummary = textarea.value;

    // 필드명 매핑
    const fieldMap = {
        'all': 'summary_all',
        '1y': 'summary_1y',
        '6m': 'summary_6m',
        '3m': 'summary_3m',
        '1m': 'summary_1m'
    };

    const fieldName = fieldMap[period];
    if (!fieldName) {
        alert('잘못된 기간입니다.');
        return;
    }

    try {
        const response = await fetch(`/api/v2/summaries/${branchId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [fieldName]: editedSummary })
        });

        if (!response.ok) throw new Error('저장 실패');

        alert('✅ 요약이 저장되었습니다.');

        // UI 업데이트
        const textEl = document.getElementById('summary-text-' + period);
        textEl.innerHTML = editedSummary || '<span class="summary-empty">요약 없음</span>';
        cancelPeriodEdit(period);
        loadSummaries();
    } catch (e) {
        alert('❌ 저장 실패: ' + e.message);
    }
}

// Keyword Edit Functions
function toggleKeywordEdit() {
    const display = document.getElementById('keywords-display');
    const editArea = document.getElementById('edit-area-keywords');
    const editBtn = document.getElementById('edit-btn-keywords');

    if (editArea.style.display === 'none') {
        display.style.display = 'none';
        editArea.style.display = 'block';
        editBtn.style.display = 'none';
    } else {
        cancelKeywordEdit();
    }
}

function cancelKeywordEdit() {
    const display = document.getElementById('keywords-display');
    const editArea = document.getElementById('edit-area-keywords');
    const editBtn = document.getElementById('edit-btn-keywords');

    display.style.display = 'flex';
    editArea.style.display = 'none';
    editBtn.style.display = 'inline-flex';
}

async function saveKeywords(branchId) {
    const input = document.getElementById('edit-keywords-input').value.trim();

    // Parse keywords from # tags
    const keywords = input
        .split('#')
        .map(k => k.trim())
        .filter(k => k.length > 0);  // 개수 제한 제거

    const data = {
        keywords: keywords,  // JSON 배열로 저장
        // 하위 호환성을 위해 keyword_1,2,3도 저장
        keyword_1: keywords[0] || null,
        keyword_2: keywords[1] || null,
        keyword_3: keywords[2] || null
    };

    try {
        const response = await fetch(`/api/v2/summaries/${branchId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) throw new Error('저장 실패');

        alert(`✅ 키워드 ${keywords.length}개가 저장되었습니다.`);

        // UI 업데이트
        const displayEl = document.getElementById('keywords-display');
        let html = '';
        if (keywords.length > 0) {
            html = keywords.map(k => `<span class="keyword">${k}</span>`).join('');
        } else {
            html = '<span class="summary-empty">키워드 없음</span>';
        }
        displayEl.innerHTML = html;

        cancelKeywordEdit();
        loadSummaries();
    } catch (e) {
        alert('❌ 저장 실패: ' + e.message);
    }
}

// Update Status
async function updateStatus(branchId, status) {
    try {
        const response = await fetch(`/api/v2/summaries/${branchId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || '상태 변경 실패');
        }

        const result = await response.json();
        if (result.success) {
            alert(`✅ 상태가 ${status}로 변경되었습니다.`);
            closeModal();
            await loadStats();
            await loadSummaries();
        } else {
            throw new Error('상태 변경 실패');
        }
    } catch (e) {
        console.error('Status update error:', e);
        alert('❌ 상태 변경 실패: ' + e.message);
    }
}

// Sync Affiliates
async function syncAffiliates() {
    if (!confirm('Carmore API에서 업체 정보를 동기화하시겠습니까?')) return;

    try {
        const res = await fetch('/api/carmore/sync/affiliates', { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            alert(`동기화 완료: ${data.success}개 업체`);
            loadSummaries();
        } else {
            alert('동기화 실패: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('동기화 실패: ' + e.message);
    }
}

// Click outside modal to close
document.getElementById('detail-modal').addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) closeModal();
});

// ============================================================
// 리뷰 목록 기능
// ============================================================
let reviewsCurrentPage = 0;
const reviewsPageSize = 20;
let reviewsTotal = 0;
let reviewsVisible = false;
let reviewsCarModelsLoaded = false;

// 리뷰 섹션 토글
async function toggleReviews(branchId) {
    const section = document.getElementById('reviews-section');
    const btn = document.getElementById('btn-toggle-reviews');

    if (reviewsVisible) {
        section.style.display = 'none';
        btn.textContent = '📋 리뷰 보기';
        reviewsVisible = false;
    } else {
        section.style.display = 'block';
        btn.textContent = '📋 리뷰 숨기기';
        reviewsVisible = true;
        reviewsCurrentPage = 0;
        reviewsCarModelsLoaded = false;
        // 필터 초기화
        const carSelect = document.getElementById('filter-car-model');
        const sentSelect = document.getElementById('filter-sentiment');
        if (carSelect) carSelect.value = '';
        if (sentSelect) sentSelect.value = '';
        await loadReviews(branchId);
    }
}

// 필터 적용
function applyFilters(branchId) {
    reviewsCurrentPage = 0;
    loadReviews(branchId);
}

// 감정 아이콘 반환
function getSentimentIcon(sentiment) {
    switch (sentiment) {
        case 'positive': return '😊';
        case 'negative': return '😞';
        case 'neutral': return '😐';
        default: return '';
    }
}

// 리뷰 로드
async function loadReviews(branchId) {
    const listEl = document.getElementById('reviews-list');
    listEl.innerHTML = '<div class="loading"><div class="spinner"></div>로딩 중...</div>';

    try {
        const offset = reviewsCurrentPage * reviewsPageSize;
        const carModel = document.getElementById('filter-car-model')?.value || '';
        const sentiment = document.getElementById('filter-sentiment')?.value || '';

        let url = `/api/v2/summaries/${branchId}/reviews?limit=${reviewsPageSize}&offset=${offset}`;
        if (carModel) url += `&car_model=${encodeURIComponent(carModel)}`;
        if (sentiment) url += `&sentiment=${encodeURIComponent(sentiment)}`;

        // 메인 화면의 날짜 필터 적용
        if (selectedDateFrom) url += `&review_date_from=${selectedDateFrom}`;
        if (selectedDateTo) url += `&review_date_to=${selectedDateTo}`;

        const response = await fetch(url);
        const data = await response.json();

        // 디버깅: API 응답 확인
        console.log('📋 리뷰 API 응답:', data);
        console.log('📋 첫 번째 리뷰 데이터:', data.reviews?.[0]);
        console.log('📋 review_id 필드:', data.reviews?.[0]?.review_id);

        reviewsTotal = data.total || 0;
        const reviews = data.reviews || [];
        const carModels = data.car_models || [];

        // 차량 모델 드롭다운 채우기 (최초 1회)
        if (!reviewsCarModelsLoaded && carModels.length > 0) {
            const carSelect = document.getElementById('filter-car-model');
            if (carSelect) {
                carSelect.innerHTML = '<option value="">🚗 전체 차량</option>' +
                    carModels.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
            }
            reviewsCarModelsLoaded = true;
        }

        document.getElementById('reviews-count').textContent = `(총 ${reviewsTotal.toLocaleString()}건)`;

        if (reviews.length === 0) {
            listEl.innerHTML = '<div class="review-item" style="text-align: center;">리뷰가 없습니다.</div>';
        } else {
            listEl.innerHTML = reviews.map((r, idx) => renderReviewItem(r, idx, offset)).join('');
        }

        // 페이징 UI 업데이트
        const totalPages = Math.ceil(reviewsTotal / reviewsPageSize);
        document.getElementById('reviews-page-info').textContent = `${reviewsCurrentPage + 1} / ${totalPages || 1}`;
        document.getElementById('reviews-prev-btn').disabled = reviewsCurrentPage === 0;
        document.getElementById('reviews-next-btn').disabled = (reviewsCurrentPage + 1) >= totalPages;

    } catch (e) {
        console.error('Reviews load error:', e);
        listEl.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--error);">로드 실패</div>';
    }
}

// 리뷰 페이징
function loadMoreReviews(branchId, direction) {
    if (direction === 'prev' && reviewsCurrentPage > 0) {
        reviewsCurrentPage--;
    } else if (direction === 'next') {
        reviewsCurrentPage++;
    }
    loadReviews(branchId);
}

// 날짜 포맷
function formatDate(dateStr) {
    if (!dateStr) return '-';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' });
    } catch {
        return dateStr;
    }
}

// HTML 이스케이프
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Toast 알림 (showToast 함수가 없어서 추가)
function showToast(message, type = 'info') {
    // 기존 토스트 제거
    const existingToast = document.querySelector('.toast-notification');
    if (existingToast) existingToast.remove();

    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        padding: 16px 24px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
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

    // 3초 후 제거
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Toast 애니메이션 스타일 추가
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
