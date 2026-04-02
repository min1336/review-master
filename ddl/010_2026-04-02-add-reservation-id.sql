BEGIN;

-- reservation_id 컬럼이 없으면 추가, 있으면 varchar로 변경
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'branch_reviews' AND column_name = 'reservation_id'
    ) THEN
        ALTER TABLE public.branch_reviews ADD COLUMN reservation_id varchar(50);
    ELSE
        ALTER TABLE public.branch_reviews ALTER COLUMN reservation_id TYPE varchar(50) USING reservation_id::varchar;
    END IF;
END $$;

COMMIT;
