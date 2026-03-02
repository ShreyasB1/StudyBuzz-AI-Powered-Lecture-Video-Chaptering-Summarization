# Database Integration Quick Start

## Overview

StudyBuzz now includes PostgreSQL with pgvector for:
- **Video deduplication** - Avoid reprocessing the same video
- **Processing history** - Track all videos and their status
- **Chapter embeddings** - Future semantic search capabilities

## Local Development Setup

### 1. Start the database
```bash
make run-db
```

This starts PostgreSQL on `localhost:5432` with:
- Database: `vip_db`
- User: `postgres`
- Password: `postgres`
- Data persists in `./postgres-data/`

### 2. Initialize the schema
```bash
python init_db.py
```

This creates:
- `lecture_videos` table - Video metadata and processing status
- `chapter_embeddings` table - Vector embeddings for similarity search
- pgvector extension and indexes

### 3. Test the integration
```bash
python test_db.py
```

This verifies:
- ✓ Database connection
- ✓ Tables exist
- ✓ pgvector extension loaded
- ✓ CRUD operations work

### 4. Start your app
```bash
# Option A: Just the Flask app (connects to existing DB)
make run-app

# Option B: Full pod deployment with all services
make deploy
```

## PACE Production Setup

The database is **automatically set up** when you launch a session on PACE:

1. PostgreSQL container starts in the pod
2. `init_db.py` runs automatically
3. Your app connects to `localhost:5432` inside the pod

No manual steps required! 🎉

## Database Inspection

### Using psql (local)
```bash
psql -h localhost -p 5432 -U postgres -d vip_db
```

### Common queries
```sql
-- List all processed videos
SELECT video_name, done_processing, video_date 
FROM lecture_videos 
ORDER BY video_date DESC;

-- Count videos by status
SELECT done_processing, COUNT(*) 
FROM lecture_videos 
GROUP BY done_processing;

-- Check chapter embeddings
SELECT COUNT(*) as total_embeddings 
FROM chapter_embeddings;

-- Find videos by name pattern
SELECT * FROM lecture_videos 
WHERE video_name LIKE '%lecture%';
```

### Using the API
```bash
# Check health (includes DB status)
curl http://localhost:5000/api/health

# List all videos in database
curl http://localhost:5000/api/database/videos
```

## How It Works

### Video Upload Flow

1. **Video uploaded** → Flask computes SHA256 hash
2. **Check database** → Is this video already processed?
   - If yes → Skip processing, return cached results
   - If no → Insert record, mark as `done_processing=false`
3. **Processing starts** → Pipeline runs (transcription, chapters, summaries)
4. **Processing complete** → Update `done_processing=true`

### Database Schema

```sql
-- Video metadata
CREATE TABLE lecture_videos (
    id              BIGSERIAL PRIMARY KEY,
    video_hash      TEXT UNIQUE NOT NULL,     -- SHA256 hash
    done_processing BOOLEAN NOT NULL DEFAULT FALSE,
    note            TEXT,
    folder_path     TEXT NOT NULL,
    video_name      TEXT NOT NULL,
    video_date      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Chapter embeddings (for future semantic search)
CREATE TABLE chapter_embeddings (
    id              BIGSERIAL PRIMARY KEY,
    video_hash      TEXT NOT NULL REFERENCES lecture_videos(video_hash),
    chapter_path    TEXT NOT NULL,
    model_name      TEXT NOT NULL,
    embedding       VECTOR(1536) NOT NULL,    -- 1536-dim vector
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (video_hash, chapter_path, model_name)
);
```

## Troubleshooting

### "Database not available" in health check
- Ensure `make run-db` is running
- Check connection: `psql -h localhost -p 5432 -U postgres -d vip_db`
- Verify port 5432 isn't blocked or in use

### "relation does not exist" errors
- Run `python init_db.py` to create tables
- Verify with: `psql -h localhost -p 5432 -U postgres -d vip_db -c "\dt"`

### On PACE: Can't connect to database
- Database is only accessible inside the pod (internal only)
- SSH into compute node: `ssh <hostname from session>`
- Use: `podman exec -it studybuzz-postgres-<SLURM_JOB_ID> psql -U postgres -d vip_db`

### Data persists between restarts?
- **Local (`make run-db`)**: Yes, in `./postgres-data/`
- **PACE**: No, data is lost when SLURM job ends (by design)
  - For persistent storage on PACE, mount a network volume

## Next Steps

### Future Enhancements

1. **Semantic Chapter Search**
   - Generate embeddings for each chapter using Mistral
   - Store in `chapter_embeddings` table
   - Query: "Find chapters about machine learning"

2. **User Management**
   - Add user authentication
   - Track which user uploaded which video

3. **Analytics Dashboard**
   - Processing statistics
   - Most popular videos
   - Average processing time

4. **Persistent Storage on PACE**
   - Mount shared network volume for postgres-data
   - Keep database across SLURM sessions

## Helper Scripts

- `init_db.py` - Create database schema
- `test_db.py` - Verify database integration
- `db_helper.py` - Database utility functions (import in your code)

## Environment Variables

Override defaults if needed:

```bash
export VIP_DB_NAME="vip_db"
export VIP_DB_USER="postgres"
export VIP_DB_PASSWORD="postgres"
export VIP_DB_HOST="localhost"
export VIP_DB_PORT="5432"
```
