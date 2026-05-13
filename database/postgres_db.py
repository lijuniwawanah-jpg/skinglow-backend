# database/postgres_db.py
import os
import sys
import logging
from contextlib import asynccontextmanager

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import asyncpg for PostgreSQL
try:
    import asyncpg
    HAS_PG = True
except ImportError:
    HAS_PG = False
    import aiosqlite
    import sqlite3

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv('DATABASE_URL', '')

# Check if we should use PostgreSQL (only on Railway with DATABASE_URL)
USE_POSTGRES = HAS_PG and bool(DATABASE_URL) and 'railway' in DATABASE_URL.lower()

if USE_POSTGRES:
    logger.info("✅ Using PostgreSQL database (Railway production)")
    
    @asynccontextmanager
    async def get_db():
        """Get PostgreSQL connection"""
        conn = None
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            yield conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                await conn.close()
    
    async def init_db():
        """Initialize PostgreSQL tables"""
        conn = await asyncpg.connect(DATABASE_URL)
        
        try:
            # USERS TABLE
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT,
                    role TEXT DEFAULT 'customer',
                    is_approved INTEGER DEFAULT 0,
                    phone TEXT,
                    address TEXT,
                    latitude REAL,
                    longitude REAL,
                    profile_image TEXT,
                    fcm_token TEXT,
                    email_verified INTEGER DEFAULT 0,
                    verification_token TEXT,
                    reset_token TEXT,
                    reset_token_expiry TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            ''')
            
            # ANALYSES TABLE
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    skin_type TEXT NOT NULL,
                    skin_name TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    characteristics TEXT,
                    recommendations TEXT,
                    recommended_oils TEXT,
                    products TEXT,
                    method TEXT,
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # CHAT HISTORY TABLE
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    assistant_response TEXT NOT NULL,
                    provider TEXT,
                    skin_context TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Create indexes
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)')
            
            logger.info("✅ PostgreSQL tables created successfully!")
            
        except Exception as e:
            logger.error(f"Database init error: {e}")
            raise
        finally:
            await conn.close()
    
    async def migrate_data():
        """Migrate existing SQLite data to PostgreSQL"""
        import aiosqlite
        import os
        
        sqlite_path = 'skinglow.db'
        if not os.path.exists(sqlite_path):
            logger.info("No SQLite database found, skipping migration")
            return
        
        # Check if PostgreSQL already has users
        pg_conn = await asyncpg.connect(DATABASE_URL)
        try:
            user_count = await pg_conn.fetchval("SELECT COUNT(*) FROM users")
            if user_count > 0:
                logger.info(f"PostgreSQL already has {user_count} users, skipping migration")
                return
        finally:
            await pg_conn.close()
        
        logger.info("Migrating data from SQLite to PostgreSQL...")
        
        sqlite_conn = await aiosqlite.connect(sqlite_path)
        sqlite_conn.row_factory = aiosqlite.Row
        pg_conn = await asyncpg.connect(DATABASE_URL)
        
        try:
            # Migrate users
            users = await sqlite_conn.execute("SELECT * FROM users")
            users_list = await users.fetchall()
            
            for user in users_list:
                await pg_conn.execute('''
                    INSERT INTO users (id, email, password_hash, name, role, is_approved, 
                                       phone, address, profile_image, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (id) DO NOTHING
                ''', user['id'], user['email'], user['password_hash'], user['name'],
                    user['role'], user['is_approved'], user['phone'], user['address'],
                    user.get('profile_image'), user['created_at'])
            
            logger.info(f"✅ Migrated {len(users_list)} users")
            
            # Migrate analyses
            analyses = await sqlite_conn.execute("SELECT * FROM analyses")
            analyses_list = await analyses.fetchall()
            
            for analysis in analyses_list:
                await pg_conn.execute('''
                    INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence,
                                          characteristics, recommendations, recommended_oils, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id) DO NOTHING
                ''', analysis['id'], analysis['user_id'], analysis['skin_type'],
                    analysis['skin_name'], analysis['confidence'], analysis['characteristics'],
                    analysis['recommendations'], analysis['recommended_oils'], analysis['created_at'])
            
            logger.info(f"✅ Migrated {len(analyses_list)} analyses")
            logger.info("✅ Data migration completed!")
            
        except Exception as e:
            logger.error(f"Migration error: {e}")
        finally:
            await sqlite_conn.close()
            await pg_conn.close()

else:
    logger.info("✅ Using SQLite database (local development)")
    
    SQLITE_DB_FILE = "skinglow.db"
    
    @asynccontextmanager
    async def get_db():
        """Get SQLite connection"""
        import aiosqlite
        
        conn = await aiosqlite.connect(SQLITE_DB_FILE)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
        finally:
            await conn.close()
    
    async def init_db():
        """Initialize SQLite tables"""
        import aiosqlite
        
        conn = await aiosqlite.connect(SQLITE_DB_FILE)
        
        # Users table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                role TEXT DEFAULT 'customer',
                is_approved INTEGER DEFAULT 0,
                phone TEXT,
                address TEXT,
                latitude REAL,
                longitude REAL,
                profile_image TEXT,
                fcm_token TEXT,
                email_verified INTEGER DEFAULT 0,
                verification_token TEXT,
                reset_token TEXT,
                reset_token_expiry TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # Analyses table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                skin_type TEXT NOT NULL,
                skin_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                characteristics TEXT,
                recommendations TEXT,
                recommended_oils TEXT,
                products TEXT,
                method TEXT,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # Chat history table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                assistant_response TEXT NOT NULL,
                provider TEXT,
                skin_context TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        await conn.commit()
        await conn.close()
        logger.info("✅ SQLite tables created successfully!")
    
    async def migrate_data():
        """No migration needed for SQLite"""
        logger.info("Using SQLite, no migration needed")
        return
