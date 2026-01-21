-- ============================================================
-- branch_summaries 테이블 (통합 요약 테이블)
-- 지점당 1개 행으로 모든 정보를 단일 테이블에 저장
-- ============================================================

-- 기존 테이블 백업 (필요시)
-- CREATE TABLE summaries_backup AS SELECT * FROM summaries;

-- 새 통합 테이블 생성
CREATE TABLE IF NOT EXISTS branch_summaries (
    id SERIAL PRIMARY KEY,

    -- 기본 정보
    branch_id INTEGER UNIQUE NOT NULL,      -- 지점번호
    branch_name VARCHAR(100),               -- 업체명
    region VARCHAR(100),                    -- 지역

    -- 통계 정보
    review_count INTEGER DEFAULT 0,         -- 리뷰 개수
    avg_rating DECIMAL(3,2),                -- 평균평점 (예: 4.52)

    -- 키워드 (TOP 3)
    keyword_1 VARCHAR(50),                  -- 키워드 1
    keyword_2 VARCHAR(50),                  -- 키워드 2
    keyword_3 VARCHAR(50),                  -- 키워드 3

    -- 기간별 요약
    summary_1m TEXT,                        -- 1개월 요약
    summary_3m TEXT,                        -- 3개월 요약
    summary_6m TEXT,                        -- 6개월 요약
    summary_1y TEXT,                        -- 1년 요약
    summary_all TEXT,                       -- 전체 요약

    -- 상태 관리
    status VARCHAR(20) DEFAULT 'draft',     -- draft / approved / published

    -- 타임스탬프
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_branch_summaries_branch_id ON branch_summaries(branch_id);
CREATE INDEX IF NOT EXISTS idx_branch_summaries_status ON branch_summaries(status);
CREATE INDEX IF NOT EXISTS idx_branch_summaries_region ON branch_summaries(region);

-- 업데이트 시 updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION update_branch_summaries_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_branch_summaries_timestamp ON branch_summaries;
CREATE TRIGGER trigger_update_branch_summaries_timestamp
    BEFORE UPDATE ON branch_summaries
    FOR EACH ROW
    EXECUTE FUNCTION update_branch_summaries_timestamp();

-- RLS (Row Level Security) 정책 (필요시)
-- ALTER TABLE branch_summaries ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE branch_summaries IS '지점별 통합 요약 테이블 - 모든 기간별 요약을 단일 행에 저장';
COMMENT ON COLUMN branch_summaries.branch_id IS '지점 고유 번호';
COMMENT ON COLUMN branch_summaries.branch_name IS '업체명 (제휴사명)';
COMMENT ON COLUMN branch_summaries.region IS '지역 (주소에서 추출)';
COMMENT ON COLUMN branch_summaries.review_count IS '총 리뷰 개수';
COMMENT ON COLUMN branch_summaries.avg_rating IS '평균 평점 (1.00 ~ 5.00)';
COMMENT ON COLUMN branch_summaries.keyword_1 IS 'TOP 1 키워드';
COMMENT ON COLUMN branch_summaries.keyword_2 IS 'TOP 2 키워드';
COMMENT ON COLUMN branch_summaries.keyword_3 IS 'TOP 3 키워드';
COMMENT ON COLUMN branch_summaries.summary_1m IS '최근 1개월 리뷰 기반 AI 요약';
COMMENT ON COLUMN branch_summaries.summary_3m IS '최근 3개월 리뷰 기반 AI 요약';
COMMENT ON COLUMN branch_summaries.summary_6m IS '최근 6개월 리뷰 기반 AI 요약';
COMMENT ON COLUMN branch_summaries.summary_1y IS '최근 1년 리뷰 기반 AI 요약';
COMMENT ON COLUMN branch_summaries.summary_all IS '전체 기간 리뷰 기반 AI 요약';
