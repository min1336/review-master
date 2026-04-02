BEGIN;

ALTER TABLE public.branch_reviews
    ADD COLUMN IF NOT EXISTS rental_date timestamp with time zone;

ALTER TABLE public.branch_reviews
    ADD COLUMN IF NOT EXISTS return_date timestamp with time zone;

CREATE INDEX IF NOT EXISTS idx_branch_reviews_rental_date
    ON public.branch_reviews (rental_date)
    WHERE rental_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_branch_reviews_return_date
    ON public.branch_reviews (return_date)
    WHERE return_date IS NOT NULL;

COMMIT;
