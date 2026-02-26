-- branch_reviews 테이블 생성 (EC2 프로덕션용)
-- DDL 001 + DDL 005 통합 스크립트
-- Supabase 전용 GRANT 제거, PostgreSQL 표준만 사용

BEGIN;

-- 1. 테이블 생성
CREATE TABLE IF NOT EXISTS public.branch_reviews
(
    id                 bigserial PRIMARY KEY,
    review_id          integer UNIQUE,
    branch_id          integer NOT NULL,
    branch_name        varchar(100),
    company_name       varchar(100),
    content            text,
    rating_service     numeric(2, 1),
    rating_car         numeric(2, 1),
    rating_convenience numeric(2, 1),
    review_date        timestamp with time zone,
    car_model          varchar(100),
    rent_type          varchar(20),
    created_at         timestamp with time zone DEFAULT now(),
    sentiment          varchar(20),
    is_new             boolean DEFAULT false,
    updated_at         timestamp with time zone DEFAULT now(),
    deleted_at         timestamp with time zone
);

COMMENT ON TABLE public.branch_reviews IS '원본 리뷰 데이터 (지점별 그룹화)';

-- 2. 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_reviews_sentiment
    ON public.branch_reviews (sentiment);

CREATE INDEX IF NOT EXISTS idx_reviews_branch_sentiment
    ON public.branch_reviews (branch_id, sentiment);

CREATE INDEX IF NOT EXISTS idx_branch_reviews_is_new
    ON public.branch_reviews (review_date DESC)
    WHERE is_new = true;

CREATE INDEX IF NOT EXISTS idx_reviews_branch_date
    ON public.branch_reviews (branch_id ASC, review_date DESC);

CREATE INDEX IF NOT EXISTS idx_branch_reviews_sentiment_filter
    ON public.branch_reviews (branch_id ASC, sentiment ASC, review_date DESC);

CREATE INDEX IF NOT EXISTS idx_branch_reviews_review_date
    ON public.branch_reviews (review_date);

CREATE INDEX IF NOT EXISTS idx_branch_reviews_branch_company
    ON public.branch_reviews (branch_id, company_name)
    WHERE company_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_branch_reviews_deleted
    ON public.branch_reviews (deleted_at)
    WHERE deleted_at IS NOT NULL;

-- review_id UNIQUE 부분 인덱스 (ON CONFLICT upsert용)
CREATE UNIQUE INDEX IF NOT EXISTS uq_branch_reviews_review_id
    ON public.branch_reviews (review_id)
    WHERE review_id IS NOT NULL;

-- 3. updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION update_branch_reviews_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_branch_reviews_updated_at ON branch_reviews;
CREATE TRIGGER trg_branch_reviews_updated_at
    BEFORE UPDATE ON branch_reviews
    FOR EACH ROW
    EXECUTE FUNCTION update_branch_reviews_updated_at();

COMMIT;
