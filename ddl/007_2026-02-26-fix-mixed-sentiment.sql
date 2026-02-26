UPDATE branch_reviews SET sentiment = 'neutral' WHERE sentiment = 'mixed';
UPDATE branch_reviews SET sentiment = 'neutral' WHERE sentiment NOT IN ('positive', 'negative', 'neutral') AND sentiment IS NOT NULL;
