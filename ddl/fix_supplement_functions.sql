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

-- 3. review_count + branch_name 자동 갱신 트리거 (DDL 003 확장)
-- branch_reviews INSERT/DELETE/UPDATE 시 branch_summaries 동기화
-- branch_name: "회사명 지점명" 형식으로 자동 설정 (NULL인 경우만)
CREATE OR REPLACE FUNCTION fn_sync_branch_review_count()
RETURNS TRIGGER AS $$
DECLARE
    target_branch_id INTEGER;
    combined_name    VARCHAR(100);
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

    -- branch_name 조합: "회사명 지점명" (프로덕션 형식)
    IF TG_OP != 'DELETE' THEN
        combined_name := LEFT(TRIM(
            COALESCE(NEW.company_name, '') || ' ' || COALESCE(NEW.branch_name, '')
        ), 100);
        IF combined_name = '' THEN combined_name := NULL; END IF;
    END IF;

    INSERT INTO branch_summaries (branch_id, branch_name, review_count)
    VALUES (
        target_branch_id,
        combined_name,
        (SELECT COUNT(*) FROM branch_reviews WHERE branch_id = target_branch_id)
    )
    ON CONFLICT (branch_id) DO UPDATE
    SET review_count = (
        SELECT COUNT(*) FROM branch_reviews WHERE branch_id = target_branch_id
    ),
    -- branch_name은 NULL인 경우만 채움 (수동 설정값 보호)
    branch_name = COALESCE(branch_summaries.branch_name, EXCLUDED.branch_name);

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

-- 4. ON CONFLICT upsert에 필요한 UNIQUE 인덱스 (누락 시 모든 upsert 실패)
CREATE UNIQUE INDEX IF NOT EXISTS uq_branch_reviews_review_id ON branch_reviews (review_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tags_name ON tags (name);
CREATE UNIQUE INDEX IF NOT EXISTS uq_branch_tags_composite ON branch_tags (branch_id, tag_id, period_type);
CREATE UNIQUE INDEX IF NOT EXISTS uq_car_models_master_model_name ON car_models_master (model_name);
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_tag_mappings_composite ON review_tag_mappings (review_id, tag_id, sentiment);
CREATE UNIQUE INDEX IF NOT EXISTS uq_monthly_tag_stats_composite ON monthly_tag_stats (branch_id, period, tag_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_monthly_car_model_tag_stats_composite ON monthly_car_model_tag_stats (car_model_id, period, tag_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_monthly_rating_stats_composite ON monthly_rating_stats (branch_id, period);
CREATE UNIQUE INDEX IF NOT EXISTS uq_monthly_sentiment_stats_composite ON monthly_sentiment_stats (branch_id, period);
CREATE UNIQUE INDEX IF NOT EXISTS uq_branch_keywords_composite ON branch_keywords (branch_id, keyword);
CREATE UNIQUE INDEX IF NOT EXISTS uq_branch_reports_composite ON branch_reports (branch_id, period_start, period_end);

-- 5. get_summary_stats(): 대시보드 통계 (지점 수, 리뷰 수)
-- summary_repository.py에서 /api/summaries/stats 조회 시 사용
CREATE OR REPLACE FUNCTION get_summary_stats()
RETURNS TABLE(total_branches bigint, total_reviews bigint) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::bigint AS total_branches,
        COALESCE(SUM(review_count), 0)::bigint AS total_reviews
    FROM branch_summaries;
END;
$$ LANGUAGE plpgsql STABLE;

COMMIT;
