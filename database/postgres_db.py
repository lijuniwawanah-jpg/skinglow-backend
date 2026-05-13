# database/postgres_db.py
import os
import asyncpg
import logging
import sqlite3
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Get DATABASE_URL from Railway (auto-provided) or local
DATABASE_URL = os.getenv('DATABASE_URL', '')

# Kama DATABASE_URL ipo, tumia PostgreSQL, else tumia SQLite
USE_POSTGRES = bool(DATABASE_URL)

if not USE_POSTGRES:
    logger.info("Using SQLite database (local development)")
    SQLITE_DB_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'skinglow.db')
    
    @asynccontextmanager
    async def get_db():
        """Get SQLite connection (for local development)"""
        import aiosqlite
        
        conn = await aiosqlite.connect(SQLITE_DB_FILE)
        conn.row_factory = sqlite3.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
        finally:
            await conn.close()
    
    async def init_db():
        """Initialize SQLite tables (local development)"""
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
        logger.info("✅ SQLite database initialized successfully!")
    
    async def migrate_data():
        logger.info("No migration needed for SQLite")
        return

else:
    logger.info(f"Using PostgreSQL database")
    
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
        """Initialize PostgreSQL database tables"""
        conn = await asyncpg.connect(DATABASE_URL)
        
        try:
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
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    skin_type TEXT NOT NULL,
                    skin_name TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    characteristics TEXT,
                    recommendations TEXT,
                    recommended_oils TEXT,
                    products TEXT,
                    method TEXT,
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Chat history table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    user_message TEXT NOT NULL,
                    assistant_response TEXT NOT NULL,
                    provider TEXT,
                    skin_context TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id)')
            
            logger.info("✅ PostgreSQL database initialized successfully!")
            
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise
        finally:
            await conn.close()
    
    async def migrate_data():
        """Migrate data from SQLite to PostgreSQL if needed"""
        import os
        sqlite_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'skinglow.db')
        
        if not os.path.exists(sqlite_path):
            logger.info("No SQLite database found to migrate")
            return
        
        logger.info("Starting data migration from SQLite to PostgreSQL...")
        
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        pg_conn = await asyncpg.connect(DATABASE_URL)
        
        try:
            # Check if users already exist
            existing_users = await pg_conn.fetchval("SELECT COUNT(*) FROM users")
            if existing_users > 0:
                logger.info(f"PostgreSQL already has {existing_users} users, skipping migration")
                return
            
            # Migrate users
            users = sqlite_conn.execute("SELECT * FROM users").fetchall()
            for user in users:
                await pg_conn.execute('''
                    INSERT INTO users (id, email, password_hash, name, role, is_approved, 
                                       phone, address, profile_image, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (id) DO NOTHING
                ''', user['id'], user['email'], user['password_hash'], user['name'],
                    user['role'], user['is_approved'], user['phone'], user['address'],
                    user.get('profile_image'), user['created_at'])
            
            logger.info(f"✅ Migrated {len(users)} users")
            
            # Migrate analyses
            analyses = sqlite_conn.execute("SELECT * FROM analyses").fetchall()
            for analysis in analyses:
                await pg_conn.execute('''
                    INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence,
                                          characteristics, recommendations, recommended_oils, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id) DO NOTHING
                ''', analysis['id'], analysis['user_id'], analysis['skin_type'],
                    analysis['skin_name'], analysis['confidence'], analysis['characteristics'],
                    analysis['recommendations'], analysis['recommended_oils'], analysis['created_at'])
            
            logger.info(f"✅ Migrated {len(analyses)} analyses")
            
            logger.info("✅ Data migration completed successfully!")
            
        except Exception as e:
            logger.error(f"Migration error: {e}")
        finally:
            sqlite_conn.close()
            await pg_conn.close()