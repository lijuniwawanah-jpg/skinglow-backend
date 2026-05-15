# database/postgres_db.py
import os
import asyncpg
import logging
import bcrypt
import uuid
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# ============================================
# SECURITY FUNCTIONS (Defined here for database module)
# ============================================

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password using bcrypt"""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except:
        return False

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    logger.warning("DATABASE_URL not set, using local SQLite fallback")
    # Fallback to SQLite for local development
    import aiosqlite
    
    SQLITE_DB_FILE = "skinglow.db"
    
    @asynccontextmanager
    async def get_db():
        conn = await aiosqlite.connect(SQLITE_DB_FILE)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            await conn.close()
    
    async def init_db():
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
        
        # Skin questionnaires table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS skin_questionnaires (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                self_assessed_skin_type TEXT NOT NULL,
                calculated_skin_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                matching_percentage REAL NOT NULL,
                oiliness INTEGER,
                dryness INTEGER,
                sensitivity INTEGER,
                acne_frequency INTEGER,
                redness INTEGER,
                pores_size INTEGER,
                texture INTEGER,
                uses_sunscreen INTEGER DEFAULT 0,
                questionnaire_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        await conn.commit()
        await conn.close()
        logger.info("✅ SQLite tables created")
    
    async def migrate_data():
        pass
    
    logger.info("Using SQLite database (local development)")

else:
    logger.info(f"✅ Connected to PostgreSQL database")
    
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
            
            # STORES TABLE
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS stores (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    address TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    phone TEXT,
                    logo_url TEXT,
                    banner_url TEXT,
                    rating REAL DEFAULT 0,
                    total_reviews INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    is_verified INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # PRODUCTS TABLE
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    store_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    price REAL NOT NULL,
                    compare_price REAL,
                    category TEXT,
                    skin_type TEXT,
                    images TEXT,
                    stock INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0,
                    total_reviews INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    is_approved INTEGER DEFAULT 0,
                    is_sponsored INTEGER DEFAULT 0,
                    views INTEGER DEFAULT 0,
                    sales_count INTEGER DEFAULT 0,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # ORDERS TABLE
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    order_number TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    total_amount REAL NOT NULL,
                    subtotal REAL NOT NULL,
                    tax REAL DEFAULT 0,
                    shipping_cost REAL DEFAULT 0,
                    discount REAL DEFAULT 0,
                    payment_method TEXT,
                    payment_status TEXT DEFAULT 'pending',
                    delivery_address TEXT,
                    delivery_latitude REAL,
                    delivery_longitude REAL,
                    tracking_number TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # ORDER ITEMS TABLE
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS order_items (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    total REAL NOT NULL
                )
            ''')
            
            # REVIEWS TABLE
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT,
                    images TEXT,
                    is_verified_purchase INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, product_id)
                )
            ''')
            
            # SKIN QUESTIONNAIRES TABLE (FIXED - Now properly indented)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS skin_questionnaires (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    self_assessed_skin_type TEXT NOT NULL,
                    calculated_skin_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    matching_percentage REAL NOT NULL,
                    oiliness INTEGER,
                    dryness INTEGER,
                    sensitivity INTEGER,
                    acne_frequency INTEGER,
                    redness INTEGER,
                    pores_size INTEGER,
                    texture INTEGER,
                    uses_sunscreen INTEGER DEFAULT 0,
                    questionnaire_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # NOTIFICATIONS TABLE
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    type TEXT DEFAULT 'info',
                    is_read INTEGER DEFAULT 0,
                    data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_products_store_id ON products(store_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_reviews_product_id ON reviews(product_id)')
            
            logger.info("✅ PostgreSQL tables created successfully!")
            
            # Check if tables are empty, create default admin
            user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            if user_count == 0:
                admin_id = str(uuid.uuid4())
                admin_email = os.getenv('ADMIN_EMAIL', 'admin@skinglow.com')
                admin_password = os.getenv('ADMIN_PASSWORD', 'Admin@123')
                password_hash = hash_password(admin_password)
                
                await conn.execute('''
                    INSERT INTO users (id, email, password_hash, name, role, is_approved, email_verified)
                    VALUES ($1, $2, $3, $4, 'admin', 1, 1)
                ''', admin_id, admin_email, password_hash, "Super Admin")
                logger.info(f"✅ Default admin user created: {admin_email}")
            
        except Exception as e:
            logger.error(f"Database init error: {e}")
            raise
        finally:
            await conn.close()
    
    async def migrate_data():
        """Migrate existing SQLite data to PostgreSQL"""
        import aiosqlite
        import os
        
        # Check if SQLite exists and has data
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
        
        logger.info("Starting data migration from SQLite to PostgreSQL...")
        
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
            
            # Migrate chat history
            chats = await sqlite_conn.execute("SELECT * FROM chat_history")
            chats_list = await chats.fetchall()
            
            for chat in chats_list:
                await pg_conn.execute('''
                    INSERT INTO chat_history (id, user_id, user_message, assistant_response, provider, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO NOTHING
                ''', chat['id'], chat['user_id'], chat['user_message'],
                    chat['assistant_response'], chat.get('provider'), chat['created_at'])
            
            logger.info(f"✅ Migrated {len(chats_list)} chat messages")
            logger.info("✅ Data migration completed!")
            
        except Exception as e:
            logger.error(f"Migration error: {e}")
        finally:
            await sqlite_conn.close()
            await pg_conn.close()