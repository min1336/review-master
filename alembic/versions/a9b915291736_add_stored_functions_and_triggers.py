"""add stored functions and triggers

Revision ID: a9b915291736
Revises: 7861cf029bb8
Create Date: 2026-04-03 11:23:55.912468

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a9b915291736'
down_revision: Union[str, None] = '7861cf029bb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. get_branch_company_map ---
    op.execute("""
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
    """)

    # --- 2. get_review_stats_by_branch ---
    op.execute("""
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
    """)

    # --- 3. get_summary_stats ---
    op.execute("""
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
    """)

    # --- 4. fn_sync_branch_review_count + trigger ---
    op.execute("""
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
            branch_name = COALESCE(branch_summaries.branch_name, EXCLUDED.branch_name);

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_sync_branch_review_count ON branch_reviews;")
    op.execute("""
        CREATE TRIGGER trg_sync_branch_review_count
        AFTER INSERT OR DELETE OR UPDATE ON branch_reviews
        FOR EACH ROW
        EXECUTE FUNCTION fn_sync_branch_review_count();
    """)

    # --- 5. update_branch_reviews_updated_at + trigger ---
    op.execute("""
        CREATE OR REPLACE FUNCTION update_branch_reviews_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_branch_reviews_updated_at ON branch_reviews;")
    op.execute("""
        CREATE TRIGGER trg_branch_reviews_updated_at
        BEFORE UPDATE ON branch_reviews
        FOR EACH ROW
        EXECUTE FUNCTION update_branch_reviews_updated_at();
    """)

    # --- 6. getTagStatsByPeriod ---
    op.execute("""
        CREATE OR REPLACE FUNCTION "getTagStatsByPeriod"(
            p_branch_id INTEGER,
            p_start_date TEXT,
            p_end_date TEXT
        )
        RETURNS TABLE(
            "tagName"       VARCHAR,
            "categoryName"  VARCHAR,
            "positiveCount" BIGINT,
            "negativeCount" BIGINT,
            "neutralCount"  BIGINT,
            "totalCount"    BIGINT
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                t.name                                                          AS "tagName",
                COALESCE(c.name, '')::VARCHAR                                   AS "categoryName",
                COUNT(*) FILTER (WHERE rtm.sentiment = 'positive')              AS "positiveCount",
                COUNT(*) FILTER (WHERE rtm.sentiment = 'negative')              AS "negativeCount",
                COUNT(*) FILTER (WHERE rtm.sentiment IN ('neutral','mixed'))    AS "neutralCount",
                COUNT(*)                                                        AS "totalCount"
            FROM review_tag_mappings rtm
            JOIN branch_reviews br ON rtm.review_id = br.review_id
            JOIN tags t ON rtm.tag_id = t.id
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE br.branch_id = p_branch_id
              AND br.review_date >= p_start_date::TIMESTAMP
              AND br.review_date < p_end_date::TIMESTAMP
            GROUP BY t.name, c.name
            HAVING COUNT(*) > 0
            ORDER BY COUNT(*) DESC;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_branch_reviews_updated_at ON branch_reviews;")
    op.execute("DROP TRIGGER IF EXISTS trg_sync_branch_review_count ON branch_reviews;")
    op.execute('DROP FUNCTION IF EXISTS "getTagStatsByPeriod"(INTEGER, TEXT, TEXT);')
    op.execute("DROP FUNCTION IF EXISTS update_branch_reviews_updated_at();")
    op.execute("DROP FUNCTION IF EXISTS fn_sync_branch_review_count();")
    op.execute("DROP FUNCTION IF EXISTS get_summary_stats();")
    op.execute("DROP FUNCTION IF EXISTS get_review_stats_by_branch();")
    op.execute("DROP FUNCTION IF EXISTS get_branch_company_map();")
