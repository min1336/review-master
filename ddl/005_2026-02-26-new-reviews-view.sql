-- branch_reviews 생명주기 관리 컬럼 추가
ALTER TABLE branch_reviews
    ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now(),
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

-- review_id UNIQUE 제약조건 (SQLAlchemy ON CONFLICT upsert 필수)
CREATE UNIQUE INDEX IF NOT EXISTS uq_branch_reviews_review_id
ON branch_reviews (review_id)
WHERE review_id IS NOT NULL;

-- new_reviews 참조 트리거/함수 삭제 (테이블 DROP 전에 정리)
DROP TRIGGER IF EXISTS trg_delete_new_review_on_read ON branch_reviews;
DROP FUNCTION IF EXISTS delete_new_review_on_read();

-- new_reviews 테이블 삭제 (branch_reviews로 통합)
DROP TABLE IF EXISTS new_reviews;

-- is_new=true 부분 인덱스 (신규 리뷰 조회 최적화)
CREATE INDEX IF NOT EXISTS idx_branch_reviews_is_new
ON branch_reviews (review_date DESC)
WHERE is_new = true;

-- deleted_at 부분 인덱스 (소프트 삭제 조회 최적화)
CREATE INDEX IF NOT EXISTS idx_branch_reviews_deleted
ON branch_reviews (deleted_at)
WHERE deleted_at IS NOT NULL;

-- updated_at 트리거 (행 변경 시 자동 갱신)
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
