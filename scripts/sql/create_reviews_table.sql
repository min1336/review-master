-- Reviews table for storing reviews with sentiment tags
-- Run this in Supabase SQL Editor or psql

-- Create reviews table
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    sentiment VARCHAR(20) NOT NULL,  -- 'positive', 'negative', 'neutral'
    sentiment_score DECIMAL(5,4),
    keywords JSONB DEFAULT '[]'::jsonb,
    review_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_branch FOREIGN KEY (branch_id)
        REFERENCES branches(branch_id) ON DELETE CASCADE
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_reviews_branch_id ON reviews(branch_id);
CREATE INDEX IF NOT EXISTS idx_reviews_sentiment ON reviews(sentiment);
CREATE INDEX IF NOT EXISTS idx_reviews_branch_sentiment ON reviews(branch_id, sentiment);
CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at DESC);

-- Trigger for updated_at (if needed later)
-- CREATE TRIGGER update_reviews_updated_at
--     BEFORE UPDATE ON reviews
--     FOR EACH ROW
--     EXECUTE FUNCTION update_updated_at_column();

-- Sample query: Search reviews by sentiment tag
-- SELECT * FROM reviews WHERE sentiment = 'positive' AND branch_id = 123 LIMIT 100;

-- Sample query: Get sentiment statistics by branch
-- SELECT
--     sentiment,
--     COUNT(*) as count
-- FROM reviews
-- WHERE branch_id = 123
-- GROUP BY sentiment;
