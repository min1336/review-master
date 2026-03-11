        (function () {
            'use strict';

            // ============================================================
            // CONFIG (config.js)
            // ============================================================

            // window.__DASHBOARD_CONFIG__는 HTML 인라인 스크립트에서 Jinja2로 주입됨
            const API_PREFIX = window.__DASHBOARD_CONFIG__.API_PREFIX;
            const BASE_PATH = API_PREFIX.replace('/api', '');

            const CARMORE_ADMIN_URL = window.__DASHBOARD_CONFIG__.CARMORE_ADMIN_URL;
            const CONFIG = Object.freeze({
                API_PREFIX: API_PREFIX,
                EXTERNAL_URLS: {
                    CARMORE_REVIEW_BASE: CARMORE_ADMIN_URL + '/partners/Reviewmanage'
                },
                PAGINATION: {
                    DEFAULT_PAGE_SIZE: 30,
                    REVIEWS_PAGE_SIZE: 10
                },
                VALIDATION: {
                    REVIEW_ID_PATTERN: /^[a-zA-Z0-9_-]+$/
                },
                POLLING: {
                    INTERVAL_MS: 2000,
                    MAX_POLLS: 60
                }
            });

            const REPORT_REVIEW_THRESHOLD = 30;

            const DEFAULT_TAGS = Object.freeze([
                '직원친절',
                '사고 처리',
                '주유비',
                '가격',
                '청결',
                '외관',
                '배달'
            ]);

            const PERIOD_LABELS = Object.freeze({
                'all': '전체',
                '1y': '1년',
                '6m': '6개월',
                '3m': '3개월',
                '1m': '1개월'
            });

            const PERIOD_PRIORITY = Object.freeze(['1m', '3m', '6m', '1y', 'all']);
            const PERIOD_ALL_DESC = Object.freeze(['all', '1y', '6m', '3m', '1m']);

            // ============================================================
            // UTILS (utils.js)
            // ============================================================

            function isValidReviewId(reviewId) {
                return reviewId !== null && reviewId !== undefined && reviewId !== '';
            }

            // formatDateForAPI, formatDate, escapeHtml → shared-utils.js

            function buildCarmoreReviewUrl(reservationId) {
                const today = new Date();
                const oneMonthAgo = new Date(today);
                oneMonthAgo.setMonth(oneMonthAgo.getMonth() - 1);

                const endDate = formatDateForAPI(today);
                const startDate = formatDateForAPI(oneMonthAgo);

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

            function getKeywordColor(str) {
                if (!str) return '#e5e7eb';
                let hash = 0;
                for (let i = 0; i < str.length; i++) {
                    hash = str.charCodeAt(i) + ((hash << 5) - hash);
                }
                const h = Math.abs(hash) % 360;
                return `hsl(${h}, 70%, 85%)`;
            }

            function getKeywordTextColor(str) {
                if (!str) return '#374151';
                let hash = 0;
                for (let i = 0; i < str.length; i++) {
                    hash = str.charCodeAt(i) + ((hash << 5) - hash);
                }
                const h = Math.abs(hash) % 360;
                return `hsl(${h}, 80%, 30%)`;
            }

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

            function getSentimentIcon(sentiment) {
                switch (sentiment) {
                    case 'positive': return '😊';
                    case 'negative': return '😞';
                    case 'neutral': return '😐';
                    default: return '';
                }
            }

            // debounce, showToast → shared-utils.js

            // ============================================================
            // STATE (state.js)
            // ============================================================

            const state = {
                pagination: {
                    currentPage: 0,
                    pageSize: CONFIG.PAGINATION.DEFAULT_PAGE_SIZE
                },
                sort: {
                    field: 'review_count',
                    order: 'desc'
                },
                dateFilter: {
                    picker: null,
                    from: null,
                    to: null
                },
                selectedBranches: new Set(),
                editMode: {
                    isActive: false,
                    selectedTags: [],
                    originalTags: [],
                    currentPeriod: 'all'
                },
                reviews: {
                    currentPage: 0,
                    pageSize: CONFIG.PAGINATION.REVIEWS_PAGE_SIZE,
                    total: 0,
                    visible: false,
                    carModelsLoaded: false,
                },
                carList: {
                    visible: false,
                    loaded: false,
                    models: []
                },
                summaries: [],
                regionStats: [],
                favorites: JSON.parse(localStorage.getItem('dashboard_favorites') || '[]')
            };

            // 즐겨찾기 함수
            function isFavorite(branchId) {
                return state.favorites.includes(Number(branchId));
            }

            function toggleFavorite(branchId) {
                const id = Number(branchId);
                const idx = state.favorites.indexOf(id);
                if (idx > -1) {
                    state.favorites.splice(idx, 1);
                } else {
                    state.favorites.push(id);
                }
                localStorage.setItem('dashboard_favorites', JSON.stringify(state.favorites));
                return isFavorite(id);
            }

            // 지역 그룹 매핑 (8대 분류)
            const REGION_GROUP_MAP = {
                // 표준 시/도
                '서울': '서울', '경기': '경기도', '인천': '경기도',
                '강원': '강원도',
                '충남': '충청도', '충북': '충청도', '대전': '충청도', '세종': '충청도',
                '전남': '전라도', '전북': '전라도', '광주': '전라도',
                '경남': '경상도', '경북': '경상도', '부산': '경상도', '대구': '경상도', '울산': '경상도',
                '제주': '제주도',
                '해외': '해외',
                // 공항/도시명 (비표준)
                '김포공항': '서울', '강남': '서울',
                '인천공항': '경기도',
                '강릉': '강원도', '속초': '강원도',
                '여수': '전라도', '전주': '전라도',
                '김해공항': '경상도', '김해': '경상도', '대구공항': '경상도', '경주': '경상도',
                '제주공항': '제주도',
            };

            function getRegionGroup(region) {
                if (!region) return '해외';
                const prefix = region.trim().split(' ')[0];
                return REGION_GROUP_MAP[prefix] || '해외';
            }

            // 테이블 셀 표시용 (상세 지역)
            function toMetroRegion(region) {
                if (!region) return '-';
                return region.trim();
            }

            // State getters
            function getState() { return state; }
            function getPagination() { return state.pagination; }
            function getSort() { return state.sort; }
            function getDateFilter() { return state.dateFilter; }
            function getEditMode() { return state.editMode; }
            function getReviews() { return state.reviews; }
            function getSummaries() { return state.summaries; }

            // State setters
            function setCurrentPage(page) { state.pagination.currentPage = Math.max(0, page); }
            function stateNextPage() { state.pagination.currentPage++; }
            function statePrevPage() { if (state.pagination.currentPage > 0) state.pagination.currentPage--; }
            function resetPage() { state.pagination.currentPage = 0; }

            function setSort(field, order) {
                if (state.sort.field === field && !order) {
                    state.sort.order = state.sort.order === 'asc' ? 'desc' : 'asc';
                } else {
                    state.sort.field = field;
                    state.sort.order = order || (field === 'branch_name' ? 'asc' : 'desc');
                }
            }

            function setDateFilter(from, to) {
                state.dateFilter.from = from;
                state.dateFilter.to = to;
            }

            function stateClearDateFilter() {
                state.dateFilter.from = null;
                state.dateFilter.to = null;
            }

            function setDatePicker(picker) { state.dateFilter.picker = picker; }

            function enterEditModeState() {
                state.editMode.isActive = true;
                state.editMode.originalTags = [...state.editMode.selectedTags];
            }

            function exitEditModeState(restore = false) {
                state.editMode.isActive = false;
                if (restore) {
                    state.editMode.selectedTags = [...state.editMode.originalTags];
                }
            }

            function setSelectedTags(tags) { state.editMode.selectedTags = [...tags]; }
            function stateToggleTag(tag) {
                const idx = state.editMode.selectedTags.indexOf(tag);
                if (idx > -1) {
                    state.editMode.selectedTags.splice(idx, 1);
                } else {
                    state.editMode.selectedTags.push(tag);
                }
            }

            function addTag(tag) {
                if (state.editMode.selectedTags.includes(tag)) return false;
                state.editMode.selectedTags.push(tag);
                return true;
            }

            function removeTag(tag) {
                const idx = state.editMode.selectedTags.indexOf(tag);
                if (idx > -1) state.editMode.selectedTags.splice(idx, 1);
            }

            function setCurrentPeriod(period) { state.editMode.currentPeriod = period; }
            function commitTags() { state.editMode.originalTags = [...state.editMode.selectedTags]; }
            function setReviewsPage(page) { state.reviews.currentPage = Math.max(0, page); }

            function resetReviews() {
                state.reviews.currentPage = 0;
                state.reviews.total = 0;
                state.reviews.visible = false;
                state.reviews.carModelsLoaded = false;
            }

            function toggleReviewsVisibility() {
                state.reviews.visible = !state.reviews.visible;
                if (state.reviews.visible) {
                    state.reviews.currentPage = 0;
                    state.reviews.carModelsLoaded = false;
                }
                return state.reviews.visible;
            }

            function setReviewsTotal(total) { state.reviews.total = total; }
            function markCarModelsLoaded() { state.reviews.carModelsLoaded = true; }

            // Car list state functions
            function toggleCarListVisibility() {
                state.carList.visible = !state.carList.visible;
                return state.carList.visible;
            }
            function resetCarList() {
                state.carList.visible = false;
                state.carList.loaded = false;
                state.carList.models = [];
            }
            function setCarListModels(models) {
                state.carList.models = models;
                state.carList.loaded = true;
            }

            function setSummaries(data) { state.summaries = data; }

            function updateSummaryState(branchId, updates) {
                const idx = state.summaries.findIndex(s => Number(s.branch_id) === Number(branchId));
                if (idx > -1) {
                    state.summaries[idx] = { ...state.summaries[idx], ...updates };
                }
            }

            function setRegionStats(data) { state.regionStats = data; }

            // ============================================================
            // API (api.js)
            // ============================================================

            // apiRequest → shared-utils.js

            async function fetchStats() {
                const result = await apiRequest(`${API_PREFIX}/summaries/stats`);
                return result.data;
            }

            async function fetchRegionStats() {
                const result = await apiRequest(`${API_PREFIX}/summaries/stats/region`);
                return result.data;
            }

            function buildSummariesParams(filters = {}) {
                const favCount = state.favorites.length;
                const pageSize = state.pagination.pageSize;
                const currentPage = state.pagination.currentPage;

                // 이전 페이지까지 표시된 즐겨찾기 수
                const prevFavShown = Math.min(favCount, currentPage * pageSize);
                // 이전 페이지까지 표시된 일반 항목 수
                const prevNormalShown = Math.max(0, (currentPage * pageSize) - favCount);
                // 일반 데이터 offset
                const offset = prevNormalShown;

                // 즐겨찾기 필터링 후에도 충분한 데이터가 남도록 여유분 추가
                const limit = pageSize + favCount;

                const params = new URLSearchParams({
                    limit: limit,
                    offset: offset,
                    sort_by: state.sort.field,
                    order: state.sort.order,
                    min_reviews: 0
                });

                if (filters.keyword) params.set('keyword', filters.keyword);
                if (filters.region) params.set('region_group', filters.region);
                if (state.dateFilter.from) params.set('review_date_from', state.dateFilter.from);
                if (state.dateFilter.to) params.set('review_date_to', state.dateFilter.to);

                return params;
            }

            async function fetchSummaries(filters = {}) {
                const params = buildSummariesParams(filters);
                const result = await apiRequest(`${API_PREFIX}/summaries?${params}`);
                const data = result.data;
                // branch_id를 Number로 정규화 (favorites 비교 타입 일관성)
                data.forEach(d => { d.branch_id = Number(d.branch_id); });
                return data;
            }

            async function fetchSummaryDetail(branchId) {
                const result = await apiRequest(`${API_PREFIX}/summaries/${branchId}`);
                return result.data;
            }

            async function apiUpdateSummary(branchId, data) {
                return apiRequest(`${API_PREFIX}/summaries/${branchId}`, {
                    method: 'PATCH',
                    body: JSON.stringify(data)
                });
            }


            async function apiRegenerateSummary(branchId) {
                return apiRequest(`${API_PREFIX}/summaries/${branchId}/regenerate`, {
                    method: 'POST'
                });
            }

            async function apiApplyPendingSummary(branchId, period) {
                return apiRequest(`${API_PREFIX}/summaries/${branchId}/apply-pending`, {
                    method: 'POST',
                    body: JSON.stringify({ period })
                });
            }

            async function apiDiscardPendingSummary(branchId, period) {
                return apiRequest(`${API_PREFIX}/summaries/${branchId}/discard-pending`, {
                    method: 'POST',
                    body: JSON.stringify({ period })
                });
            }


            async function fetchBranchReviews(branchId, options = {}) {
                const params = new URLSearchParams({
                    limit: options.limit || 20,
                    offset: options.offset || 0
                });

                if (options.carModel) params.set('car_model', options.carModel);
                if (options.sentiment) params.set('sentiment', options.sentiment);
                if (state.dateFilter.from) params.set('review_date_from', state.dateFilter.from);
                if (state.dateFilter.to) params.set('review_date_to', state.dateFilter.to);

                const result = await apiRequest(`${API_PREFIX}/summaries/${branchId}/reviews?${params}`);
                return result.data;
            }

            async function fetchBranchTagsBatch(branchIds) {
                if (!branchIds || branchIds.length === 0) return {};
                const result = await apiRequest(`${API_PREFIX}/tags/batch`, {
                    method: 'POST',
                    body: JSON.stringify({ branch_ids: branchIds })
                });
                return result.data || {};
            }



            // ============================================================
            // UI (ui.js)
            // ============================================================

            const elements = {};

            function getElement(id) {
                const elNode = document.getElementById(id);
                if (elNode) {
                    elements[id] = elNode;
                }
                return elNode || elements[id];
            }

            function el(tag, attrs, children) {
                var node = document.createElement(tag);
                if (attrs) {
                    Object.keys(attrs).forEach(function (k) {
                        if (k === 'className') node.className = attrs[k];
                        else if (k === 'textContent') node.textContent = attrs[k];
                        else if (k === 'style' && typeof attrs[k] === 'object') {
                            Object.assign(node.style, attrs[k]);
                        } else node.setAttribute(k, attrs[k]);
                    });
                }
                if (children) {
                    children.forEach(function (child) {
                        if (typeof child === 'string') node.appendChild(document.createTextNode(child));
                        else if (child) node.appendChild(child);
                    });
                }
                return node;
            }

            function renderSkeletonTable(rowCount = 8) {
                const tableEl = getElement('summaries-table');
                if (!tableEl) return;
                let html = '';
                for (let i = 0; i < rowCount; i++) {
                    html += `<tr class="skeleton-row">
                        <td></td>
                        <td><div class="skeleton-line short" style="width: 36px; height: 12px;"></div></td>
                        <td><div class="skeleton-line medium" style="width: ${60 + Math.random() * 40}%; height: 14px; margin-bottom: 6px;"></div><div class="skeleton-line" style="width: 50%; height: 10px;"></div></td>
                        <td><div class="skeleton-line long" style="height: 14px;"></div></td>
                        <td><div class="skeleton-line short" style="width: 44px; height: 14px;"></div></td>
                        <td><div class="skeleton-line short" style="width: 36px; height: 14px;"></div></td>
                    </tr>`;
                }
                tableEl.innerHTML = html;
            }

            function renderStats(stats) {
                const statTotal = getElement('stat-total');
                const statReviews = getElement('stat-reviews');

                if (statTotal) statTotal.textContent = stats.total?.toLocaleString() || '0';
                if (statReviews) statReviews.textContent = stats.total_reviews?.toLocaleString() || '0';
            }

            function renderTable(data, onDetailClick) {
                const tableEl = getElement('summaries-table');

                if (!tableEl) return;

                if (!data || data.length === 0) {
                    tableEl.innerHTML = '<tr><td colspan="6" style="text-align:center; color: var(--grey-5);">데이터 없음</td></tr>';
                    return;
                }

                const html = data.map(row => renderTableRow(row, onDetailClick)).join('');
                tableEl.innerHTML = html;

                // Add click handlers to table rows
                attachRowClickHandlers();

                // 선택 상태 복원 (페이지 전환 시 state 기반)
                restoreBranchCheckboxes();
            }

            function findBestPeriod(data) {
                for (const p of PERIOD_PRIORITY) {
                    if (data['summary_' + p]) return p;
                }
                return 'all';
            }

            function getBestSummary(row) {
                return row['summary_' + findBestPeriod(row)] || '';
            }

            function renderTableRow(row, onDetailClick) {
                const bestSummary = getBestSummary(row);
                const summaryPreview = bestSummary
                    ? escapeHtml(bestSummary.length > 40 ? bestSummary.substring(0, 40) + '...' : bestSummary)
                    : '<span style="color: var(--grey-5); font-style: italic;">요약 없음</span>';

                const isFav = isFavorite(row.branch_id);
                const rating = row.avg_rating ? row.avg_rating.toFixed(1) : '-';
                const fullSummary = bestSummary ? escapeAttr(bestSummary) : '';

                return `
                <tr class="clickable-row" data-branch-id="${row.branch_id}" data-summary="${fullSummary}" style="vertical-align: middle; cursor: pointer; transition: background-color 0.2s;">
                    <td style="text-align: center; padding: 4px;">
                        <input type="checkbox" class="branch-checkbox" data-branch-id="${row.branch_id}" onchange="window.dashboardHandlers.updateBranchSelection()" style="cursor: pointer; accent-color: var(--primary);">
                    </td>
                    <td style="text-align: center; color: var(--grey-3); font-size: 11px;">${toMetroRegion(row.region)}</td>
                    <td>
                        <div class="branch-info">
                            <span class="company-name">
                                ${isFav ? '<span style="color: #f59e0b; margin-right: 4px;">⭐</span>' : ''}${escapeHtml(row.affiliate_name || row.branch_name || '-')}
                            </span>
                            ${row.affiliate_name && row.branch_name ? `<span class="branch-name">${escapeHtml(row.branch_name)}</span>` : ''}
                        </div>
                    </td>
                    <td class="summary-cell" style="font-size: 13px; color: var(--grey-3); line-height: 1.5; cursor: pointer;">${summaryPreview}</td>
                    <td style="text-align: center; font-weight: 600; color: #f59e0b;">⭐ ${rating}</td>
                    <td style="text-align: center; font-weight: 600; font-size: 15px;">${row.review_count?.toLocaleString() || 0}</td>
                </tr>
            `;
            }

            function attachRowClickHandlers() {
                const rows = document.querySelectorAll('.clickable-row');
                rows.forEach(row => {
                    row.addEventListener('click', function (e) {
                        if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON' || e.target.closest('button') || e.target.closest('a')) {
                            return;
                        }

                        const branchId = this.getAttribute('data-branch-id');
                        if (!branchId) return;

                        // 요약 컬럼 클릭 → 상세 모달
                        if (e.target.closest('.summary-cell')) {
                            window.dashboardHandlers.showDetail(parseInt(branchId));
                            return;
                        }

                        // 나머지 영역 클릭 → 체크박스 토글
                        const cb = this.querySelector('.branch-checkbox');
                        if (cb && e.target !== cb) {
                            cb.checked = !cb.checked;
                        }
                        window.dashboardHandlers.updateBranchSelection();
                    });

                    // Add hover effect
                    row.addEventListener('mouseenter', function () {
                        this.style.backgroundColor = 'var(--grey-7)';
                    });
                    row.addEventListener('mouseleave', function () {
                        this.style.backgroundColor = '';
                    });
                });

                // Attach summary tooltip handlers
                attachSummaryTooltipHandlers();
            }

            // Summary Tooltip - 마우스를 따라다니는 요약 툴팁
            function attachSummaryTooltipHandlers() {
                const tooltip = getOrCreateSummaryTooltip();
                const summaryCells = document.querySelectorAll('.summary-cell');

                summaryCells.forEach(cell => {
                    const row = cell.closest('.clickable-row');
                    const summary = row?.getAttribute('data-summary');

                    if (!summary) return;

                    cell.addEventListener('mouseenter', function (e) {
                        tooltip.textContent = summary;
                        tooltip.classList.add('visible');
                        updateTooltipPosition(e, tooltip);
                    });

                    cell.addEventListener('mousemove', function (e) {
                        updateTooltipPosition(e, tooltip);
                    });

                    cell.addEventListener('mouseleave', function () {
                        tooltip.classList.remove('visible');
                    });
                });
            }

            function getOrCreateSummaryTooltip() {
                let tooltip = document.getElementById('summary-tooltip');
                if (!tooltip) {
                    tooltip = document.createElement('div');
                    tooltip.id = 'summary-tooltip';
                    tooltip.className = 'summary-tooltip';
                    document.body.appendChild(tooltip);
                }
                return tooltip;
            }

            function updateTooltipPosition(e, tooltip) {
                const offsetX = 15;
                const offsetY = 15;
                const padding = 10;

                let x = e.clientX + offsetX;
                let y = e.clientY + offsetY;

                // 화면 오른쪽 경계 체크
                if (x + tooltip.offsetWidth + padding > window.innerWidth) {
                    x = e.clientX - tooltip.offsetWidth - offsetX;
                }

                // 화면 아래쪽 경계 체크
                if (y + tooltip.offsetHeight + padding > window.innerHeight) {
                    y = e.clientY - tooltip.offsetHeight - offsetY;
                }

                tooltip.style.left = x + 'px';
                tooltip.style.top = y + 'px';
            }

            function updateSortUI() {
                document.querySelectorAll('.sort-icon').forEach(el => el.textContent = '');
                const iconEl = getElement(`sort-icon-${state.sort.field}`);
                if (iconEl) {
                    iconEl.textContent = state.sort.order === 'asc' ? ' ↑' : ' ↓';
                    iconEl.style.color = 'var(--primary)';
                }
            }

            function createReviewLinkNode(reviewId) {
                if (!isValidReviewId(reviewId)) return null;
                const encodedId = encodeURIComponent(String(reviewId));
                const reviewUrl = buildCarmoreReviewUrl(encodedId);
                return el('a', {
                    href: reviewUrl, target: '_blank', rel: 'noopener noreferrer',
                    className: 'review-link', title: 'Carmore 관리자에서 리뷰 보기'
                }, ['#' + String(reviewId)]);
            }

            function renderReviewItemNode(reviewData, index, pageOffset) {
                var linkNode = createReviewLinkNode(reviewData.review_id);
                if (!linkNode) {
                    linkNode = el('span', {}, ['#' + (pageOffset + index + 1)]);
                }
                var sentimentIcon = reviewData.sentiment ? getSentimentIcon(reviewData.sentiment) : '';
                var metaLeft = el('span', { className: 'review-item__meta' }, [
                    linkNode,
                    sentimentIcon ? el('span', { className: 'review-item__sentiment', textContent: sentimentIcon }) : null
                ]);
                var metaRight = el('span', { className: 'review-item__meta', textContent: formatDate(reviewData.review_date) });
                var header = el('div', { className: 'review-item__header' }, [metaLeft, metaRight]);
                var content = el('div', { className: 'review-item__content', textContent: reviewData.content || '-' });
                var footerNode = renderReviewFooterNode(reviewData);
                return el('div', { className: 'review-item' }, [header, content, footerNode]);
            }

            function renderReviewFooterNode(reviewData) {
                var metaParts = [];
                if (reviewData.rating_service) metaParts.push('친절: ' + reviewData.rating_service);
                if (reviewData.rating_car) metaParts.push('차량: ' + reviewData.rating_car);
                if (reviewData.car_model) metaParts.push(reviewData.car_model);
                if (metaParts.length === 0) return null;
                return el('div', { className: 'review-item__footer', textContent: metaParts.join(' | ') });
            }

            function renderReviewsList(reviews, offset) {
                const listEl = getElement('reviews-list');
                if (!listEl) return;

                listEl.textContent = '';
                if (reviews.length === 0) {
                    listEl.appendChild(el('div', { className: 'review-item', style: { textAlign: 'center' }, textContent: '리뷰가 없습니다.' }));
                } else {
                    reviews.forEach(function (r, idx) {
                        listEl.appendChild(renderReviewItemNode(r, idx, offset));
                    });
                }
            }

            function updateReviewsPagination(currentPage, totalPages) {
                const pageInfo = getElement('reviews-page-info');
                const prevBtn = getElement('reviews-prev-btn');
                const nextBtn = getElement('reviews-next-btn');

                if (pageInfo) pageInfo.textContent = `${currentPage + 1} / ${totalPages || 1}`;
                if (prevBtn) prevBtn.disabled = currentPage === 0;
                if (nextBtn) nextBtn.disabled = (currentPage + 1) >= totalPages;
            }

            function updateReviewsCount(total) {
                const countEl = getElement('reviews-count');
                if (countEl) countEl.textContent = `(총 ${total.toLocaleString()}건)`;
            }

            function updateCarModelDropdown(carModels) {
                const carSelect = getElement('filter-car-model');
                if (carSelect && carModels.length > 0) {
                    carSelect.textContent = '';
                    carSelect.appendChild(new Option('\uD83D\uDE97 전체 차량', ''));
                    carModels.forEach(function (m) {
                        carSelect.appendChild(new Option(m, m));
                    });
                }
            }

            function renderTagsDisplay(tags) {
                const display = getElement('tags-display');
                if (!display) return;

                display.textContent = '';
                if (tags.length > 0) {
                    tags.forEach(function (t) {
                        display.appendChild(el('span', {
                            className: 'keyword',
                            textContent: t,
                            style: { background: getKeywordColor(t), color: getKeywordTextColor(t) }
                        }));
                    });
                } else {
                    display.appendChild(el('span', { className: 'summary-empty', textContent: '태그 없음' }));
                }
            }

            function renderTagSelector(selectedTags, onToggle, onRemove) {
                const selector = getElement('tag-selector');
                if (!selector) return;

                const allTags = [...new Set([...DEFAULT_TAGS, ...selectedTags])];

                selector.textContent = '';
                allTags.forEach(function (tag) {
                    const isSelected = selectedTags.includes(tag);
                    const isCustom = !DEFAULT_TAGS.includes(tag);
                    const bg = isSelected ? getKeywordColor(tag) : 'var(--grey-8)';
                    const color = isSelected ? getKeywordTextColor(tag) : 'var(--grey-3)';
                    const border = isSelected ? '2px solid var(--primary)' : '2px solid transparent';

                    var children = [tag];
                    if (isCustom) {
                        var deleteBtn = el('span', {
                            textContent: '\u2715',
                            style: { marginLeft: '4px', fontSize: '10px' }
                        });
                        deleteBtn.addEventListener('click', function (e) {
                            e.stopPropagation();
                            window.dashboardHandlers.removeCustomTag(tag);
                        });
                        children.push(deleteBtn);
                    }

                    var tagSpan = el('span', {
                        className: 'keyword',
                        'data-tag': tag,
                        style: { background: bg, color: color, border: border, cursor: 'pointer', userSelect: 'none' }
                    }, children);
                    tagSpan.addEventListener('click', function () {
                        window.dashboardHandlers.toggleTag(tag);
                    });
                    selector.appendChild(tagSpan);
                });
            }

            function openModal() {
                const modal = getElement('detail-modal');
                if (modal) modal.classList.add('active');
            }

            function uiCloseModal() {
                const modal = getElement('detail-modal');
                if (modal) modal.classList.remove('active');
            }

            function showModalLoading() {
                const body = getElement('modal-body');
                if (body) body.innerHTML = '<div class="loading"><div class="spinner"></div>로딩 중...</div>';
            }

            function showModalError(message = '로드 실패') {
                const body = getElement('modal-body');
                if (body) body.innerHTML = `<div style="color: var(--error);">${escapeHtml(message)}</div>`;
            }

            function setModalTitle(title) {
                const titleEl = getElement('modal-title');
                if (titleEl) titleEl.textContent = title;
            }

            function toggleEditModeUI(isEditMode) {
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

                PERIOD_ALL_DESC.forEach(period => {
                    const textEl = getElement(`summary-text-${period}`);
                    const editEl = getElement(`edit-summary-${period}`);
                    if (textEl) textEl.style.display = isEditMode ? 'none' : 'block';
                    if (editEl) editEl.style.display = isEditMode ? 'block' : 'none';
                });
            }

            function uiShowSummaryTab(tabEl, period) {
                document.querySelectorAll('.tabs .tab').forEach(t => {
                    t.classList.remove('active');
                    t.style.background = 'var(--grey-8)';
                    t.style.color = 'var(--grey-3)';
                });

                if (tabEl) {
                    tabEl.classList.add('active');
                    tabEl.style.background = 'var(--grey-2)';
                    tabEl.style.color = 'white';
                }

                document.querySelectorAll('.summary-panel').forEach(p => p.style.display = 'none');
                const panel = getElement(`panel-${period}`);
                if (panel) panel.style.display = 'block';
            }

            function showReviewsLoading() {
                const listEl = getElement('reviews-list');
                if (listEl) listEl.innerHTML = '<div class="loading"><div class="spinner"></div>로딩 중...</div>';
            }

            function showTableMessage(message, isError = false) {
                const tableEl = getElement('summaries-table');
                if (tableEl) {
                    const style = isError ? 'color: var(--error);' : 'color: var(--grey-5);';
                    tableEl.innerHTML = `<tr><td colspan="6" style="text-align:center; ${style}">${escapeHtml(message)}</td></tr>`;
                }
            }

            // ============================================================
            // INDEX / MAIN CONTROLLER (index.js)
            // ============================================================

            async function init() {
                bindEvents();
                initDateRangePicker();

                // 순차 호출: uvicorn --limit-concurrency 2 제한 준수
                await loadStats();
                await loadRegionStatsData();
                await loadSummaries();

                registerGlobalHandlers();

                console.log('Dashboard initialized (v2.0)');
            }

            async function handleToggleFavorite(branchId) {
                const isFav = toggleFavorite(branchId);
                const btn = getElement('btn-favorite');
                if (btn) {
                    btn.textContent = isFav ? '⭐' : '☆';
                    btn.title = isFav ? '즐겨찾기 해제' : '즐겨찾기 추가';
                }
                showToast(isFav ? '즐겨찾기에 추가되었습니다' : '즐겨찾기가 해제되었습니다', 'success');
                // 현재 페이지 유지, 백그라운드에서 테이블 업데이트
                // (즐겨찾기 항목은 1페이지로 가면 최상단에 표시됨)
                await loadSummaries();
            }

            function registerGlobalHandlers() {
                window.dashboardHandlers = {
                    showDetail,
                    handleSort,
                    prevPage,
                    nextPage,
                    toggleReviews,
                    loadMoreReviews,
                    applyFilters,
                    onCarModelChange,
                    enterEditMode,
                    cancelEditMode,
                    saveAllChanges,

                    showSummaryTab,
                    regenerateSummary,
                    applyPendingSummary,
                    discardPendingSummary,
                    toggleTag,
                    addCustomTag,
                    removeCustomTag,
                    closeModal,
                    clearDateFilter,
                    toggleFavorite: handleToggleFavorite,
                    // AI Report handlers
                    openReportModal,
                    closeReportModal,
                    setReportPeriod,
                    onReportDateChange,
                    checkReviewCount,
                    generateReport,
                    regenerateReport,
                    renderReportPeriodSelection,
                    renderReportList,
                    loadSavedReport,
                    renderReportContent,
                    downloadReportPDF,
                    deleteReport,
                    // Batch PDF handlers
                    downloadBatchPDF,
                    updateBranchSelection,
                    toggleSelectAllBranch,
                    clearBranchSelection
                };

                window.handleSort = handleSort;
                window.prevPage = prevPage;
                window.nextPage = nextPage;
            }

            function bindEvents() {
                // 헤더 네비게이션 버튼
                const btnPipelineConsole = document.getElementById('btn-pipeline-console');
                if (btnPipelineConsole) {
                    btnPipelineConsole.addEventListener('click', () => {
                        window.location.href = `${BASE_PATH}/pipeline-console`;
                    });
                }

                const btnAnalysis = document.getElementById('btn-analysis');

                if (btnAnalysis) {
                    btnAnalysis.addEventListener('click', () => {
                        window.location.href = `${BASE_PATH}/analysis`;
                    });
                }
                const btnReviewDetail = document.getElementById('btn-review-detail');
                if (btnReviewDetail) {
                    btnReviewDetail.addEventListener('click', () => {
                        window.location.href = `${BASE_PATH}/review-detail-test`;
                    });
                }
                const btnScheduler = document.getElementById('btn-scheduler');
                if (btnScheduler) {
                    btnScheduler.addEventListener('click', () => {
                        window.location.href = `${BASE_PATH}/scheduler`;
                    });
                }

                const selectAllBranch = getElement('select-all-branch');
                if (selectAllBranch) {
                    selectAllBranch.addEventListener('change', toggleSelectAllBranch);
                }

                const searchInput = getElement('search-input');
                const filterRegion = getElement('filter-region');
                const modal = getElement('detail-modal');

                const searchBox = getElement('search-box');
                const searchClear = getElement('search-clear');

                if (searchInput) {
                    searchInput.addEventListener('input', debounce(() => {
                        resetPage();
                        loadSummaries();
                    }, 300));

                    // X 버튼 표시 토글
                    searchInput.addEventListener('input', () => {
                        if (searchBox) {
                            searchBox.classList.toggle('has-value', searchInput.value.length > 0);
                        }
                    });
                }

                if (searchClear) {
                    searchClear.addEventListener('click', () => {
                        searchInput.value = '';
                        if (searchBox) searchBox.classList.remove('has-value');
                        resetPage();
                        loadSummaries();
                        searchInput.focus();
                    });
                }

                if (filterRegion) {
                    filterRegion.addEventListener('change', () => {
                        resetPage();
                        loadSummaries();
                    });
                }

                if (modal) {
                    modal.addEventListener('click', (e) => {
                        if (e.target.classList.contains('modal-overlay')) {
                            closeModal();
                        }
                    });
                }

                const reportModal = getElement('report-modal');
                if (reportModal) {
                    reportModal.addEventListener('click', (e) => {
                        if (e.target.classList.contains('report-modal-overlay')) {
                            closeReportModal();
                        }
                    });
                }
            }

            function initDateRangePicker() {
                const picker = flatpickr('#filter-date-range', {
                    mode: 'range',
                    locale: 'ko',
                    dateFormat: 'Y-m-d',
                    maxDate: 'today',
                    onChange: function (selectedDates) {
                        if (selectedDates.length === 2) {
                            setDateFilter(
                                formatDateForAPI(selectedDates[0]),
                                formatDateForAPI(selectedDates[1])
                            );
                            getElement('btn-clear-date').style.display = 'inline-block';
                            resetPage();
                            loadSummaries();
                        }
                    },
                    onClose: function (selectedDates) {
                        if (selectedDates.length === 1) {
                            const dateStr = formatDateForAPI(selectedDates[0]);
                            setDateFilter(dateStr, dateStr);
                            getElement('btn-clear-date').style.display = 'inline-block';
                            resetPage();
                            loadSummaries();
                        }
                    }
                });

                setDatePicker(picker);
            }

            async function loadStats() {
                try {
                    const stats = await fetchStats();
                    renderStats(stats);
                } catch (e) {
                    console.error('Stats load error:', e);
                }
            }

            // getRegionGroup()으로 대체됨 (8대 분류 매핑)

            async function loadRegionStatsData() {
                try {
                    const data = await fetchRegionStats();
                    setRegionStats(data);

                    // 8대 분류로 집계
                    const GROUP_ORDER = ['서울', '경기도', '강원도', '충청도', '전라도', '경상도', '제주도', '해외'];
                    const groupStats = {};
                    data.forEach(r => {
                        if (r.region && r.region !== '미분류') {
                            const group = REGION_GROUP_MAP[r.region] || '해외';
                            if (!groupStats[group]) {
                                groupStats[group] = { count: 0, total_reviews: 0 };
                            }
                            groupStats[group].count += r.count || 0;
                            groupStats[group].total_reviews += r.total_reviews || 0;
                        }
                    });

                    const select = getElement('filter-region');
                    if (select) {
                        GROUP_ORDER.forEach(group => {
                            const stats = groupStats[group];
                            if (!stats) return;
                            const opt = document.createElement('option');
                            opt.value = group;
                            opt.textContent = `${group} (${stats.count})`;
                            select.appendChild(opt);
                        });
                    }

                    const totalReviews = data.reduce((sum, r) => sum + (r.total_reviews || 0), 0);
                    const statReviews = getElement('stat-reviews');
                    if (statReviews) {
                        statReviews.textContent = totalReviews.toLocaleString();
                    }
                } catch (e) {
                    console.error('Region stats error:', e);
                }
            }

            // 필터 조건에 맞는지 확인하는 함수
            function matchesFilters(item, filters) {
                // 지역 그룹 필터 확인
                if (filters.region && getRegionGroup(item.region) !== filters.region) {
                    return false;
                }

                // 기간 필터 확인 (리뷰 날짜 기준)
                if (state.dateFilter.from || state.dateFilter.to) {
                    // 업체의 최신 리뷰 날짜나 업데이트 날짜를 확인
                    const itemDate = item.last_review_date || item.updated_at;
                    if (itemDate) {
                        const date = new Date(itemDate);
                        if (state.dateFilter.from) {
                            const fromDate = new Date(state.dateFilter.from);
                            if (date < fromDate) return false;
                        }
                        if (state.dateFilter.to) {
                            const toDate = new Date(state.dateFilter.to);
                            toDate.setHours(23, 59, 59, 999); // 해당 날짜의 끝까지 포함
                            if (date > toDate) return false;
                        }
                    }
                }

                return true;
            }

            function buildPageData(favoriteIds, currentPage, pageSize) {
                const favCount = favoriteIds.length;
                const prevFavShown = Math.min(favCount, currentPage * pageSize);
                const thisFavCount = Math.min(favCount - prevFavShown, pageSize);
                return {
                    prevFavShown,
                    thisFavCount,
                    thisNormalCount: pageSize - thisFavCount,
                    thisFavIds: favoriteIds.slice(prevFavShown, prevFavShown + thisFavCount)
                };
            }

            async function loadFavoriteItems(data, favoriteIds, pageData, filters) {
                const favIdSet = new Set(favoriteIds);
                const thisFavIdSet = new Set(pageData.thisFavIds);

                let favoriteData = [];
                const normalData = [];
                for (const d of data) {
                    if (thisFavIdSet.has(d.branch_id)) {
                        favoriteData.push(d);
                    } else if (!favIdSet.has(d.branch_id)) {
                        normalData.push(d);
                    }
                }

                // 현재 데이터에 없는 즐겨찾기는 별도 조회
                const loadedFavIds = new Set(favoriteData.map(d => d.branch_id));
                const missingFavIds = pageData.thisFavIds.filter(id => !loadedFavIds.has(id));

                if (missingFavIds.length > 0) {
                    const missingResults = await Promise.all(
                        missingFavIds.map(id => fetchSummaryDetail(id).catch(() => null))
                    );
                    missingResults.forEach(item => { if (item) favoriteData.push(item); });
                }

                favoriteData = favoriteData.filter(item => matchesFilters(item, filters));
                // 필터로 제외된 즐겨찾기만큼 일반 항목으로 보충
                const adjustedNormalCount = pageData.thisNormalCount + (pageData.thisFavCount - favoriteData.length);
                return { favoriteData, normalData: normalData.slice(0, adjustedNormalCount) };
            }

            async function attachTagsToData(allData) {
                const branchIds = allData.map(d => d.branch_id).filter(Boolean);
                let tagsData = {};

                if (branchIds.length > 0) {
                    try {
                        tagsData = await fetchBranchTagsBatch(branchIds);
                    } catch (e) {
                        console.error('Tags load error:', e);
                    }
                }

                allData.forEach(row => {
                    if (Array.isArray(row.keywords)) {
                        row.top_tags = row.keywords.map(k => ({ name: k }));
                    } else {
                        row.top_tags = tagsData[String(row.branch_id)] || [];
                    }
                });
            }

            async function loadSummaries() {
                const filters = {
                    keyword: getElement('search-input')?.value || '',
                    region: getElement('filter-region')?.value || ''
                };

                updateSortUI();
                renderSkeletonTable();

                try {
                    const data = await fetchSummaries(filters);
                    const favoriteIds = state.favorites;
                    const pageSize = state.pagination.pageSize;
                    const pageData = buildPageData(favoriteIds, state.pagination.currentPage, pageSize);

                    let favoriteData = [];
                    let normalData;

                    if (pageData.thisFavCount > 0) {
                        ({ favoriteData, normalData } = await loadFavoriteItems(data, favoriteIds, pageData, filters));
                    } else {
                        const favIdSet = new Set(favoriteIds);
                        normalData = data.filter(d => !favIdSet.has(d.branch_id));
                    }

                    const allData = [...favoriteData, ...normalData].slice(0, pageSize);
                    await attachTagsToData(allData);

                    setSummaries(allData);
                    renderTable(allData, showDetail);
                } catch (e) {
                    console.error('Summaries load error:', e);
                    showTableMessage('로드 실패', true);
                }
            }

            function handleSort(field) {
                setSort(field);
                resetPage();
                loadSummaries();
            }

            function prevPage() {
                if (state.pagination.currentPage > 0) {
                    statePrevPage();
                    loadSummaries();
                }
            }

            function nextPage() {
                if (state.summaries.length === state.pagination.pageSize) {
                    stateNextPage();
                    loadSummaries();
                }
            }

            function clearDateFilter() {
                if (state.dateFilter.picker) {
                    state.dateFilter.picker.clear();
                }
                stateClearDateFilter();
                getElement('btn-clear-date').style.display = 'none';
                resetPage();
                loadSummaries();
            }

            async function showDetail(branchId) {
                openModal();
                showModalLoading();
                resetReviews();
                resetCarList();

                try {
                    const data = await fetchSummaryDetail(branchId);
                    setModalTitle(data.branch_name || `지점 ${branchId}`);

                    const modalHtml = buildDetailModalHtml(data);
                    getElement('modal-body').innerHTML = modalHtml;

                    // innerHTML 설정 후 bestPeriod 초기화 (script 태그 대신 직접 실행)
                    const headerWrap = document.getElementById('summary-header-wrap');
                    const bestPeriod = headerWrap ? headerWrap.dataset.bestPeriod : 'all';
                    window._bestPeriod = bestPeriod;
                    const periodLabel = document.getElementById('summary-period-label');
                    const periodMap = { '1m': '1개월 요약', '3m': '3개월 요약', '6m': '6개월 요약', '1y': '1년 요약', 'all': '전체 기간 요약' };
                    if (periodLabel) periodLabel.textContent = periodMap[bestPeriod] || '';

                    await loadBranchTags(data, branchId);
                } catch (e) {
                    console.error('Detail load error:', e);
                    showModalError();
                }
            }

            function buildModalHeaderHtml(data, isFav) {
                return `
                <div class="modal-header-content" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                    <div style="flex: 1;">
                        <div style="font-size: 14px; color: var(--grey-5); margin-bottom: 4px;">ID: ${data.branch_id}</div>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <h2 style="font-size: 24px; font-weight: 700; color: var(--grey-1); margin: 0;">${escapeHtml(data.branch_name)}</h2>
                            <button id="btn-favorite" onclick="window.dashboardHandlers.toggleFavorite(${data.branch_id})"
                                style="background: none; border: none; cursor: pointer; font-size: 24px; padding: 0; line-height: 1;"
                                title="${isFav ? '즐겨찾기 해제' : '즐겨찾기 추가'}">
                                ${isFav ? '⭐' : '☆'}
                            </button>
                        </div>
                        <div id="region-display" style="font-size: 14px; color: var(--grey-3); margin-top: 4px;">${escapeHtml(data.region) || '지역 정보 없음'}</div>
                        <input type="text" id="region-input" value="${escapeAttr(data.region || '')}" placeholder="지역 입력 (예: 서울 강남구)"
                            style="display: none; margin-top: 8px; padding: 8px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 14px; width: 100%; max-width: 300px;">
                    </div>
                </div>`;
            }

            function buildModalTagsHtml() {
                return `
                <div style="margin-bottom: 24px;">
                    <div style="font-size: 14px; font-weight: 600; color: var(--grey-3); margin-bottom: 8px;">카테고리</div>
                    <div class="keywords" id="tags-display" style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <span class="summary-empty">로딩 중...</span>
                    </div>
                    <div id="edit-area-tags" style="display: none; margin-top: 12px;">
                        <div style="font-size: 12px; color: var(--grey-5); margin-bottom: 8px;">클릭하여 선택/해제:</div>
                        <div id="tag-selector" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;"></div>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <input type="text" id="custom-tag-input" placeholder="커스텀 카테고리 입력"
                                style="padding: 6px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 13px; width: 150px;">
                            <button class="btn btn-secondary btn-sm" onclick="window.dashboardHandlers.addCustomTag()">+ 추가</button>
                        </div>
                    </div>
                </div>`;
            }

            function buildModalStatsHtml(data) {
                return `
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 16px;">
                    <div style="background: var(--grey-9); padding: 16px; border-radius: var(--radius);">
                        <div style="font-size: 13px; color: var(--grey-5);">총 리뷰 수</div>
                        <div style="font-size: 20px; font-weight: 700; color: var(--grey-1); margin-top: 4px;">${data.review_count?.toLocaleString() || 0}건</div>
                    </div>
                    <div style="background: var(--grey-9); padding: 16px; border-radius: var(--radius);">
                        <div style="font-size: 13px; color: var(--grey-5);">평균 평점</div>
                        <div style="font-size: 20px; font-weight: 700; color: var(--grey-1); margin-top: 4px;">⭐ ${data.avg_rating?.toFixed(2) || '0.0'}</div>
                    </div>
                </div>`;
            }

            function buildModalSummaryHtml(data, pendingSummaries) {
                const bestPeriod = findBestPeriod(data);
                let panels = '';
                for (const period of PERIOD_ALL_DESC) {
                    const isVisible = period === bestPeriod;
                    const pHasPending = !!pendingSummaries[period];
                    panels += `
                        <div class="summary-panel" id="panel-${period}" style="display: ${isVisible ? 'block' : 'none'};">
                            <div class="summary-text" id="summary-text-${period}" style="font-size: 15px; line-height: 1.7; color: var(--grey-2);">
                                ${escapeHtml(data['summary_' + period]) || '<span class="summary-empty" style="color: var(--grey-5); font-style: italic;">작성된 요약이 없습니다.</span>'}
                            </div>
                            <textarea id="edit-summary-${period}" style="display: none; width: 100%; min-height: 120px; padding: 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 14px; line-height: 1.6; resize: vertical; font-family: inherit;">${escapeHtml(data['summary_' + period]) || ''}</textarea>

                            <div id="pending-section-${period}" class="pending-summary-section" style="display: ${pHasPending ? 'block' : 'none'}; margin-top: 16px; padding: 16px; background: var(--primary-light); border: 2px dashed var(--primary); border-radius: var(--radius-sm);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                    <span style="font-size: 13px; font-weight: 600; color: var(--primary);">✨ 신규 생성 요약</span>
                                    <div style="display: flex; gap: 8px;">
                                        <button class="btn btn-primary btn-sm" onclick="window.dashboardHandlers.applyPendingSummary(${data.branch_id}, '${period}')" style="font-size: 12px; padding: 4px 12px;">변경</button>
                                        <button class="btn btn-secondary btn-sm" onclick="window.dashboardHandlers.discardPendingSummary(${data.branch_id}, '${period}')" style="font-size: 12px; padding: 4px 12px;">취소</button>
                                    </div>
                                </div>
                                <div id="pending-text-${period}" style="font-size: 14px; line-height: 1.6; color: var(--grey-2);">${escapeHtml(pendingSummaries[period]) || ''}</div>
                            </div>
                        </div>`;
                }

                return `
                <div data-best-period="${bestPeriod}" id="summary-header-wrap"></div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <div style="display: flex; align-items: baseline; gap: 8px;">
                        <span style="font-size: 14px; font-weight: 600; color: var(--grey-3);">요약</span>
                        <span id="summary-period-label" style="font-size: 12px; color: var(--grey-5);"></span>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn-ai-report" onclick="window.dashboardHandlers.openReportModal(${data.branch_id}, '${escapeAttr(data.branch_name)}', '${escapeAttr(data.affiliate_name || '')}')" title="AI 리포트 생성">
                            📋 AI 리포트
                        </button>
                        <button class="btn-ai-summary" onclick="window.dashboardHandlers.regenerateSummary(${data.branch_id}, event)" title="AI 요약 재생성">
                            ✨ AI 요약
                        </button>
                    </div>
                </div>
                <div id="summary-content" style="background: white; border-radius: var(--radius);">
                    ${panels}
                </div>`;
            }

            function buildModalActionsHtml(data) {
                return `
                <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--grey-8);">
                    <div id="view-mode-buttons" style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-secondary" onclick="window.dashboardHandlers.enterEditMode()">✏️ 수정</button>
                            <button class="btn btn-secondary" onclick="window.dashboardHandlers.toggleReviews(${data.branch_id})" id="btn-toggle-reviews">📋 리뷰 보기</button>
                        </div>
                    </div>
                    <div id="edit-mode-buttons" style="display: none; justify-content: flex-end; gap: 12px;">
                        <button class="btn btn-secondary" onclick="window.dashboardHandlers.cancelEditMode()">취소</button>
                        <button class="btn btn-primary" onclick="window.dashboardHandlers.saveAllChanges(${data.branch_id})">💾 저장</button>
                    </div>
                </div>`;
            }

            function buildModalReviewsSectionHtml(data) {
                return `
                <div id="reviews-section" style="display: none; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--grey-8);">
                    <div style="font-size: 14px; font-weight: 600; color: var(--grey-3); margin-bottom: 12px;">
                        📋 리뷰 목록 <span id="reviews-count" style="font-weight: normal; color: var(--grey-5);"></span>
                    </div>
                    <div id="reviews-filters" style="display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; align-items: center;">
                        <select id="filter-car-model" onchange="window.dashboardHandlers.onCarModelChange(${data.branch_id})" style="padding: 6px 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 13px; background: white;">
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
                </div>`;
            }

            function buildDetailModalHtml(data) {
                const pendingSummaries = data.pending_summaries || {};
                const isFav = isFavorite(data.branch_id);

                return buildModalHeaderHtml(data, isFav)
                    + buildModalTagsHtml()
                    + buildModalStatsHtml(data)
                    + buildModalSummaryHtml(data, pendingSummaries)
                    + buildModalActionsHtml(data)
                    + buildModalReviewsSectionHtml(data);
            }

            async function loadBranchTags(data, branchId) {
                let tags = [];

                if (Array.isArray(data.keywords)) {
                    tags = [...data.keywords];
                } else {
                    try {
                        const tagsData = await fetchBranchTagsBatch([branchId]);
                        const branchTags = tagsData[String(branchId)] || [];
                        tags = branchTags.map(t => t.name);
                    } catch (e) {
                        console.error('Tags load error:', e);
                    }
                }

                setSelectedTags(tags);
                commitTags();
                renderTagsDisplay(tags);
            }

            function closeModal() {
                uiCloseModal();
            }

            function enterEditMode() {
                enterEditModeState();
                toggleEditModeUI(true);
                renderTagSelector(state.editMode.selectedTags, toggleTag, removeCustomTagHandler);
            }

            function cancelEditMode() {
                exitEditModeState(true);
                toggleEditModeUI(false);
                renderTagsDisplay(state.editMode.selectedTags);
            }

            async function saveAllChanges(branchId) {
                const region = getElement('region-input')?.value.trim() || '';

                const summariesData = {};
                PERIOD_ALL_DESC.forEach(period => {
                    const editEl = getElement(`edit-summary-${period}`);
                    if (editEl) summariesData[`summary_${period}`] = editEl.value;
                });

                try {
                    const response = await apiUpdateSummary(branchId, {
                        region,
                        keywords: state.editMode.selectedTags,
                        ...summariesData
                    });

                    if (response.success) {
                        getElement('region-display').textContent = region || '지역 정보 없음';

                        PERIOD_ALL_DESC.forEach(period => {
                            const textEl = getElement(`summary-text-${period}`);
                            const editEl = getElement(`edit-summary-${period}`);
                            if (textEl && editEl) {
                                if (editEl.value) {
                                    textEl.textContent = editEl.value;
                                } else {
                                    textEl.innerHTML = '<span class="summary-empty" style="color: var(--grey-5); font-style: italic;">작성된 요약이 없습니다.</span>';
                                }
                            }
                        });

                        commitTags();
                        updateSummaryState(branchId, {
                            region,
                            top_tags: state.editMode.selectedTags.map(t => ({ name: t })),
                            ...summariesData
                        });

                        renderTable(state.summaries, showDetail);

                        exitEditModeState(false);
                        toggleEditModeUI(false);
                        renderTagsDisplay(state.editMode.selectedTags);

                        showToast('✅ 저장되었습니다.', 'success');
                    } else {
                        showToast('저장 실패', 'error');
                    }
                } catch (e) {
                    console.error('Save error:', e);
                    showToast('저장 중 오류 발생', 'error');
                }
            }

            function toggleTag(tag) {
                stateToggleTag(tag);
                renderTagSelector(state.editMode.selectedTags, toggleTag, removeCustomTagHandler);
            }

            function addCustomTag() {
                const input = getElement('custom-tag-input');
                const tagName = input?.value.trim();

                if (!tagName) return;

                if (!addTag(tagName)) {
                    showToast('이미 존재하는 카테고리입니다.', 'warning');
                    return;
                }

                input.value = '';
                renderTagSelector(state.editMode.selectedTags, toggleTag, removeCustomTagHandler);
            }

            function removeCustomTagHandler(tag) {
                removeTag(tag);
                renderTagSelector(state.editMode.selectedTags, toggleTag, removeCustomTagHandler);
            }

            // Alias for global handler
            function removeCustomTag(tag) {
                removeCustomTagHandler(tag);
            }

            function showSummaryTab(tabEl, period) {
                setCurrentPeriod(period);
                uiShowSummaryTab(tabEl, period);
            }

            async function regenerateSummary(branchId, e) {
                if (!confirm('AI로 요약을 재생성하시겠습니까?\n\n새 요약이 생성되며, "변경" 버튼을 눌러야 적용됩니다.')) {
                    return;
                }

                const btn = e?.target || e?.currentTarget;
                const originalText = btn.textContent;

                try {
                    btn.textContent = '⏳ 생성 중...';
                    btn.disabled = true;

                    const result = await apiRegenerateSummary(branchId);

                    const innerSuccess = result.data?.success !== false;
                    if (result.success && innerSuccess && result.data?.period) {
                        const generatedPeriod = result.data.period;

                        // 해당 기간 패널 표시
                        PERIOD_ALL_DESC.forEach(p => {
                            const panel = getElement(`panel-${p}`);
                            if (panel) panel.style.display = p === generatedPeriod ? 'block' : 'none';
                        });

                        const pendingSection = getElement(`pending-section-${generatedPeriod}`);
                        const pendingText = getElement(`pending-text-${generatedPeriod}`);

                        if (pendingSection && pendingText) {
                            pendingText.textContent = result.data.summary;
                            pendingSection.style.display = 'block';
                        }

                        // 기간 레이블 업데이트
                        const periodMap = { '1m': '1개월 요약', '3m': '3개월 요약', '6m': '6개월 요약', '1y': '1년 요약', 'all': '전체 기간 요약' };
                        const lbl = getElement('summary-period-label');
                        if (lbl) lbl.textContent = periodMap[generatedPeriod] || '';

                        window._bestPeriod = generatedPeriod;
                        setCurrentPeriod(generatedPeriod);

                        showToast('✨ 새 요약이 생성되었습니다.', 'success');
                    } else {
                        throw new Error(result.data?.error || result.error || '요약 생성 실패');
                    }
                } catch (error) {
                    console.error('Regenerate error:', error);
                    showToast('❌ 요약 생성 실패: ' + error.message, 'error');
                } finally {
                    btn.textContent = originalText;
                    btn.disabled = false;
                }
            }

            async function applyPendingSummary(branchId, period) {
                if (!confirm('새 요약을 적용하시겠습니까?')) {
                    return;
                }

                try {
                    const result = await apiApplyPendingSummary(branchId, period);

                    if (result.success) {
                        const textEl = getElement(`summary-text-${period}`);
                        const editEl = getElement(`edit-summary-${period}`);
                        const pendingSection = getElement(`pending-section-${period}`);

                        if (textEl) textEl.textContent = result.data.applied;
                        if (editEl) editEl.value = result.data.applied;
                        if (pendingSection) pendingSection.style.display = 'none';

                        showToast('✅ 요약이 적용되었습니다', 'success');
                    }
                } catch (error) {
                    console.error('Apply error:', error);
                    showToast('❌ 적용 실패: ' + error.message, 'error');
                }
            }

            async function discardPendingSummary(branchId, period) {
                if (!confirm('새 요약을 취소하시겠습니까?')) {
                    return;
                }

                try {
                    const result = await apiDiscardPendingSummary(branchId, period);

                    if (result.success) {
                        const pendingSection = getElement(`pending-section-${period}`);
                        if (pendingSection) pendingSection.style.display = 'none';

                        showToast('🗑️ 새 요약이 취소되었습니다', 'success');
                    }
                } catch (error) {
                    console.error('Discard error:', error);
                    showToast('❌ 취소 실패: ' + error.message, 'error');
                }
            }

            // ============================================================
            // AI REPORT FUNCTIONS
            // ============================================================

            let reportState = {
                branchId: null,
                branchName: '',
                affiliateName: '',
                startDate: '',
                endDate: '',
                reportData: null,
                config: {
                    output: {
                        include_period_summary: true,
                        include_affiliate_eval: true,
                        include_vehicle_eval: true,
                        include_trend_comparison: false,
                        include_benchmark: true,
                        include_priority_actions: false,
                        summary_max_length: 300,
                        eval_max_length: 150,
                    },
                    data: {
                        include_tags: true,
                        include_vehicles: true,
                        include_sample_reviews: true,
                        sample_review_count: 10,
                    },
                    prompt: {
                        custom_instruction: '',
                        analysis_perspective: 'operational',
                        tone: 'analytical',
                        detail_level: 'standard',
                        focus_areas: [],
                        temperature: 0.5,
                        preset_id: null,
                    },
                },
            };
            let presetCache = null;
            let reviewCountCache = null;

            async function openReportModal(branchId, branchName, affiliateName) {
                reportState.branchId = branchId;
                reportState.branchName = branchName;
                reportState.affiliateName = affiliateName;
                reportState.reportData = null;
                // config 리셋
                reportState.config = {
                    output: {
                        include_period_summary: true, include_affiliate_eval: true,
                        include_vehicle_eval: true, include_trend_comparison: false,
                        include_benchmark: true, include_priority_actions: false,
                        summary_max_length: 300, eval_max_length: 150,
                    },
                    data: {
                        include_tags: true, include_vehicles: true,
                        include_sample_reviews: true, sample_review_count: 10,
                    },
                    prompt: {
                        custom_instruction: '', analysis_perspective: 'operational',
                        tone: 'analytical', detail_level: 'standard',
                        focus_areas: [], temperature: 0.5, preset_id: null,
                    },
                };

                // 기본 날짜 설정 (최근 1개월 → 30건 미만이면 자동 확장)
                const today = new Date();
                const oneMonthAgo = new Date(today);
                oneMonthAgo.setMonth(today.getMonth() - 1);

                reportState.startDate = formatReportDate(oneMonthAgo);
                reportState.endDate = formatReportDate(today);

                const modal = getElement('report-modal');
                if (modal) {
                    modal.style.display = 'flex';
                    document.getElementById('report-modal-title').textContent = `📋 ${branchName} AI 리포트`;
                }

                // 저장된 리포트 목록 조회
                const body = getElement('report-modal-body');
                if (body) {
                    body.innerHTML = `
                        <div class="report-loading">
                            <div class="spinner"></div>
                            <div class="report-loading-text">리포트 확인 중...</div>
                        </div>
                    `;
                }

                try {
                    const response = await fetchRetry(`${API_PREFIX}/reports/${branchId}/list?limit=5`);
                    const result = await response.json();

                    if (result.success && result.data && result.data.length > 0) {
                        // 저장된 리포트가 있으면 목록 표시
                        renderReportList(result.data);
                    } else {
                        // 없으면 기간 선택 UI 표시
                        renderReportPeriodSelection();
                    }
                } catch (error) {
                    console.error('Report list fetch error:', error);
                    renderReportPeriodSelection();
                }
            }

            function renderReportList(reports) {
                const body = getElement('report-modal-body');
                if (!body) return;

                // 헤더 버튼들 숨기기
                ['header-back-btn', 'header-regen-btn', 'header-pdf-btn'].forEach(id => {
                    const btn = document.getElementById(id);
                    if (btn) btn.style.display = 'none';
                });

                var listSection = el('div', { style: { marginBottom: '16px' } }, [
                    el('div', { style: { fontSize: '14px', fontWeight: '500', color: 'var(--grey-2)', marginBottom: '12px' }, textContent: '\uD83D\uDCC1 저장된 리포트' })
                ]);

                reports.forEach(function (r) {
                    var periodText = el('div', { style: { fontWeight: '500', color: 'var(--grey-2)' }, textContent: r.period_start + ' ~ ' + r.period_end });
                    var countText = el('div', { style: { fontSize: '12px', color: 'var(--grey-5)', marginTop: '4px' }, textContent: '총 ' + r.total_reviews + '건 리뷰 분석' });
                    var dateText = el('div', { style: { fontSize: '12px', color: 'var(--grey-5)' }, textContent: new Date(r.created_at).toLocaleDateString('ko-KR') });

                    var deleteBtn = el('button', {
                        className: 'delete-report-btn',
                        style: { background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '18px', color: 'var(--grey-5)', padding: '4px 8px', transition: 'color 0.2s' },
                        title: '리포트 삭제',
                        textContent: '\uD83D\uDDD1\uFE0F'
                    });
                    deleteBtn.addEventListener('click', function (e) {
                        e.stopPropagation();
                        window.dashboardHandlers.deleteReport(r.period_start, r.period_end);
                    });
                    deleteBtn.addEventListener('mouseenter', function () { deleteBtn.style.color = '#dc3545'; });
                    deleteBtn.addEventListener('mouseleave', function () { deleteBtn.style.color = 'var(--grey-5)'; });

                    var item = el('div', {
                        className: 'saved-report-item',
                        style: { cursor: 'pointer', padding: '12px', border: '1px solid var(--grey-7)', borderRadius: '8px', marginBottom: '8px', transition: 'all 0.2s' }
                    }, [
                        el('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } }, [
                            el('div', {}, [periodText, countText]),
                            el('div', { style: { display: 'flex', alignItems: 'center', gap: '12px' } }, [dateText, deleteBtn])
                        ])
                    ]);
                    item.addEventListener('click', function () {
                        window.dashboardHandlers.loadSavedReport(r.period_start, r.period_end);
                    });
                    item.addEventListener('mouseenter', function () { item.style.borderColor = 'var(--primary)'; });
                    item.addEventListener('mouseleave', function () { item.style.borderColor = 'var(--grey-7)'; });
                    listSection.appendChild(item);
                });

                var newBtn = el('button', {
                    className: 'btn btn-primary',
                    style: { width: '100%' },
                    textContent: '+ 새 기간으로 리포트 생성'
                });
                newBtn.addEventListener('click', function () {
                    window.dashboardHandlers.renderReportPeriodSelection();
                });

                var newSection = el('div', { style: { borderTop: '1px solid var(--grey-7)', paddingTop: '16px' } }, [
                    el('div', { style: { fontSize: '14px', fontWeight: '500', color: 'var(--grey-2)', marginBottom: '12px' }, textContent: '\u2728 새 리포트 생성' }),
                    newBtn
                ]);

                body.textContent = '';
                body.appendChild(listSection);
                body.appendChild(newSection);
            }

            async function loadSavedReport(startDate, endDate) {
                const body = getElement('report-modal-body');
                if (!body) return;

                reportState.startDate = startDate;
                reportState.endDate = endDate;

                body.innerHTML = `
                    <div class="report-loading">
                        <div class="spinner"></div>
                        <div class="report-loading-text">리포트를 불러오는 중...</div>
                    </div>
                `;

                try {
                    const response = await fetchRetry(`${API_PREFIX}/reports/${reportState.branchId}?start_date=${startDate}&end_date=${endDate}`);
                    const result = await response.json();

                    if (result.success) {
                        reportState.reportData = result.data;
                        renderReportContent(result.data, false); // is_new = false
                    } else {
                        throw new Error(result.error || '리포트 조회 실패');
                    }
                } catch (error) {
                    console.error('Report load error:', error);
                    body.textContent = '';
                    const errWrap = document.createElement('div');
                    errWrap.style.cssText = 'text-align: center; padding: 40px;';
                    const errIcon = document.createElement('div');
                    errIcon.style.cssText = 'font-size: 48px; margin-bottom: 16px;';
                    errIcon.textContent = '\u274C';
                    const errTitle = document.createElement('div');
                    errTitle.style.cssText = 'font-size: 16px; color: var(--grey-2);';
                    errTitle.textContent = '리포트 조회 실패';
                    const errMsg = document.createElement('div');
                    errMsg.style.cssText = 'font-size: 14px; color: var(--grey-5); margin-top: 8px;';
                    errMsg.textContent = error.message;
                    errWrap.append(errIcon, errTitle, errMsg);
                    body.appendChild(errWrap);
                }
            }

            async function deleteReport(startDate, endDate) {
                if (!confirm(`리포트를 삭제하시겠습니까?\n기간: ${startDate} ~ ${endDate}`)) {
                    return;
                }

                try {
                    const response = await fetchRetry(
                        `${API_PREFIX}/reports/${reportState.branchId}?start_date=${startDate}&end_date=${endDate}`,
                        { method: 'DELETE' }
                    );
                    const result = await response.json();

                    if (result.success) {
                        showToast('리포트가 삭제되었습니다.', 'success');
                        // 목록 새로고침
                        const listResponse = await fetchRetry(`${API_PREFIX}/reports/${reportState.branchId}/list?limit=5`);
                        const listResult = await listResponse.json();
                        if (listResult.success && listResult.data && listResult.data.length > 0) {
                            renderReportList(listResult.data);
                        } else {
                            renderReportPeriodSelection();
                        }
                    } else {
                        throw new Error(result.detail || '삭제 실패');
                    }
                } catch (error) {
                    console.error('Report delete error:', error);
                    showToast(`리포트 삭제 실패: ${error.message}`, 'error');
                }
            }

            // 폴링 취소용 AbortController (전역 스코프)
            let reportPollingController = null;
            // 시뮬레이션 프로그레스 타이머
            let reportCurrentProgress = 0;
            // 현재 진행 중인 작업 ID (백엔드 취소용)
            let reportActiveJobId = null;

            function closeReportModal() {
                const modal = getElement('report-modal');
                if (modal) {
                    modal.style.display = 'none';
                }
                reportState.reportData = null;

                // 시뮬레이션 타이머 정리
                setReportProgress(0);

                // 진행 중인 백엔드 작업 취소
                if (reportActiveJobId && reportState.branchId) {
                    fetch(`${API_PREFIX}/reports/${reportState.branchId}/job/${reportActiveJobId}`, {
                        method: 'DELETE'
                    }).catch(function () { });
                    reportActiveJobId = null;
                }

                // 진행 중인 폴링 취소
                if (reportPollingController) {
                    reportPollingController.abort();
                    reportPollingController = null;
                }
            }

            function formatReportDate(date) {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                return `${year}-${month}-${day}`;
            }

            function setReportPeriod(months) {
                const today = new Date();
                let startDate;

                if (months === 'all') {
                    // 전체 기간: 2020년 1월 1일부터
                    startDate = new Date(2020, 0, 1);
                } else {
                    startDate = new Date(today);
                    startDate.setMonth(today.getMonth() - months);
                }

                reportState.startDate = formatReportDate(startDate);
                reportState.endDate = formatReportDate(today);

                // UI 업데이트
                const startInput = getElement('report-start-date');
                const endInput = getElement('report-end-date');
                if (startInput) startInput.value = reportState.startDate;
                if (endInput) endInput.value = reportState.endDate;

                // 활성 버튼 표시
                document.querySelectorAll('.period-preset-btn').forEach(btn => {
                    btn.classList.remove('active');
                });
                document.querySelector(`.period-preset-btn[data-months="${months}"]`)?.classList.add('active');

                // 캐시된 리뷰 수로 info bar + selected_count 업데이트
                if (reviewCountCache) {
                    const key = months === 'all' ? 'all' : `${months}m`;
                    const count = reviewCountCache.period_counts[key];
                    if (count !== undefined) {
                        reviewCountCache.selected_count = count;
                        updateReviewCountInfoBar(count);
                    }
                }
            }

            function renderReportPeriodSelection() {
                const body = getElement('report-modal-body');
                if (!body) return;

                // 헤더 버튼들 숨기기
                ['header-back-btn', 'header-regen-btn', 'header-pdf-btn'].forEach(id => {
                    const btn = document.getElementById(id);
                    if (btn) btn.style.display = 'none';
                });

                // DOM API로 구성
                const container = document.createElement('div');

                // 기간 선택 섹션
                const periodSection = document.createElement('div');
                periodSection.className = 'period-selection';

                const label = document.createElement('label');
                label.textContent = '분석 기간을 선택하세요';
                periodSection.appendChild(label);

                // 프리셋 버튼들
                const presets = document.createElement('div');
                presets.className = 'period-presets';
                const presetData = [
                    { months: '1', label: '최근 1개월', countId: 'count-1m', active: true },
                    { months: '3', label: '최근 3개월', countId: 'count-3m' },
                    { months: '6', label: '최근 6개월', countId: 'count-6m' },
                    { months: '12', label: '최근 1년', countId: 'count-12m' },
                    { months: 'all', label: '전체', countId: 'count-all' },
                ];
                presetData.forEach(p => {
                    const btn = document.createElement('button');
                    btn.className = 'period-preset-btn' + (p.active ? ' active' : '');
                    btn.dataset.months = p.months;
                    btn.textContent = p.label;
                    const badge = document.createElement('span');
                    badge.className = 'period-count-badge';
                    badge.id = p.countId;
                    btn.appendChild(badge);
                    btn.addEventListener('click', () => window.dashboardHandlers.setReportPeriod(p.months === 'all' ? 'all' : Number(p.months)));
                    presets.appendChild(btn);
                });
                periodSection.appendChild(presets);

                // 날짜 입력
                const dateRange = document.createElement('div');
                dateRange.className = 'date-range-inputs';
                const startInput = document.createElement('input');
                startInput.type = 'date';
                startInput.id = 'report-start-date';
                startInput.value = reportState.startDate;
                startInput.addEventListener('change', () => window.dashboardHandlers.onReportDateChange());
                const sep = document.createElement('span');
                sep.textContent = '~';
                const endInput = document.createElement('input');
                endInput.type = 'date';
                endInput.id = 'report-end-date';
                endInput.value = reportState.endDate;
                endInput.addEventListener('change', () => window.dashboardHandlers.onReportDateChange());
                dateRange.appendChild(startInput);
                dateRange.appendChild(sep);
                dateRange.appendChild(endInput);
                periodSection.appendChild(dateRange);

                container.appendChild(periodSection);

                // 리뷰 수 info bar
                const infoBar = document.createElement('div');
                infoBar.className = 'review-count-info loading';
                infoBar.id = 'review-count-info';
                infoBar.textContent = '리뷰 수 확인 중...';
                container.appendChild(infoBar);

                // 프리셋 선택 (고급 설정 위에 표시)
                buildPresetSelector(container);

                // 고급 설정 토글
                const toggleBtn = document.createElement('button');
                toggleBtn.className = 'settings-toggle';
                toggleBtn.type = 'button';
                const toggleLabel = document.createElement('span');
                toggleLabel.textContent = '고급 설정';
                const toggleArrow = document.createElement('span');
                toggleArrow.className = 'toggle-arrow';
                toggleArrow.textContent = '\u25BC';
                toggleBtn.appendChild(toggleLabel);
                toggleBtn.appendChild(toggleArrow);

                const settingsPanel = document.createElement('div');
                settingsPanel.className = 'settings-panel';
                settingsPanel.id = 'report-settings-panel';

                toggleBtn.addEventListener('click', () => {
                    toggleBtn.classList.toggle('open');
                    settingsPanel.classList.toggle('open');
                });

                container.appendChild(toggleBtn);

                // 설정 섹션 빌드
                buildOutputSettings(settingsPanel);
                buildDataSettings(settingsPanel);
                buildPromptSettings(settingsPanel);
                container.appendChild(settingsPanel);

                // 생성 버튼
                const genBtn = document.createElement('button');
                genBtn.className = 'btn-generate-report';
                genBtn.textContent = '리포트 생성하기';
                genBtn.addEventListener('click', () => window.dashboardHandlers.checkReviewCount());
                container.appendChild(genBtn);

                body.replaceChildren(container);

                fetchReviewCounts();
            }

            // ============================================================
            // Report Settings Builders (DOM API only)
            // ============================================================

            function buildSettingsCheckbox(parent, label, configPath, configKey) {
                const row = document.createElement('label');
                row.className = 'settings-checkbox-row';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = reportState.config[configPath][configKey];
                cb.addEventListener('change', () => {
                    reportState.config[configPath][configKey] = cb.checked;
                });
                const span = document.createElement('span');
                span.textContent = label;
                row.appendChild(cb);
                row.appendChild(span);
                parent.appendChild(row);
            }

            function buildSettingsSlider(parent, label, configPath, configKey, min, max, step, unit) {
                const row = document.createElement('div');
                row.className = 'settings-slider-row';
                const lbl = document.createElement('span');
                lbl.textContent = label;
                lbl.style.minWidth = '90px';
                const slider = document.createElement('input');
                slider.type = 'range';
                slider.min = String(min);
                slider.max = String(max);
                slider.step = String(step);
                slider.value = String(reportState.config[configPath][configKey]);
                const valSpan = document.createElement('span');
                valSpan.className = 'slider-value';
                valSpan.textContent = slider.value + (unit || '');
                slider.addEventListener('input', () => {
                    const val = configKey === 'temperature' ? parseFloat(slider.value) : parseInt(slider.value, 10);
                    reportState.config[configPath][configKey] = val;
                    valSpan.textContent = slider.value + (unit || '');
                });
                row.appendChild(lbl);
                row.appendChild(slider);
                row.appendChild(valSpan);
                parent.appendChild(row);
            }

            function buildSettingsSelect(parent, label, configPath, configKey, options) {
                const row = document.createElement('div');
                row.className = 'settings-select-row';
                const lbl = document.createElement('span');
                lbl.textContent = label;
                lbl.style.minWidth = '90px';
                const sel = document.createElement('select');
                options.forEach(opt => {
                    const o = document.createElement('option');
                    o.value = opt.value;
                    o.textContent = opt.label;
                    if (opt.value === reportState.config[configPath][configKey]) o.selected = true;
                    sel.appendChild(o);
                });
                sel.addEventListener('change', () => {
                    reportState.config[configPath][configKey] = sel.value;
                });
                row.appendChild(lbl);
                row.appendChild(sel);
                parent.appendChild(row);
            }

            function buildOutputSettings(panel) {
                const section = document.createElement('div');
                section.className = 'settings-section';
                const title = document.createElement('div');
                title.className = 'settings-section-title';
                title.textContent = '출력 섹션';
                section.appendChild(title);

                buildSettingsCheckbox(section, '기간 요약', 'output', 'include_period_summary');
                buildSettingsCheckbox(section, '업체 평가', 'output', 'include_affiliate_eval');
                buildSettingsCheckbox(section, '차량 평가', 'output', 'include_vehicle_eval');
                buildSettingsCheckbox(section, '벤치마크', 'output', 'include_benchmark');
                buildSettingsSlider(section, '요약 분량', 'output', 'summary_max_length', 150, 1000, 50, '자');
                buildSettingsSlider(section, '평가 분량', 'output', 'eval_max_length', 100, 400, 50, '자');

                panel.appendChild(section);
            }

            function buildDataSettings(panel) {
                const section = document.createElement('div');
                section.className = 'settings-section';
                const title = document.createElement('div');
                title.className = 'settings-section-title';
                title.textContent = '데이터 범위';
                section.appendChild(title);

                buildSettingsCheckbox(section, '태그 분석 포함', 'data', 'include_tags');
                buildSettingsCheckbox(section, '차량 분석 포함', 'data', 'include_vehicles');
                buildSettingsCheckbox(section, '샘플 리뷰 포함', 'data', 'include_sample_reviews');
                buildSettingsSlider(section, '샘플 리뷰 수', 'data', 'sample_review_count', 5, 20, 1, '건');

                panel.appendChild(section);
            }

            const DETAIL_LEVEL_DEFAULTS = {
                brief: { summary: 150, eval: 100 },
                standard: { summary: 300, eval: 150 },
                detailed: { summary: 600, eval: 250 },
            };

            const AIRPORT_KEYWORDS = ['공항', '인천공항', '김포공항', '제주공항', '김해공항', '대구공항'];
            const TOURIST_KEYWORDS = ['제주', '부산', '강릉', '속초', '여수', '경주', '전주'];

            function detectBranchType(branchName) {
                if (!branchName) return null;
                const lower = branchName.toLowerCase();
                for (const kw of AIRPORT_KEYWORDS) { if (lower.includes(kw)) return 'airport'; }
                for (const kw of TOURIST_KEYWORDS) { if (lower.includes(kw)) return 'tourist'; }
                return 'city';
            }

            async function fetchPresets(branchType) {
                try {
                    const qs = branchType ? '?branch_type=' + encodeURIComponent(branchType) : '';
                    const resp = await fetchRetry(API_PREFIX + '/presets' + qs);
                    const json = await resp.json();
                    if (json.success) { presetCache = json.data; return json.data; }
                } catch (e) { console.error('Preset fetch error:', e); }
                return [];
            }

            function applyPreset(preset) {
                if (!preset) return;
                const p = reportState.config.prompt;
                p.analysis_perspective = preset.analysis_perspective || 'operational';
                p.tone = preset.tone || 'analytical';
                p.detail_level = preset.detail_level || 'standard';
                p.focus_areas = Array.isArray(preset.focus_areas) ? [...preset.focus_areas] : [];
                p.custom_instruction = preset.custom_instruction || '';
                p.temperature = typeof preset.temperature === 'number' ? preset.temperature : 0.5;
                p.preset_id = preset.id || null;

                const dl = DETAIL_LEVEL_DEFAULTS[p.detail_level] || DETAIL_LEVEL_DEFAULTS.standard;
                reportState.config.output.summary_max_length = preset.summary_max_length || dl.summary;
                reportState.config.output.eval_max_length = preset.eval_max_length || dl.eval;
            }

            function buildPresetSelector(panel) {
                const section = document.createElement('div');
                section.className = 'preset-section';
                const label = document.createElement('div');
                label.style.cssText = 'font-size: 13px; font-weight: 500; margin-bottom: 2px;';
                label.textContent = '프리셋 선택';
                section.appendChild(label);

                const sel = document.createElement('select');
                sel.id = 'preset-selector';
                const defaultOpt = document.createElement('option');
                defaultOpt.value = '';
                defaultOpt.textContent = '직접 설정';
                sel.appendChild(defaultOpt);
                section.appendChild(sel);

                const detectedType = detectBranchType(reportState.branchName);
                fetchPresets(detectedType).then(presets => {
                    presets.forEach(p => {
                        const o = document.createElement('option');
                        o.value = String(p.id);
                        let text = p.name;
                        if (p.branch_type && p.branch_type === detectedType) {
                            text += ' [추천]';
                        }
                        o.textContent = text;
                        sel.appendChild(o);
                    });
                });

                sel.addEventListener('change', () => {
                    const selectedId = parseInt(sel.value, 10);
                    if (!selectedId || !presetCache) {
                        reportState.config.prompt.preset_id = null;
                        return;
                    }
                    const preset = presetCache.find(p => p.id === selectedId);
                    if (preset) {
                        applyPreset(preset);
                        // 설정 패널 UI 새로고침
                        const settingsPanel = document.getElementById('report-settings-panel');
                        if (settingsPanel) {
                            settingsPanel.textContent = '';
                            buildOutputSettings(settingsPanel);
                            buildDataSettings(settingsPanel);
                            buildPromptSettings(settingsPanel);
                        }
                    }
                });

                panel.appendChild(section);
            }

            function buildPromptSettings(panel) {
                const section = document.createElement('div');
                section.className = 'settings-section';
                const title = document.createElement('div');
                title.className = 'settings-section-title';
                title.textContent = '분석 설정';
                section.appendChild(title);

                buildSettingsSelect(section, '분석 관점', 'prompt', 'analysis_perspective', [
                    { value: 'operational', label: '운영 관점' },
                    { value: 'marketing', label: '마케팅 관점' },
                    { value: 'executive', label: '경영진 보고' },
                    { value: 'customer_service', label: 'CS 품질 개선' },
                    { value: 'investor', label: '투자/사업성과' },
                    { value: 'comparative', label: '비교 분석' },
                ]);
                buildSettingsSelect(section, '톤', 'prompt', 'tone', [
                    { value: 'analytical', label: '분석적' },
                    { value: 'friendly', label: '친근한' },
                    { value: 'formal', label: '격식체' },
                    { value: 'concise', label: '간결한' },
                    { value: 'data_driven', label: '데이터 중심' },
                    { value: 'narrative', label: '서술형' },
                ]);

                // detail_level 셀렉트
                const dlRow = document.createElement('div');
                dlRow.className = 'settings-select-row';
                const dlLabel = document.createElement('span');
                dlLabel.textContent = '상세 수준';
                dlLabel.style.minWidth = '90px';
                const dlSel = document.createElement('select');
                [
                    { value: 'brief', label: '간략 (150~250자)' },
                    { value: 'standard', label: '표준 (400~600자)' },
                    { value: 'detailed', label: '상세 (600~1000자)' },
                ].forEach(opt => {
                    const o = document.createElement('option');
                    o.value = opt.value;
                    o.textContent = opt.label;
                    if (opt.value === reportState.config.prompt.detail_level) o.selected = true;
                    dlSel.appendChild(o);
                });
                dlSel.addEventListener('change', () => {
                    reportState.config.prompt.detail_level = dlSel.value;
                    const defaults = DETAIL_LEVEL_DEFAULTS[dlSel.value];
                    if (defaults) {
                        reportState.config.output.summary_max_length = defaults.summary;
                        reportState.config.output.eval_max_length = defaults.eval;
                        // 슬라이더 업데이트
                        const settingsPanel = document.getElementById('report-settings-panel');
                        if (settingsPanel) {
                            settingsPanel.textContent = '';
                            buildOutputSettings(settingsPanel);
                            buildDataSettings(settingsPanel);
                            buildPromptSettings(settingsPanel);
                        }
                    }
                });
                dlRow.appendChild(dlLabel);
                dlRow.appendChild(dlSel);
                section.appendChild(dlRow);

                // focus_areas 멀티 체크박스
                const faLabel = document.createElement('div');
                faLabel.style.cssText = 'font-size: 13px; margin-top: 10px; margin-bottom: 4px;';
                faLabel.textContent = '집중 분석 카테고리';
                section.appendChild(faLabel);

                const faGrid = document.createElement('div');
                faGrid.className = 'settings-focus-grid';
                const FOCUS_AREAS = [
                    '직원친절', '외관', '가격', '청결',
                    '사고 처리', '주유비', '배달',
                ];
                FOCUS_AREAS.forEach(area => {
                    const item = document.createElement('label');
                    item.className = 'settings-focus-item';
                    const cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.checked = reportState.config.prompt.focus_areas.includes(area);
                    cb.addEventListener('change', () => {
                        const arr = reportState.config.prompt.focus_areas;
                        if (cb.checked) {
                            if (!arr.includes(area)) arr.push(area);
                        } else {
                            const idx = arr.indexOf(area);
                            if (idx !== -1) arr.splice(idx, 1);
                        }
                    });
                    const span = document.createElement('span');
                    span.textContent = area;
                    item.appendChild(cb);
                    item.appendChild(span);
                    faGrid.appendChild(item);
                });
                section.appendChild(faGrid);

                buildSettingsSlider(section, 'Temperature', 'prompt', 'temperature', 0.0, 1.0, 0.1, '');

                // 커스텀 지시사항 textarea
                const taRow = document.createElement('div');
                taRow.className = 'settings-textarea-row';
                const taLabel = document.createElement('div');
                taLabel.textContent = '커스텀 지시사항';
                taLabel.style.fontSize = '13px';
                taLabel.style.marginBottom = '6px';
                const ta = document.createElement('textarea');
                ta.placeholder = '추가 분석 요청사항을 입력하세요 (최대 500자)';
                ta.maxLength = 500;
                ta.value = reportState.config.prompt.custom_instruction;
                const charCount = document.createElement('div');
                charCount.className = 'char-count';
                charCount.textContent = ta.value.length + '/500';
                ta.addEventListener('input', () => {
                    reportState.config.prompt.custom_instruction = ta.value;
                    charCount.textContent = ta.value.length + '/500';
                });
                taRow.appendChild(taLabel);
                taRow.appendChild(ta);
                taRow.appendChild(charCount);
                section.appendChild(taRow);

                panel.appendChild(section);
            }

            function onReportDateChange() {
                const startInput = getElement('report-start-date');
                const endInput = getElement('report-end-date');
                if (startInput) reportState.startDate = startInput.value;
                if (endInput) reportState.endDate = endInput.value;

                // 프리셋 버튼 비활성화
                document.querySelectorAll('.period-preset-btn').forEach(btn => {
                    btn.classList.remove('active');
                });

                // 커스텀 날짜에 대해 리뷰 수 다시 조회
                fetchReviewCounts();
            }

            async function fetchReviewCounts() {
                const infoBar = document.getElementById('review-count-info');
                try {
                    const resp = await fetchRetry(
                        `${API_PREFIX}/reports/${reportState.branchId}/review-count?start_date=${reportState.startDate}&end_date=${reportState.endDate}`
                    );
                    if (!resp.ok) {
                        if (infoBar) infoBar.style.display = 'none';
                        reviewCountCache = null;
                        return;
                    }
                    const json = await resp.json();
                    reviewCountCache = json.data;

                    // 프리셋 버튼에 count badge 표시
                    const periodKeys = { '1': '1m', '3': '3m', '6': '6m', '12': '12m', 'all': 'all' };
                    Object.entries(periodKeys).forEach(([months, key]) => {
                        const badge = document.getElementById('count-' + key);
                        const btn = document.querySelector(`.period-preset-btn[data-months="${months}"]`);
                        if (badge && reviewCountCache.period_counts[key] !== undefined) {
                            const count = reviewCountCache.period_counts[key];
                            badge.textContent = ` (${count}건)`;
                            if (btn) {
                                btn.classList.add('has-count');
                                if (count >= REPORT_REVIEW_THRESHOLD) {
                                    btn.classList.add('sufficient');
                                } else {
                                    btn.classList.remove('sufficient');
                                }
                            }
                        }
                    });

                    // 선택 기간 리뷰가 threshold 미만이면 권장 기간으로 자동 전환
                    const threshold = reviewCountCache.threshold || REPORT_REVIEW_THRESHOLD;
                    if (reviewCountCache.selected_count < threshold && reviewCountCache.recommended_period) {
                        const periodMap = { '1m': 1, '3m': 3, '6m': 6, '12m': 12, 'all': 'all' };
                        const months = periodMap[reviewCountCache.recommended_period];
                        if (months !== undefined) {
                            setReportPeriod(months);
                            const newCount = reviewCountCache.period_counts[reviewCountCache.recommended_period] || 0;
                            updateReviewCountInfoBar(newCount);
                            showToast(`선택 기간에 리뷰가 없어 리뷰가 있는 기간으로 자동 전환했습니다.`, 'info');
                            return;
                        }
                    }

                    // info bar 업데이트
                    updateReviewCountInfoBar(reviewCountCache.selected_count);
                } catch (e) {
                    if (infoBar) infoBar.style.display = 'none';
                    reviewCountCache = null;
                }
            }

            function updateReviewCountInfoBar(count) {
                const infoBar = document.getElementById('review-count-info');
                if (!infoBar) return;

                infoBar.style.display = 'flex';
                infoBar.className = 'review-count-info';

                if (count >= REPORT_REVIEW_THRESHOLD) {
                    infoBar.classList.add('sufficient');
                    infoBar.textContent = '';
                    const icon = document.createElement('span');
                    icon.textContent = '\u2713';
                    const text = document.createElement('span');
                    text.textContent = '선택 기간 리뷰 ';
                    const num = document.createElement('span');
                    num.className = 'count-number';
                    num.textContent = `${count}건`;
                    infoBar.appendChild(icon);
                    infoBar.appendChild(text);
                    infoBar.appendChild(num);
                } else {
                    infoBar.classList.add('insufficient');
                    infoBar.textContent = '';
                    const icon = document.createElement('span');
                    icon.textContent = '\u26A0';
                    const text = document.createElement('span');
                    text.textContent = '선택 기간 리뷰 ';
                    const num = document.createElement('span');
                    num.className = 'count-number';
                    num.textContent = `${count}건`;
                    const hint = document.createElement('span');
                    hint.textContent = ` (권장: ${REPORT_REVIEW_THRESHOLD}건 이상)`;
                    infoBar.appendChild(icon);
                    infoBar.appendChild(text);
                    infoBar.appendChild(num);
                    infoBar.appendChild(hint);
                }
            }

            function checkReviewCount() {
                // 캐시된 데이터로 리뷰 수 확인
                if (reviewCountCache && reviewCountCache.selected_count < REPORT_REVIEW_THRESHOLD) {
                    const count = reviewCountCache.selected_count;
                    if (!confirm(`선택 기간의 리뷰가 ${count}건입니다.\n권장 기준(${REPORT_REVIEW_THRESHOLD}건) 미만이면 리포트 품질이 낮을 수 있습니다.\n\n그대로 생성하시겠습니까?`)) {
                        return;
                    }
                }
                generateReport();
            }

            async function generateReport() {
                const body = getElement('report-modal-body');
                if (!body) return;

                // 이전 폴링 취소
                if (reportPollingController) {
                    reportPollingController.abort();
                }
                reportPollingController = new AbortController();

                // 로딩 표시 + 시뮬레이션 프로그레스 시작
                showReportLoadingUI(body, '지점 데이터를 수집하고 있습니다...');
                startReportProgress();

                try {
                    // 1단계: 비동기 작업 제출 (즉시 반환)
                    const submitResponse = await fetchRetry(`${API_PREFIX}/reports/${reportState.branchId}/generate/async`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            start_date: reportState.startDate,
                            end_date: reportState.endDate,
                            output_config: reportState.config.output,
                            data_config: reportState.config.data,
                            prompt_config: reportState.config.prompt,
                        }),
                        signal: reportPollingController.signal
                    });

                    if (!submitResponse.ok) {
                        const error = await submitResponse.json();
                        throw new Error(error.detail || '리포트 생성 요청 실패');
                    }

                    const submitResult = await submitResponse.json();
                    if (!submitResult.success || !submitResult.data?.job_id) {
                        throw new Error(submitResult.error || '작업 ID를 받지 못했습니다');
                    }

                    const jobId = submitResult.data.job_id;
                    reportActiveJobId = jobId;

                    // 2단계: 폴링으로 진행 상태 확인 (최대 2분)
                    await pollReportJob(jobId, true);
                    reportActiveJobId = null;

                } catch (error) {
                    setReportProgress(0);
                    reportActiveJobId = null;
                    if (error.name === 'AbortError') {
                        console.log('Report generation aborted');
                        return;
                    }
                    console.error('Report generation error:', error);
                    showReportErrorUI(body, '리포트 생성 실패', error.message, 'renderReportPeriodSelection');
                }
            }

            function showReportLoadingUI(container, message) {
                // 로딩 컨테이너 생성
                const loadingDiv = document.createElement('div');
                loadingDiv.className = 'report-loading';

                const spinner = document.createElement('div');
                spinner.className = 'spinner';
                loadingDiv.appendChild(spinner);

                const textDiv = document.createElement('div');
                textDiv.className = 'report-loading-text';
                textDiv.id = 'report-loading-message';
                textDiv.textContent = message;
                loadingDiv.appendChild(textDiv);

                // 프로그레스 바
                const progressWrap = document.createElement('div');
                progressWrap.className = 'report-progress-wrap';
                progressWrap.id = 'report-progress-wrap';

                const progressBar = document.createElement('div');
                progressBar.className = 'report-progress-bar';

                const progressFill = document.createElement('div');
                progressFill.className = 'report-progress-fill';
                progressFill.id = 'report-progress-fill';
                progressBar.appendChild(progressFill);
                progressWrap.appendChild(progressBar);

                const progressInfo = document.createElement('div');
                progressInfo.className = 'report-progress-info';

                const progressStep = document.createElement('span');
                progressStep.id = 'report-progress-step';
                progressStep.textContent = '';
                progressInfo.appendChild(progressStep);

                const progressPercent = document.createElement('span');
                progressPercent.className = 'report-progress-percent';
                progressPercent.id = 'report-progress-percent';
                progressPercent.textContent = '0%';
                progressInfo.appendChild(progressPercent);

                progressWrap.appendChild(progressInfo);
                loadingDiv.appendChild(progressWrap);

                container.replaceChildren(loadingDiv);
            }

            function updateReportProgressUI(progress) {
                const wrap = document.getElementById('report-progress-wrap');
                const fill = document.getElementById('report-progress-fill');
                const percent = document.getElementById('report-progress-percent');
                const step = document.getElementById('report-progress-step');
                const msg = document.getElementById('report-loading-message');
                if (!wrap || !fill) return;

                const rounded = Math.round(progress);
                fill.style.width = rounded + '%';
                if (percent) percent.textContent = rounded + '%';

                // 단계별 메시지 매핑
                let stepText = '';
                let loadingText = '';
                if (rounded <= 20) {
                    stepText = '데이터 수집';
                    loadingText = '지점 데이터를 수집하고 있습니다...';
                } else if (rounded <= 50) {
                    stepText = '태그 분석';
                    loadingText = '리뷰 태그를 분석하고 있습니다...';
                } else if (rounded <= 90) {
                    stepText = 'AI 분석';
                    loadingText = 'AI가 리포트를 작성하고 있습니다...';
                } else {
                    stepText = '리포트 저장';
                    loadingText = '거의 완료되었습니다...';
                }
                if (step) step.textContent = stepText;
                if (msg) msg.textContent = loadingText;
            }

            function startReportProgress() {
                reportCurrentProgress = 0;
                updateReportProgressUI(0);
            }

            function setReportProgress(progress) {
                reportCurrentProgress = progress;
                updateReportProgressUI(progress);
            }

            function showReportErrorUI(container, title, message, retryHandler) {
                const errorDiv = document.createElement('div');
                errorDiv.style.cssText = 'text-align: center; padding: 40px;';

                const icon = document.createElement('div');
                icon.style.cssText = 'font-size: 48px; margin-bottom: 16px;';
                icon.textContent = '\u274C';
                errorDiv.appendChild(icon);

                const titleDiv = document.createElement('div');
                titleDiv.style.cssText = 'font-size: 16px; color: var(--grey-2); margin-bottom: 8px;';
                titleDiv.textContent = title;
                errorDiv.appendChild(titleDiv);

                const msgDiv = document.createElement('div');
                msgDiv.style.cssText = 'font-size: 14px; color: var(--grey-5); margin-bottom: 24px;';
                msgDiv.textContent = message;
                errorDiv.appendChild(msgDiv);

                const btn = document.createElement('button');
                btn.className = 'btn btn-secondary';
                btn.textContent = retryHandler === 'renderReportPeriodSelection' ? '다시 시도' : '돌아가기';
                btn.onclick = () => window.dashboardHandlers[retryHandler](retryHandler === 'renderReportContent' ? reportState.reportData : undefined, false);
                errorDiv.appendChild(btn);

                container.replaceChildren(errorDiv);
            }

            async function pollReportJob(jobId, isNew) {
                const maxPolls = CONFIG.POLLING.MAX_POLLS;
                let pollCount = 0;

                while (pollCount < maxPolls) {
                    // 폴링 취소 확인
                    if (reportPollingController && reportPollingController.signal.aborted) {
                        console.log('Report polling cancelled');
                        return;
                    }

                    const statusResponse = await fetchRetry(`${API_PREFIX}/reports/${reportState.branchId}/job/${jobId}`, {
                        signal: reportPollingController ? reportPollingController.signal : undefined
                    });

                    if (!statusResponse.ok) {
                        throw new Error('작업 상태 조회 실패');
                    }

                    const statusResult = await statusResponse.json();
                    const jobData = statusResult.data;

                    // 서버 진행률 직접 반영 (CSS transition이 부드럽게 처리)
                    if (typeof jobData.progress === 'number' && jobData.progress > 0) {
                        setReportProgress(jobData.progress);
                    }

                    if (jobData.status === 'completed') {
                        reportActiveJobId = null;
                        setReportProgress(100);
                        const reportData = await fetchReportData();
                        if (reportData) {
                            reportState.reportData = reportData;
                            renderReportContent(reportData, isNew);
                        }
                        return;
                    } else if (jobData.status === 'failed') {
                        reportActiveJobId = null;
                        throw new Error(jobData.error_message || '리포트 생성 실패');
                    }

                    // 2초 대기 후 다음 폴링
                    await new Promise(resolve => setTimeout(resolve, CONFIG.POLLING.INTERVAL_MS));
                    pollCount++;
                }

                // 타임아웃
                throw new Error('리포트 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.');
            }

            async function fetchReportData() {
                // 생성된 리포트 데이터 가져오기
                const response = await fetchRetry(
                    `${API_PREFIX}/reports/${reportState.branchId}?start_date=${reportState.startDate}&end_date=${reportState.endDate}`,
                    { signal: reportPollingController ? reportPollingController.signal : undefined }
                );

                if (!response.ok) {
                    throw new Error('리포트 데이터 조회 실패');
                }

                const result = await response.json();
                return result.success ? result.data : null;
            }

            async function regenerateReport() {
                const body = getElement('report-modal-body');
                if (!body) return;

                // 이전 폴링 취소
                if (reportPollingController) {
                    reportPollingController.abort();
                }
                reportPollingController = new AbortController();

                // 로딩 표시 + 시뮬레이션 프로그레스 시작
                showReportLoadingUI(body, '지점 데이터를 수집하고 있습니다...');
                startReportProgress();

                try {
                    // 비동기 작업 제출 (/generate/async는 regenerate와 동일한 로직 사용)
                    const submitResponse = await fetchRetry(`${API_PREFIX}/reports/${reportState.branchId}/generate/async`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            start_date: reportState.startDate,
                            end_date: reportState.endDate,
                            output_config: reportState.config.output,
                            data_config: reportState.config.data,
                            prompt_config: reportState.config.prompt,
                        }),
                        signal: reportPollingController.signal
                    });

                    if (!submitResponse.ok) {
                        const error = await submitResponse.json();
                        throw new Error(error.detail || '리포트 재생성 요청 실패');
                    }

                    const submitResult = await submitResponse.json();
                    if (!submitResult.success || !submitResult.data?.job_id) {
                        throw new Error(submitResult.error || '작업 ID를 받지 못했습니다');
                    }

                    const jobId = submitResult.data.job_id;
                    reportActiveJobId = jobId;

                    // 폴링으로 진행 상태 확인
                    await pollReportJob(jobId, true);
                    reportActiveJobId = null;

                } catch (error) {
                    setReportProgress(0);
                    reportActiveJobId = null;
                    if (error.name === 'AbortError') {
                        console.log('Report regeneration aborted');
                        return;
                    }
                    console.error('Report regeneration error:', error);
                    showReportErrorUI(body, '리포트 재생성 실패', error.message, 'renderReportContent');
                }
            }

            function renderReportContent(data, isNew = true) {
                const body = getElement('report-modal-body');
                if (!body) return;

                const hasNewFormat = Array.isArray(data.top_tags_detail);
                if (!hasNewFormat) {
                    renderLegacyReportContent(data, isNew);
                    return;
                }

                // 헤더 버튼들 표시
                const headerBackBtn = document.getElementById('header-back-btn');
                const headerRegenBtn = document.getElementById('header-regen-btn');
                const headerPdfBtn = document.getElementById('header-pdf-btn');
                if (headerBackBtn) {
                    headerBackBtn.style.display = 'block';
                    headerBackBtn.onclick = () => window.dashboardHandlers.openReportModal(data.branch_id, data.branch_name || '', data.affiliate_name || '');
                }
                if (headerRegenBtn) headerRegenBtn.style.display = 'block';
                if (headerPdfBtn) headerPdfBtn.style.display = 'block';

                // 태그 리스트 생성 헬퍼
                const TAG_SENTENCE_MAP = {
                    '직원친절': { positive: '직원이 친절함', negative: '직원이 불친절함' },
                    '사고 처리': { positive: '사고 처리를 잘해줌', negative: '사고 처리를 잘 못해줌' },
                    '배달': { positive: '배달 서비스가 우수함', negative: '배달 서비스가 미흡함' },
                    '가격': { positive: '가격이 저렴함', negative: '가격이 비쌈' },
                    '주유비': { positive: '주유비 부담 없음', negative: '주유비 부담 있음' },
                    '외관': { positive: '차량 외관이 좋음', negative: '차량 외관이 안좋음' },
                    '청결': { positive: '차량이 청결함', negative: '차량이 불결함' },
                };
                function buildTagListNode(tags, mode) {
                    var frag = document.createDocumentFragment();
                    if (!tags || tags.length === 0) {
                        frag.appendChild(el('div', { style: { color: 'var(--grey-5)', fontSize: '13px' }, textContent: '데이터 부족' }));
                        return frag;
                    }
                    var color = mode === 'negative' ? '#ef4444' : '#10b981';
                    var sentiment = mode === 'negative' ? 'negative' : 'positive';
                    tags.forEach(function (t, i) {
                        var sentence = TAG_SENTENCE_MAP[t.tag_name]?.[sentiment] || t.tag_name;
                        frag.appendChild(el('div', { style: { color: 'var(--grey-3)', fontSize: '13px', padding: '3px 0' } }, [
                            (i + 1) + '. ' + sentence + ' ',
                            el('span', { style: { color: color }, textContent: t.count + '건' })
                        ]));
                    });
                    return frag;
                }

                // 차량 리스트 생성 헬퍼
                function buildVehicleListNode(vehicles, mode) {
                    var frag = document.createDocumentFragment();
                    if (!vehicles || vehicles.length === 0) {
                        frag.appendChild(el('div', { style: { color: 'var(--grey-5)', fontSize: '13px' }, textContent: '데이터 부족' }));
                        return frag;
                    }
                    var tagColor = mode === 'disliked' ? '#ef4444' : '#10b981';
                    vehicles.forEach(function (v, i) {
                        var children = [(i + 1) + '. ' + v.model];
                        var vTags = (v.tags || []).slice(0, 3);
                        if (vTags.length > 0) {
                            children.push(' ');
                            vTags.forEach(function (t, ti) {
                                if (ti > 0) children.push(', ');
                                children.push(el('span', { style: { color: tagColor }, textContent: t }));
                            });
                        }
                        frag.appendChild(el('div', { style: { color: 'var(--grey-3)', fontSize: '13px', padding: '3px 0' } }, children));
                    });
                    return frag;
                }

                const aff = data.affiliate_evaluation || {};
                const veh = data.vehicle_evaluation || {};

                body.textContent = '';

                // 분석 기간
                body.appendChild(el('div', { style: { marginBottom: '16px' } }, [
                    el('span', { style: { fontSize: '13px', color: 'var(--grey-5)' }, textContent: '분석 기간: ' + data.period_start + ' ~ ' + data.period_end })
                ]));

                // 섹션 1: 요약
                if (data.period_summary) {
                    var summarySection = el('div', { className: 'report-section' }, [
                        el('div', { className: 'report-section-title', textContent: '요약' }),
                        el('div', { className: 'report-summary-box', textContent: data.period_summary })
                    ]);
                    body.appendChild(summarySection);
                }

                // 섹션 2: 업체 평가
                if (data.affiliate_evaluation) {
                    var affPosBox = el('div', { style: { flex: '1', background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: '8px', padding: '12px' } }, [
                        el('div', { style: { fontWeight: '600', color: '#10b981', marginBottom: '8px', fontSize: '13px' }, textContent: '잘한점' })
                    ]);
                    affPosBox.appendChild(buildTagListNode(aff.top_positive, 'positive'));

                    var affNegBox = el('div', { style: { flex: '1', background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '8px', padding: '12px' } }, [
                        el('div', { style: { fontWeight: '600', color: '#ef4444', marginBottom: '8px', fontSize: '13px' }, textContent: '개선점' })
                    ]);
                    affNegBox.appendChild(buildTagListNode(aff.top_negative, 'negative'));

                    var affSection = el('div', { className: 'report-section' }, [
                        el('div', { className: 'report-section-title', textContent: '업체 평가' }),
                        el('div', { style: { display: 'flex', gap: '16px' } }, [affPosBox, affNegBox])
                    ]);
                    body.appendChild(affSection);
                }

                // 섹션 3: 차량 평가
                if (data.vehicle_evaluation) {
                    var vehLikedBox = el('div', { style: { flex: '1', background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: '8px', padding: '12px' } }, [
                        el('div', { style: { fontWeight: '600', color: '#10b981', marginBottom: '8px', fontSize: '13px' }, textContent: '칭찬 차량' })
                    ]);
                    vehLikedBox.appendChild(buildVehicleListNode(veh.top_liked, 'liked'));

                    var vehDislikedBox = el('div', { style: { flex: '1', background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '8px', padding: '12px' } }, [
                        el('div', { style: { fontWeight: '600', color: '#ef4444', marginBottom: '8px', fontSize: '13px' }, textContent: '불만 차량' })
                    ]);
                    vehDislikedBox.appendChild(buildVehicleListNode(veh.top_disliked, 'disliked'));

                    var vehSection = el('div', { className: 'report-section' }, [
                        el('div', { className: 'report-section-title', textContent: '차량 평가' }),
                        el('div', { style: { display: 'flex', gap: '16px' } }, [vehLikedBox, vehDislikedBox])
                    ]);
                    body.appendChild(vehSection);
                }

                // 섹션 5: 벤치마크
                if (data.benchmark) {
                    var bm = data.benchmark;
                    var bmSection = el('div', { className: 'report-section' }, [
                        el('div', { className: 'report-section-title', textContent: '벤치마크' }),
                        el('div', { style: { display: 'flex', gap: '12px' } }, [
                            el('div', { style: { flex: '1', background: 'var(--grey-8)', borderRadius: '8px', padding: '14px', textAlign: 'center' } }, [
                                el('div', { style: { fontSize: '12px', color: 'var(--grey-5)', marginBottom: '6px' }, textContent: '이 지점' }),
                                el('div', { style: { fontSize: '22px', fontWeight: '700', color: '#f59e0b' }, textContent: bm.branch_rating.toFixed(1) })
                            ]),
                            el('div', { style: { flex: '1', background: 'var(--grey-8)', borderRadius: '8px', padding: '14px', textAlign: 'center' } }, [
                                el('div', { style: { fontSize: '12px', color: 'var(--grey-5)', marginBottom: '6px' }, textContent: (bm.region_name || '지역') + ' 평균' }),
                                el('div', { style: { fontSize: '22px', fontWeight: '700', color: 'var(--grey-3)' }, textContent: bm.regional_avg_rating.toFixed(1) }),
                                el('div', { style: { fontSize: '11px', color: 'var(--grey-5)', marginTop: '2px' }, textContent: '상위 ' + bm.regional_rank_pct + '% (' + bm.total_branches_in_region + '개 지점)' })
                            ]),
                            el('div', { style: { flex: '1', background: 'var(--grey-8)', borderRadius: '8px', padding: '14px', textAlign: 'center' } }, [
                                el('div', { style: { fontSize: '12px', color: 'var(--grey-5)', marginBottom: '6px' }, textContent: '전국 평균' }),
                                el('div', { style: { fontSize: '22px', fontWeight: '700', color: 'var(--grey-3)' }, textContent: bm.national_avg_rating.toFixed(1) }),
                                el('div', { style: { fontSize: '11px', color: 'var(--grey-5)', marginTop: '2px' }, textContent: '상위 ' + bm.national_rank_pct + '% (' + bm.total_branches_national + '개 지점)' })
                            ])
                        ])
                    ]);
                    if (bm.branch_rating > 0) {
                        var isAboveAvg = bm.branch_rating >= bm.regional_avg_rating;
                        var bmMsg = isAboveAvg
                            ? '이 지점은 ' + (bm.region_name || '해당 지역') + ' 평균 이상의 평점을 유지하고 있습니다.'
                            : '이 지점은 ' + (bm.region_name || '해당 지역') + ' 평균보다 낮은 평점이므로, 개선 조치가 필요할 수 있습니다.';
                        bmSection.appendChild(el('div', {
                            style: { marginTop: '12px', background: isAboveAvg ? 'rgba(16,185,129,0.06)' : 'rgba(239,68,68,0.06)', border: '1px solid ' + (isAboveAvg ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'), borderRadius: '8px', padding: '10px 14px', fontSize: '13px', color: 'var(--grey-3)' },
                            textContent: bmMsg
                        }));
                    }
                    body.appendChild(bmSection);
                }

                // 섹션 6: 부정 리뷰 목록
                if (data.negative_reviews && data.negative_reviews.length > 0) {
                    var nrThead = el('thead', {}, [
                        el('tr', {}, [
                            el('th', { style: { textAlign: 'left', padding: '8px 10px', fontSize: '12px', color: 'var(--grey-4)', borderBottom: '2px solid var(--grey-7)' }, textContent: '날짜' }),
                            el('th', { style: { textAlign: 'center', padding: '8px 10px', fontSize: '12px', color: 'var(--grey-4)', borderBottom: '2px solid var(--grey-7)' }, textContent: '평점' }),
                            el('th', { style: { textAlign: 'left', padding: '8px 10px', fontSize: '12px', color: 'var(--grey-4)', borderBottom: '2px solid var(--grey-7)' }, textContent: '리뷰 내용' })
                        ])
                    ]);
                    var nrTbody = el('tbody');
                    data.negative_reviews.forEach(function (r) {
                        nrTbody.appendChild(el('tr', {}, [
                            el('td', { style: { padding: '8px 10px', fontSize: '12px', color: 'var(--grey-4)', borderBottom: '1px solid var(--grey-7)', whiteSpace: 'nowrap' }, textContent: r.review_date || '' }),
                            el('td', { style: { padding: '8px 10px', fontSize: '12px', color: '#ef4444', textAlign: 'center', borderBottom: '1px solid var(--grey-7)' }, textContent: String(r.rating || '') }),
                            el('td', { style: { padding: '8px 10px', fontSize: '12px', color: 'var(--grey-3)', borderBottom: '1px solid var(--grey-7)', lineHeight: '1.5', whiteSpace: 'pre-line' }, textContent: (r.content || '').replace(/<br\s*\/?>/gi, '\n') })
                        ]));
                    });
                    body.appendChild(el('div', { className: 'report-section' }, [
                        el('div', { className: 'report-section-title', textContent: '부정 리뷰 목록' }),
                        el('table', { className: 'report-table', style: { width: '100%', borderCollapse: 'collapse' } }, [nrThead, nrTbody])
                    ]));
                }

                // 하단 (신뢰도 + 생성 정보)
                var footerChildren = [];
                if (data.tag_coverage) {
                    var reliabilityColor = data.tag_coverage.ratio >= 70 ? '#10b981' : data.tag_coverage.ratio >= 40 ? '#f59e0b' : '#ef4444';
                    footerChildren.push(el('div', { style: { marginBottom: '6px' } }, [
                        el('span', { style: { color: 'var(--grey-4)' }, textContent: '분석 신뢰도: ' }),
                        el('span', { style: { color: reliabilityColor, fontWeight: '600' }, textContent: data.tag_coverage.ratio + '%' }),
                        el('span', { style: { color: 'var(--grey-5)' }, textContent: ' (태그 분석 ' + data.tag_coverage.tagged_reviews + '건 / 전체 ' + data.tag_coverage.total_reviews + '건)' })
                    ]));
                }
                footerChildren.push('Generated by Carmore AI \u00B7 ' + (data.generated_at || new Date().toLocaleString('ko-KR')));
                body.appendChild(el('div', { style: { textAlign: 'center', padding: '8px 0', color: 'var(--grey-5)', fontSize: '12px', marginTop: '16px', borderTop: '1px solid var(--grey-7)', paddingTop: '16px' } }, footerChildren));
            }

            function renderLegacyReportContent(data, isNew = true) {
                const body = getElement('report-modal-body');
                if (!body) return;

                // 헤더 버튼들 표시
                const headerBackBtn = document.getElementById('header-back-btn');
                const headerRegenBtn = document.getElementById('header-regen-btn');
                const headerPdfBtn = document.getElementById('header-pdf-btn');
                if (headerBackBtn) {
                    headerBackBtn.style.display = 'block';
                    headerBackBtn.onclick = () => window.dashboardHandlers.openReportModal(data.branch_id, data.branch_name || '', data.affiliate_name || '');
                }
                if (headerRegenBtn) headerRegenBtn.style.display = 'block';
                if (headerPdfBtn) headerPdfBtn.style.display = 'block';

                // 차량별 분석 테이블 body
                var vTbody = el('tbody');
                if (data.vehicle_analysis && data.vehicle_analysis.length > 0) {
                    data.vehicle_analysis.forEach(function (v) {
                        vTbody.appendChild(el('tr', {}, [
                            el('td', { textContent: v.model || '' }),
                            el('td', { style: { textAlign: 'center' }, textContent: v.count + '건' }),
                            el('td', { style: { color: '#10b981' }, textContent: v.top_praise || '-' }),
                            el('td', { style: { color: '#ef4444' }, textContent: v.top_issue || '-' })
                        ]));
                    });
                } else {
                    var emptyTd = el('td', { style: { textAlign: 'center', color: 'var(--grey-5)' }, textContent: '차량별 데이터가 없습니다.' });
                    emptyTd.setAttribute('colspan', '4');
                    vTbody.appendChild(el('tr', {}, [emptyTd]));
                }

                body.textContent = '';
                body.appendChild(el('div', { style: { marginBottom: '16px' } }, [
                    el('span', { style: { fontSize: '13px', color: 'var(--grey-5)' }, textContent: '분석 기간: ' + data.period_start + ' ~ ' + data.period_end })
                ]));
                body.appendChild(el('div', { className: 'report-section' }, [
                    el('div', { className: 'report-section-title', textContent: '기간별 요약 분석' }),
                    el('div', { className: 'report-summary-box', textContent: data.period_summary || '요약 정보가 없습니다.' })
                ]));
                body.appendChild(el('div', { className: 'report-section' }, [
                    el('div', { className: 'report-section-title', textContent: '차량별 평가 분석' }),
                    el('table', { className: 'report-table' }, [
                        el('thead', {}, [
                            el('tr', {}, [
                                el('th', { textContent: '차량 모델' }),
                                el('th', { style: { textAlign: 'center' }, textContent: '리뷰 수' }),
                                el('th', { textContent: '주요 호평' }),
                                el('th', { textContent: '주요 불만' })
                            ])
                        ]),
                        vTbody
                    ])
                ]));
                body.appendChild(el('div', {
                    style: { textAlign: 'center', padding: '8px 0', color: 'var(--grey-5)', fontSize: '12px', marginTop: '16px', borderTop: '1px solid var(--grey-7)', paddingTop: '16px' },
                    textContent: 'Generated by Carmore AI \u00B7 ' + (data.generated_at || new Date().toLocaleString('ko-KR'))
                }));
            }

            function downloadReportPDF() {
                if (!reportState.branchId) {
                    showToast('❌ 리포트 정보가 없습니다.', 'error');
                    return;
                }

                const url = `${API_PREFIX}/reports/${reportState.branchId}/pdf?start_date=${reportState.startDate}&end_date=${reportState.endDate}`;
                window.open(url, '_blank');
            }

            // ============================================================
            // BATCH REPORT (일괄 리포트 생성 + PDF 다운로드)
            // ============================================================

            function getSelectedBranchIds() {
                return Array.from(state.selectedBranches);
            }

            const MAX_BATCH_SELECT = 5;

            function updateBranchSelection() {
                const checkboxes = document.querySelectorAll('.branch-checkbox');
                checkboxes.forEach(cb => {
                    const id = parseInt(cb.dataset.branchId);
                    if (cb.checked) {
                        if (state.selectedBranches.size >= MAX_BATCH_SELECT && !state.selectedBranches.has(id)) {
                            cb.checked = false;
                            showToast(`최대 ${MAX_BATCH_SELECT}개까지 선택 가능합니다.`, 'error');
                            return;
                        }
                        state.selectedBranches.add(id);
                    } else {
                        state.selectedBranches.delete(id);
                    }
                });

                const batchActions = getElement('batch-actions');
                const countEl = getElement('selected-count');
                const selectAll = getElement('select-all-branch');

                if (countEl) countEl.textContent = state.selectedBranches.size;
                if (batchActions) batchActions.style.display = state.selectedBranches.size > 0 ? 'flex' : 'none';
                if (selectAll && checkboxes.length > 0) {
                    selectAll.checked = Array.from(checkboxes).every(cb => cb.checked);
                }
            }

            function toggleSelectAllBranch() {
                const selectAll = getElement('select-all-branch');
                if (!selectAll) return;
                const checkboxes = document.querySelectorAll('.branch-checkbox');
                if (selectAll.checked) {
                    let count = 0;
                    checkboxes.forEach(cb => {
                        const id = parseInt(cb.dataset.branchId);
                        if (count < MAX_BATCH_SELECT) {
                            cb.checked = true;
                            state.selectedBranches.add(id);
                            count++;
                        } else {
                            cb.checked = false;
                        }
                    });
                    if (checkboxes.length > MAX_BATCH_SELECT) {
                        showToast(`최대 ${MAX_BATCH_SELECT}개까지 선택됩니다.`, 'info');
                        selectAll.checked = false;
                    }
                } else {
                    checkboxes.forEach(cb => {
                        cb.checked = false;
                        state.selectedBranches.delete(parseInt(cb.dataset.branchId));
                    });
                }
                updateBranchSelection();
            }

            function clearBranchSelection() {
                state.selectedBranches.clear();
                document.querySelectorAll('.branch-checkbox').forEach(cb => { cb.checked = false; });
                const selectAll = getElement('select-all-branch');
                if (selectAll) selectAll.checked = false;
                updateBranchSelection();
            }

            function restoreBranchCheckboxes() {
                const checkboxes = document.querySelectorAll('.branch-checkbox');
                checkboxes.forEach(cb => {
                    cb.checked = state.selectedBranches.has(parseInt(cb.dataset.branchId));
                });
                const selectAll = getElement('select-all-branch');
                if (selectAll) {
                    selectAll.checked = checkboxes.length > 0 && Array.from(checkboxes).every(cb => cb.checked);
                }
                const batchActions = getElement('batch-actions');
                if (batchActions) batchActions.style.display = state.selectedBranches.size > 0 ? 'flex' : 'none';
                const countEl = getElement('selected-count');
                if (countEl) countEl.textContent = state.selectedBranches.size;
            }

            function downloadBatchPDF() {
                const branchIds = getSelectedBranchIds();
                if (branchIds.length === 0) {
                    showToast('업체를 선택해주세요.', 'error');
                    return;
                }
                if (branchIds.length > 5) {
                    showToast('일괄 리포트는 최대 5개까지 선택 가능합니다.', 'error');
                    return;
                }

                // 기간 선택 모달 표시
                const modal = document.getElementById('batch-period-modal');
                const countEl = document.getElementById('batch-period-count');
                if (countEl) countEl.textContent = branchIds.length;

                const periodBtns = modal.querySelectorAll('.batch-period-btn');
                const confirmBtn = document.getElementById('batch-confirm-btn');
                const closeBtn = modal.querySelector('.modal-close');
                const cancelBtn = document.getElementById('batch-cancel-btn');
                let selectedPeriod = '1y';

                // 모달 열 때 상태 초기화
                selectPeriod('1y');
                const startInput = document.getElementById('batch-start-date');
                const endInput = document.getElementById('batch-end-date');
                if (startInput) startInput.value = '';
                if (endInput) endInput.value = '';

                modal.classList.add('active');

                function selectPeriod(period) {
                    selectedPeriod = period;
                    periodBtns.forEach(b => {
                        const isActive = b.dataset.period === period;
                        b.style.outline = isActive ? '2px solid var(--primary)' : 'none';
                        b.style.outlineOffset = isActive ? '1px' : '0';
                    });
                    // 프리셋 선택 시 직접 입력 초기화
                    const s = document.getElementById('batch-start-date');
                    const e = document.getElementById('batch-end-date');
                    if (s) s.value = '';
                    if (e) e.value = '';
                }

                function calcDates(period) {
                    const today = new Date();
                    const endDate = formatDateForAPI(today);
                    let start = new Date(today);
                    if (period === '1m') start.setMonth(start.getMonth() - 1);
                    else if (period === '3m') start.setMonth(start.getMonth() - 3);
                    else if (period === '6m') start.setMonth(start.getMonth() - 6);
                    else if (period === '1y') start.setFullYear(start.getFullYear() - 1);
                    else start = new Date('2020-01-01');
                    return { startDate: formatDateForAPI(start), endDate };
                }

                function cleanup() {
                    modal.classList.remove('active');
                    periodBtns.forEach(b => b.removeEventListener('click', onPeriodClick));
                    if (confirmBtn) confirmBtn.removeEventListener('click', onConfirm);
                    if (closeBtn) closeBtn.removeEventListener('click', cleanup);
                    if (cancelBtn) cancelBtn.removeEventListener('click', cleanup);
                }

                function onPeriodClick(e) {
                    selectPeriod(e.target.dataset.period);
                }

                function onConfirm() {
                    const customStart = document.getElementById('batch-start-date').value;
                    const customEnd = document.getElementById('batch-end-date').value;

                    let startDate, endDate;
                    if (customStart && customEnd) {
                        if (customStart > customEnd) {
                            showToast('시작일이 종료일보다 늦습니다.', 'error');
                            return;
                        }
                        startDate = customStart;
                        endDate = customEnd;
                    } else {
                        const dates = calcDates(selectedPeriod);
                        startDate = dates.startDate;
                        endDate = dates.endDate;
                    }

                    cleanup();
                    _executeBatchPDF(branchIds, startDate, endDate);
                }

                periodBtns.forEach(b => b.addEventListener('click', onPeriodClick));
                if (confirmBtn) confirmBtn.addEventListener('click', onConfirm);
                if (closeBtn) closeBtn.addEventListener('click', cleanup);
                if (cancelBtn) cancelBtn.addEventListener('click', cleanup);
            }

            async function _executeBatchPDF(branchIds, startDate, endDate) {
                const btn = getElement('btn-batch-pdf');
                const originalText = btn ? btn.textContent : '';
                const abortController = new AbortController();
                const onEsc = (e) => { if (e.key === 'Escape') abortController.abort(); };
                document.addEventListener('keydown', onEsc);

                if (btn) {
                    btn.disabled = true;
                    btn.textContent = '리포트 생성 준비 중...';
                }

                try {
                    // 1단계: 비동기 생성 작업 제출 (3개씩 동시)
                    const jobs = [];
                    const concurrency = 3;
                    for (let i = 0; i < branchIds.length; i += concurrency) {
                        if (abortController.signal.aborted) throw new DOMException('Aborted', 'AbortError');
                        const chunk = branchIds.slice(i, i + concurrency);
                        if (btn) btn.textContent = `작업 제출 중... (${i}/${branchIds.length})`;

                        const results = await Promise.allSettled(
                            chunk.map(async (branchId) => {
                                const res = await fetchRetry(`${API_PREFIX}/reports/${branchId}/generate/async`, {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ start_date: startDate, end_date: endDate }),
                                    signal: abortController.signal,
                                });
                                if (!res.ok) throw new Error(`Branch ${branchId} 실패`);
                                const result = await res.json();
                                if (result.success && result.data?.job_id) {
                                    return { branchId, jobId: result.data.job_id };
                                }
                                throw new Error(`Branch ${branchId}: job_id 없음`);
                            })
                        );

                        for (const r of results) {
                            if (r.status === 'fulfilled') {
                                jobs.push({ ...r.value, done: false, failed: false });
                            }
                        }
                    }

                    if (jobs.length === 0) {
                        throw new Error('리포트 생성 요청에 모두 실패했습니다.');
                    }

                    if (btn) btn.textContent = `리포트 생성 중... (0/${jobs.length})`;

                    // 2단계: 모든 작업 병렬 폴링 (최대 120초)
                    let pollCount = 0;
                    const maxPolls = CONFIG.POLLING.MAX_POLLS;

                    while (pollCount < maxPolls) {
                        if (abortController.signal.aborted) throw new DOMException('Aborted', 'AbortError');
                        const pending = jobs.filter(j => !j.done && !j.failed);
                        if (pending.length === 0) break;

                        await new Promise(resolve => setTimeout(resolve, CONFIG.POLLING.INTERVAL_MS));

                        await Promise.allSettled(pending.map(async (job) => {
                            try {
                                const res = await fetchRetry(
                                    `${API_PREFIX}/reports/${job.branchId}/job/${job.jobId}`,
                                    { signal: abortController.signal }
                                );
                                if (!res.ok) return;
                                const result = await res.json();
                                if (result.data.status === 'completed') job.done = true;
                                else if (result.data.status === 'failed') {
                                    job.failed = true;
                                    console.warn(`Branch ${job.branchId} 생성 실패:`, result.data.error_message);
                                }
                            } catch (e) {
                                if (e.name === 'AbortError') throw e;
                            }
                        }));

                        const doneCount = jobs.filter(j => j.done || j.failed).length;
                        if (btn) btn.textContent = `리포트 생성 중... (${doneCount}/${jobs.length})`;
                        pollCount++;
                    }

                    const completedJobs = jobs.filter(j => j.done);
                    if (completedJobs.length === 0) {
                        throw new Error('모든 리포트 생성에 실패했습니다. 잠시 후 다시 시도해주세요.');
                    }

                    // 3단계: 비동기 ZIP 생성 제출
                    if (btn) btn.textContent = 'PDF 생성 중...';

                    const batchRes = await fetchRetry(`${API_PREFIX}/reports/batch-pdf`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            branch_ids: completedJobs.map(j => j.branchId),
                            start_date: startDate,
                            end_date: endDate,
                        }),
                        signal: abortController.signal,
                    });

                    if (!batchRes.ok) {
                        const errData = await batchRes.json().catch(() => ({}));
                        throw new Error(errData.detail || 'PDF 생성 요청 실패');
                    }

                    const batchResult = await batchRes.json();
                    const batchJobId = batchResult.data?.job_id;
                    if (!batchJobId) throw new Error('batch-pdf job_id 없음');

                    // 4단계: ZIP 생성 폴링 (최대 300초)
                    let zipDone = false;
                    for (let i = 0; i < 150; i++) {
                        if (abortController.signal.aborted) throw new DOMException('Aborted', 'AbortError');
                        await new Promise(resolve => setTimeout(resolve, 2000));

                        const statusRes = await fetchRetry(
                            `${API_PREFIX}/reports/batch-pdf/job/${batchJobId}`,
                            { signal: abortController.signal }
                        );
                        if (!statusRes.ok) continue;

                        const statusData = (await statusRes.json()).data;
                        if (btn) btn.textContent = statusData.message || 'PDF 생성 중...';

                        if (statusData.status === 'completed') { zipDone = true; break; }
                        if (statusData.status === 'failed') throw new Error(statusData.error || 'PDF 생성 실패');
                    }

                    if (!zipDone) throw new Error('PDF 생성 시간 초과. 잠시 후 다시 시도해주세요.');

                    // 5단계: ZIP 다운로드
                    if (btn) btn.textContent = '다운로드 중...';

                    const dlRes = await fetchRetry(
                        `${API_PREFIX}/reports/batch-pdf/download/${batchJobId}`,
                        { signal: abortController.signal }
                    );
                    if (!dlRes.ok) throw new Error('ZIP 다운로드 실패');

                    const blob = await dlRes.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `AI_Reports_${startDate}_${endDate}.zip`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);

                    const failedCount = jobs.filter(j => j.failed).length;
                    if (failedCount > 0) {
                        showToast(`${completedJobs.length}개 완료, ${failedCount}개 실패`, 'warning');
                    } else {
                        showToast(`${completedJobs.length}개 업체 리포트 다운로드 완료`, 'success');
                    }
                } catch (e) {
                    if (e.name === 'AbortError') {
                        showToast('일괄 다운로드가 취소되었습니다.', 'info');
                    } else {
                        console.error('Batch report error:', e);
                        showToast(e.message || '일괄 리포트 생성에 실패했습니다.', 'error');
                    }
                } finally {
                    document.removeEventListener('keydown', onEsc);
                    if (btn) {
                        btn.disabled = false;
                        btn.textContent = originalText;
                    }
                }
            }

            async function toggleReviews(branchId) {
                const section = getElement('reviews-section');
                const btn = getElement('btn-toggle-reviews');
                const visible = toggleReviewsVisibility();

                if (section) section.style.display = visible ? 'block' : 'none';
                if (btn) btn.textContent = visible ? '📋 리뷰 숨기기' : '📋 리뷰 보기';

                if (visible) {
                    const carSelect = getElement('filter-car-model');
                    const sentSelect = getElement('filter-sentiment');

                    if (carSelect) carSelect.value = '';
                    if (sentSelect) sentSelect.value = '';

                    await loadReviews(branchId);
                }
            }


            async function toggleCarList(branchId) {
                const section = getElement('carlist-section');
                const btn = getElement('btn-toggle-carlist');
                const visible = toggleCarListVisibility();

                if (section) section.style.display = visible ? 'block' : 'none';
                if (btn) btn.textContent = visible ? '🚗 차량 숨기기' : '🚗 차량 리스트';

                if (visible && !state.carList.loaded) {
                    await loadCarList(branchId);
                }
            }

            async function loadCarList(branchId) {
                const content = getElement('carlist-content');
                const countEl = getElement('carlist-count');

                if (content) {
                    content.innerHTML = '<div class="loading"><div class="spinner"></div>로딩 중...</div>';
                }

                try {
                    const result = await fetchBranchReviews(branchId, { limit: 1, offset: 0 });
                    const carModels = result.car_models || [];

                    setCarListModels(carModels);

                    if (countEl) {
                        countEl.textContent = `(${carModels.length}종)`;
                    }

                    if (content) {
                        content.textContent = '';
                        if (carModels.length === 0) {
                            content.appendChild(el('div', {
                                style: { padding: '16px', color: 'var(--grey-5)', fontStyle: 'italic' },
                                textContent: '등록된 차량이 없습니다.'
                            }));
                        } else {
                            carModels.forEach(function (model) {
                                content.appendChild(el('span', {
                                    style: { display: 'inline-block', padding: '8px 16px', background: 'var(--grey-8)', borderRadius: '20px', fontSize: '13px', color: 'var(--grey-2)' },
                                    textContent: '\uD83D\uDE97 ' + model
                                }));
                            });
                        }
                    }
                } catch (e) {
                    console.error('Car list load error:', e);
                    if (content) {
                        content.textContent = '';
                        content.appendChild(el('div', {
                            style: { padding: '16px', color: 'var(--error)' },
                            textContent: '차량 리스트 로드 실패'
                        }));
                    }
                }
            }

            function onCarModelChange(branchId) {
                applyFilters(branchId);
            }

            function applyFilters(branchId) {
                setReviewsPage(0);
                loadReviews(branchId);
            }

            async function loadReviews(branchId) {
                const carModel = getElement('filter-car-model')?.value || '';
                const sentiment = getElement('filter-sentiment')?.value || '';
                const useAthena = !carModel && !sentiment;

                const listEl = getElement('reviews-list');
                if (listEl) {
                    const msg = useAthena ? '원본 리뷰 검색 중... (2~4초 소요)' : '로딩 중...';
                    listEl.textContent = '';
                    const div = document.createElement('div');
                    div.className = 'loading';
                    const spinner = document.createElement('div');
                    spinner.className = 'spinner';
                    div.appendChild(spinner);
                    div.appendChild(document.createTextNode(msg));
                    listEl.appendChild(div);
                }

                const offset = state.reviews.currentPage * state.reviews.pageSize;

                try {
                    const result = await fetchBranchReviews(branchId, {
                        limit: state.reviews.pageSize,
                        offset,
                        carModel,
                        sentiment,
                    });

                    // debug: console.log('리뷰 API 응답:', result);

                    setReviewsTotal(result.total || 0);

                    if (!state.reviews.carModelsLoaded && result.car_models?.length > 0) {
                        updateCarModelDropdown(result.car_models);
                        markCarModelsLoaded();
                    }

                    updateReviewsCount(result.total || 0);
                    renderReviewsList(result.reviews || [], offset);

                    const totalPages = Math.ceil((result.total || 0) / state.reviews.pageSize);
                    updateReviewsPagination(state.reviews.currentPage, totalPages);

                } catch (e) {
                    console.error('Reviews load error:', e);
                    const listEl = getElement('reviews-list');
                    if (listEl) {
                        listEl.textContent = '';
                        const errDiv = document.createElement('div');
                        errDiv.style.cssText = 'padding: 24px; text-align: center; color: var(--error);';
                        errDiv.textContent = '로드 실패';
                        listEl.appendChild(errDiv);
                    }
                }
            }

            function loadMoreReviews(branchId, direction) {
                if (direction === 'prev' && state.reviews.currentPage > 0) {
                    setReviewsPage(state.reviews.currentPage - 1);
                } else if (direction === 'next') {
                    setReviewsPage(state.reviews.currentPage + 1);
                }

                loadReviews(branchId);
            }

            // Expose global handlers immediately (before DOMContentLoaded)
            registerGlobalHandlers();

            // Auto Initialize
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', init);
            } else {
                init();
            }
        })();
