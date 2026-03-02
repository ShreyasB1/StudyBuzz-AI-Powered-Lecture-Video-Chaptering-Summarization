#!/usr/bin/env python3
"""
Test script to verify database integration.
Run this after starting the database with: make run-db
"""

import sys
import db_helper

def test_connection():
    """Test database connection."""
    print("Testing database connection...")
    try:
        with db_helper.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()
                print(f"✓ Connected to: {version['version']}")
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


def test_tables():
    """Test that required tables exist."""
    print("\nChecking tables...")
    try:
        with db_helper.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name;
                """)
                tables = [row['table_name'] for row in cur.fetchall()]
                
                required = ['lecture_videos', 'chapter_embeddings']
                for table in required:
                    if table in tables:
                        print(f"✓ Table '{table}' exists")
                    else:
                        print(f"✗ Table '{table}' missing")
                        return False
        return True
    except Exception as e:
        print(f"✗ Table check failed: {e}")
        return False


def test_insert_video():
    """Test inserting a video record."""
    print("\nTesting video insertion...")
    try:
        test_hash = "test_hash_123456789"
        video_id = db_helper.insert_video(
            video_hash=test_hash,
            folder_path="/test/path",
            video_name="test_video.mp4",
            note="Test video"
        )
        print(f"✓ Inserted video with ID: {video_id}")
        
        # Verify retrieval
        video = db_helper.get_video_by_hash(test_hash)
        if video:
            print(f"✓ Retrieved video: {video['video_name']}")
        else:
            print("✗ Failed to retrieve video")
            return False
            
        # Clean up
        with db_helper.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM lecture_videos WHERE video_hash = %s", (test_hash,))
                conn.commit()
        print("✓ Test data cleaned up")
        
        return True
    except Exception as e:
        print(f"✗ Video insertion failed: {e}")
        return False


def test_pgvector():
    """Test pgvector extension."""
    print("\nTesting pgvector extension...")
    try:
        with db_helper.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
                result = cur.fetchone()
                if result:
                    print(f"✓ pgvector extension is installed")
                    return True
                else:
                    print("✗ pgvector extension not found")
                    return False
    except Exception as e:
        print(f"✗ pgvector check failed: {e}")
        return False


def main():
    print("=" * 60)
    print("StudyBuzz Database Integration Test")
    print("=" * 60)
    
    tests = [
        test_connection,
        test_tables,
        test_pgvector,
        test_insert_video,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        if test():
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed > 0:
        print("\n⚠️  Some tests failed. Check your database setup:")
        print("1. Ensure database is running: make run-db")
        print("2. Initialize schema: python init_db.py")
        sys.exit(1)
    else:
        print("\n✅ All tests passed! Database is ready.")
        sys.exit(0)


if __name__ == "__main__":
    main()
