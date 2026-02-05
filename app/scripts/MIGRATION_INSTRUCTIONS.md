# Review Read Status Migration Instructions

## 1. Execute SQL in Supabase Dashboard

Go to your Supabase project dashboard and run the following SQL in the SQL Editor:

```sql
-- review_read_status 테이블 생성
CREATE TABLE IF NOT EXISTS review_read_status (
    id SERIAL PRIMARY KEY,
    review_id VARCHAR(255) UNIQUE NOT NULL,
    read_at TIMESTAMP DEFAULT now(),
    read_by VARCHAR(100)
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_review_read_status_review_id
ON review_read_status(review_id);
```

## 2. Files Created

### Model: `app/models/review_read_status.py`
- Pydantic model for the review_read_status table
- Fields: id, review_id, read_at, read_by

### Repository: `app/repository/review_read_status_repository.py`
- BaseRepository implementation
- Methods:
  - `mark_as_read(review_ids, read_by=None)` - Mark reviews as read (batch processing)
  - `mark_all_as_read(read_by=None)` - Mark all reviews from branch_reviews as read
  - `get_read_ids(review_ids)` - Get set of read review IDs
  - `is_read(review_id)` - Check if single review is read
  - `unmark_as_read(review_ids)` - Remove read status
  - `get_read_count()` - Get total count of read reviews

## 3. Usage Example

```python
from repository.session import get_client
from repository.review_read_status_repository import ReviewReadStatusRepository

# Initialize repository
client = await get_client()
repo = ReviewReadStatusRepository(client)

# Mark reviews as read
review_ids = ["REV001", "REV002", "REV003"]
count = await repo.mark_as_read(review_ids, read_by="admin")
print(f"Marked {count} reviews as read")

# Get read review IDs
all_review_ids = ["REV001", "REV002", "REV003", "REV004"]
read_ids = await repo.get_read_ids(all_review_ids)
print(f"Read reviews: {read_ids}")

# Check if specific review is read
is_read = await repo.is_read("REV001")
print(f"Is REV001 read? {is_read}")

# Mark all reviews as read
total = await repo.mark_all_as_read(read_by="system")
print(f"Marked {total} total reviews as read")
```

## 4. Database Schema

```
Table: review_read_status
├── id (SERIAL, PRIMARY KEY)
├── review_id (VARCHAR(255), UNIQUE, NOT NULL)
├── read_at (TIMESTAMP, DEFAULT now())
└── read_by (VARCHAR(100), NULLABLE)

Indexes:
└── idx_review_read_status_review_id (review_id)
```

## 5. Features

- **Batch Processing**: Handles large lists of review_ids in batches of 100
- **Upsert Logic**: Uses ON CONFLICT to prevent duplicates
- **Error Handling**: Logs warnings on failures, doesn't crash
- **Type Safety**: Full type hints for all methods
- **Follows Patterns**: Matches existing repository implementations
