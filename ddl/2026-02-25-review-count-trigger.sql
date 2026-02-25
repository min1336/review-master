-- branch_reviews INSERT/DELETE/UPDATE 시 branch_summaries.review_count 자동 갱신 트리거
-- Dashboard와 Analysis 페이지의 리뷰 건수 정합성 보장

CREATE OR REPLACE FUNCTION fn_sync_branch_review_count()
RETURNS TRIGGER AS $$
DECLARE
    target_branch_id INTEGER;
BEGIN
    -- UPDATE로 branch_id가 변경된 경우: 이전 지점도 갱신
    IF TG_OP = 'UPDATE' AND OLD.branch_id IS DISTINCT FROM NEW.branch_id THEN
        UPDATE branch_summaries
        SET review_count = (
            SELECT COUNT(*) FROM branch_reviews WHERE branch_id = OLD.branch_id
        )
        WHERE branch_id = OLD.branch_id;
    END IF;

    IF TG_OP = 'DELETE' THEN
        target_branch_id := OLD.branch_id;
    ELSE
        target_branch_id := NEW.branch_id;
    END IF;

    -- branch_summaries에 행이 있으면 UPDATE, 없으면 INSERT
    INSERT INTO branch_summaries (branch_id, review_count)
    VALUES (
        target_branch_id,
        (SELECT COUNT(*) FROM branch_reviews WHERE branch_id = target_branch_id)
    )
    ON CONFLICT (branch_id) DO UPDATE
    SET review_count = (
        SELECT COUNT(*) FROM branch_reviews WHERE branch_id = target_branch_id
    );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_branch_review_count ON branch_reviews;

CREATE TRIGGER trg_sync_branch_review_count
AFTER INSERT OR DELETE OR UPDATE ON branch_reviews
FOR EACH ROW
EXECUTE FUNCTION fn_sync_branch_review_count();
