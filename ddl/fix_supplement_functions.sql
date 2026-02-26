-- branch_reviews 보조 함수 및 트리거 (EC2 프로덕션용)
-- fix_create_branch_reviews.sql 실행 후 적용

BEGIN;

-- 1. get_branch_company_map(): branch_id → company_name 매핑
-- analysis_service.py에서 필터 옵션 조회 시 사용
CREATE OR REPLACE FUNCTION get_branch_company_map()
RETURNS TABLE(branch_id integer, company_name varchar) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT br.branch_id, br.company_name
    FROM branch_reviews br
    WHERE br.company_name IS NOT NULL
    ORDER BY br.branch_id;
END;
$$ LANGUAGE plpgsql STABLE;

-- 2. get_review_stats_by_branch(): 지점별 리뷰 통계
-- review_repository.py에서 정의되어 있으나 현재 미사용 (향후 사용 대비)
CREATE OR REPLACE FUNCTION get_review_stats_by_branch()
RETURNS TABLE(
    branch_id integer,
    total_reviews bigint,
    positive_count bigint,
    neutral_count bigint,
    negative_count bigint,
    avg_rating_service numeric,
    avg_rating_car numeric,
    avg_rating_convenience numeric
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        br.branch_id,
        COUNT(*)::bigint AS total_reviews,
        COUNT(*) FILTER (WHERE br.sentiment = 'positive')::bigint AS positive_count,
        COUNT(*) FILTER (WHERE br.sentiment = 'neutral')::bigint AS neutral_count,
        COUNT(*) FILTER (WHERE br.sentiment = 'negative')::bigint AS negative_count,
        ROUND(AVG(br.rating_service), 1) AS avg_rating_service,
        ROUND(AVG(br.rating_car), 1) AS avg_rating_car,
        ROUND(AVG(br.rating_convenience), 1) AS avg_rating_convenience
    FROM branch_reviews br
    WHERE br.deleted_at IS NULL
    GROUP BY br.branch_id
    ORDER BY br.branch_id;
END;
$$ LANGUAGE plpgsql STABLE;

-- 3. review_count 자동 갱신 트리거 (DDL 003)
-- branch_reviews INSERT/DELETE/UPDATE 시 branch_summaries.review_count 동기화
CREATE OR REPLACE FUNCTION fn_sync_branch_review_count()
RETURNS TRIGGER AS $$
DECLARE
    target_branch_id INTEGER;
BEGIN
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

COMMIT;
