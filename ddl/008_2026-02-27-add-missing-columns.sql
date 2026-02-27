BEGIN;

ALTER TABLE public.branch_reviews
    ADD COLUMN IF NOT EXISTS updated_at timestamp with time zone DEFAULT now();

ALTER TABLE public.branch_reviews
    ADD COLUMN IF NOT EXISTS deleted_at timestamp with time zone;

CREATE INDEX IF NOT EXISTS idx_branch_reviews_deleted
    ON public.branch_reviews (deleted_at)
    WHERE deleted_at IS NOT NULL;

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
