
import os

file_path = 'web/templates/dashboard_v2.html'

def patch_file():
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. showDetail 함수 찾기
    func_marker = "async function showDetail(branchId)"
    func_idx = content.find(func_marker)
    if func_idx == -1:
        print("Error: Could not find showDetail function")
        return

    # 2. const html = ` 찾기 (함수 내부에서)
    start_marker = "const html = `"
    start_idx = content.find(start_marker, func_idx)
    if start_idx == -1:
        print("Error: Could not find 'const html = `' inside showDetail")
        return

    # 3. 끝나는 `(백틱)과 ; 찾기
    # 단순 ` 찾기가 아니라, 템플릿이 끝나는 지점을 찾아야 함.
    # 기존 코드는 `                `;` 로 끝남 (들여쓰기 포함)
    # 하지만 안전하게 `;` 로 끝나는 백틱을 찾아야 함.
    # 현재 `html` 변수 다음에 바로 `document.getElementById`가 나오므로,
    # `document.getElementById('modal-body').innerHTML = html;` 앞의 `;`를 찾으면 됨.
    
    next_statement = "document.getElementById('modal-body').innerHTML = html;"
    next_idx = content.find(next_statement, start_idx)
    if next_idx == -1:
        print("Error: Could not find next statement")
        return
        
    # next_statement 바로 앞의 `;` 찾기 (역방향 탐색 대신 슬라이싱)
    # start_idx 이후부터 next_idx 이전까지 중에서 마지막 `;` 찾기?
    # 아니, `const html = ` ... `;` 구조임.
    # `next_idx` 바로 앞의 공백들을 건너뛰고 `;`를 찾아야 함.
    
    temp_segment = content[start_idx:next_idx]
    end_tick_idx = temp_segment.rfind('`;')
    
    if end_tick_idx == -1:
        print("Error: Could not find ending backtick")
        return
        
    abs_end_idx = start_idx + end_tick_idx
    
    new_html = r"""
                    <div class="modal-header-content" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px;">
                        <div>
                            <div style="font-size: 14px; color: var(--grey-5); margin-bottom: 4px;">ID: ${data.branch_id}</div>
                            <h2 style="font-size: 24px; font-weight: 700; color: var(--grey-1); margin: 0;">${data.branch_name}</h2>
                            <div style="font-size: 14px; color: var(--grey-3); margin-top: 4px;">${data.region || '지역 정보 없음'}</div>
                        </div>
                        <div>
                            <span class="badge badge-${statusClassMap[data.status] || 'grey'}" style="font-size: 14px; padding: 6px 12px;">
                                ${statusLabelMap[data.status] || data.status}
                            </span>
                        </div>
                    </div>

                    <!-- Keywords -->
                    <div style="margin-bottom: 24px;">
                        <div style="font-size: 14px; font-weight: 600; color: var(--grey-3); margin-bottom: 8px;">주요 키워드</div>
                        <div class="keywords" id="keywords-display" style="display: flex; gap: 8px; flex-wrap: wrap;">
                             ${(() => {
                                let keywords = data.keywords || [];
                                if (!keywords.length) {
                                    keywords = [data.keyword_1, data.keyword_2, data.keyword_3].filter(k => k);
                                }
                                if (keywords.length > 0) {
                                    return keywords.map(k => `<span style="background: var(--primary-light); color: var(--primary); padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: 500;">#${k}</span>`).join('');
                                } else {
                                    return '<span class="summary-empty">키워드 없음</span>';
                                }
                            })()}
                        </div>
                        <div class="edit-area" id="edit-area-keywords" style="display:none; margin-top: 12px;">
                            <input type="text" id="edit-keywords-input" placeholder="#키워드1 #키워드2 #키워드3 ..." 
                                value="${(() => {
                                    let keywords = data.keywords || [];
                                    if (!keywords.length) {
                                        keywords = [data.keyword_1, data.keyword_2, data.keyword_3].filter(k => k);
                                    }
                                    return keywords.map(k => '#' + k).join(' ');
                                })()}"
                                style="width: 100%; padding: 12px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 14px;">
                            <div style="margin-top: 8px; display: flex; gap: 8px;">
                                <button class="btn btn-primary btn-sm" onclick="saveKeywords(${data.branch_id})">💾 저장</button>
                                <button class="btn btn-secondary btn-sm" onclick="cancelKeywordEdit()">취소</button>
                            </div>
                            <div style="margin-top: 8px; font-size: 12px; color: var(--grey-5);">
                                💡 # 기호로 키워드를 구분하세요 (예: #친절 #깨끗 #편리)
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" style="margin-top: 12px;" onclick="toggleKeywordEdit()" id="edit-btn-keywords">✏️ 키워드 수정</button>
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
                    <div class="tabs" style="display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--grey-8);">
                        <div class="tab active" onclick="showSummaryTab(this, 'all')" style="padding: 12px 16px; cursor: pointer; font-weight: 600; color: var(--primary); border-bottom: 2px solid var(--primary);">전체 기간</div>
                        <div class="tab" onclick="showSummaryTab(this, '1y')" style="padding: 12px 16px; cursor: pointer; color: var(--grey-5);">1년</div>
                        <div class="tab" onclick="showSummaryTab(this, '6m')" style="padding: 12px 16px; cursor: pointer; color: var(--grey-5);">6개월</div>
                        <div class="tab" onclick="showSummaryTab(this, '3m')" style="padding: 12px 16px; cursor: pointer; color: var(--grey-5);">3개월</div>
                        <div class="tab" onclick="showSummaryTab(this, '1m')" style="padding: 12px 16px; cursor: pointer; color: var(--grey-5);">1개월</div>
                    </div>

                    <!-- Summary Content -->
                    <div id="summary-content" style="min-height: 200px; background: white; border-radius: 0 0 var(--radius) var(--radius);">
                        ${['all', '1y', '6m', '3m', '1m'].map(period => `
                            <div class="summary-panel" id="panel-${period}" style="display: ${period === 'all' ? 'block' : 'none'};">
                                <div class="summary-text" id="summary-text-${period}" style="font-size: 15px; line-height: 1.7; color: var(--grey-2); white-space: pre-wrap;">${data['summary_' + period] || '<span class="summary-empty" style="color: var(--grey-5); font-style: italic;">작성된 요약이 없습니다.</span>'}</div>
                                <div class="edit-area" id="edit-area-${period}" style="display:none; margin-top: 12px;">
                                    <textarea id="edit-summary-${period}" style="width: 100%; min-height: 150px; padding: 16px; border: 1px solid var(--grey-7); border-radius: var(--radius-sm); font-size: 14px; line-height: 1.6; resize: vertical; margin-bottom: 12px; font-family: inherit;">${data['summary_' + period] || ''}</textarea>
                                    <div style="display: flex; gap: 8px; justify-content: flex-end;">
                                        <button class="btn btn-secondary btn-sm" onclick="cancelPeriodEdit('${period}')">취소</button>
                                        <button class="btn btn-primary btn-sm" onclick="savePeriodSummary(${data.branch_id}, '${period}')">저장하기</button>
                                    </div>
                                </div>
                                <div style="display: flex; justify-content: flex-end; margin-top: 16px;">
                                    <button class="btn btn-secondary btn-sm" onclick="togglePeriodEdit('${period}')" id="edit-btn-${period}">✏️ 요약 수정</button>
                                </div>
                            </div>
                        `).join('')}
                    </div>

                    <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--grey-8); display: flex; justify-content: flex-end; gap: 12px;">
                        <button class="btn btn-secondary" onclick="updateStatus(${data.branch_id}, 'draft')">Draft로 변경</button>
                        <button class="btn btn-secondary" onclick="updateStatus(${data.branch_id}, 'approved')">승인(Approved)</button>
                        <button class="btn btn-primary" onclick="updateStatus(${data.branch_id}, 'published')">최종 게시</button>
                    </div>
    """
    
    # 교체 (const html = ` 뒷부분부터 `; 앞까지)
    # new_html은 내용만 있으므로 양옆의 ` 도 처리해야 함.
    # 아니, new_html에 ` 없으므로...
    # 원본: const html = `....`;
    # 교체: const html = ` + new_html + `;
    
    # abs_end_idx는 `;`의 인덱스.
    # start_idx + len(start_marker) 부터
    
    final_content = content[:start_idx + len(start_marker)] + new_html + content[abs_end_idx:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)
    
    print("Successfully patched dashboard_v2.html")

if __name__ == "__main__":
    patch_file()
