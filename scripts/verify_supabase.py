#!/usr/bin/env python3
"""
Supabase Connection Verification Script
Tests connection and verifies tables/data after migration
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_supabase_connection():
    """Test connection to Supabase"""
    try:
        import psycopg2
        
        db_url = os.getenv("DB_URL")
        if not db_url:
            print("❌ ERROR: DB_URL not found in .env")
            return False
        
        print(f"🔄 Testing connection to Supabase...")
        print(f"   Connection string: {db_url[:50]}...")
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Test basic query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✓ Connected successfully!")
        print(f"  PostgreSQL Version: {version.split(',')[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def verify_tables():
    """Verify all required tables exist"""
    try:
        import psycopg2
        
        db_url = os.getenv("DB_URL")
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # List of expected tables
        expected_tables = [
            'roles', 'users', 'subjects', 'assessments', 
            'assessment_questions', 'moods', 'whitelist',
            'student_revisions', 'revision_content', 'system_settings'
        ]
        
        print("\n📋 Checking tables...")
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        all_exist = True
        for table in expected_tables:
            if table in existing_tables:
                print(f"  ✓ {table}")
            else:
                print(f"  ✗ {table} (MISSING)")
                all_exist = False
        
        cursor.close()
        conn.close()
        return all_exist
        
    except Exception as e:
        print(f"❌ Error checking tables: {e}")
        return False


def count_records():
    """Count records in main tables"""
    try:
        import psycopg2
        
        db_url = os.getenv("DB_URL")
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        print("\n📊 Record counts...")
        tables = ['roles', 'users', 'subjects', 'assessments', 'moods']
        
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table}: {count} records")
            except Exception as e:
                print(f"  {table}: Error - {str(e)[:50]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error counting records: {e}")


def main():
    """Run all verification checks"""
    print("=" * 60)
    print("🔍 Supabase Migration Verification")
    print("=" * 60)
    
    # Step 1: Test connection
    if not test_supabase_connection():
        print("\n⚠️  Update your .env file with valid Supabase credentials:")
        print("   - DB_HOST: xxxx.pooler.supabase.com")
        print("   - DB_PASSWORD: Your Supabase password")
        print("   - DB_URL: Full connection string")
        return 1
    
    # Step 2: Verify tables
    if not verify_tables():
        print("\n⚠️  Some tables are missing. Run migrations:")
        print("   1. Go to Supabase SQL Editor")
        print("   2. Run: migrations/schema_changes.sql")
        print("   3. Run: migrations/seed_changes.sql")
        print("   4. Re-run this script")
    else:
        print("\n✅ All tables present!")
    
    # Step 3: Count records
    count_records()
    
    print("\n" + "=" * 60)
    print("✅ Verification complete!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
