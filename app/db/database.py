from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from dotenv import load_dotenv
import os


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

"""
-This is the core interface to the database, which creates a global instance of the database engine
-Creates and maintains the connection pool
-Handles low-level database operations
-Will be used to:
    Create database tables
    Manage connection pooling
-args
    DATABASE_URL: The URL to connect to the database
    pool_size=10: Maximum number of connections in pool
    max_overflow=20: Maximum overflow connections
    pool_timeout=30: Seconds to wait for a connection
    pool_recycle=1800: Recycle connections after 30 minutes
    pool_pre_ping=True: Verify connections before using
"""

engine = create_engine(
    DATABASE_URL,
    pool_size=10,               
    max_overflow=20,           
    pool_timeout=30,           
    pool_recycle=1800,          
    pool_pre_ping=True,         
)

"""
-Factory for creating database sessions
-Each session represents a "workspace" for database operations
-Manages database transactions
-Will be used to:
    Create new database sessions
    Perform CRUD operations
    Manage transactions
-args
    autocommit=False: Whether to commit after each transaction
    autoflush=False: Whether to flush the database after each transaction
    bind=engine: The engine to use for database operations
"""

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

"""
-Parent class for all database models, all models will inherit this as the base class
-Will be used to:
    create SQLAlchemy ORM models
    define database tables as classes
    define columns as class attributes
    define relationships between tables
"""

Base = declarative_base()

"""
-FastAPI dependency for database access
-Creates and manages database sessions for each request
-Ensures proper cleanup of database connections
"""

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""
Below is a code snippet to check if the database connection is working or not
Uncomment the code below and run this file to check the database connection
"""

"""
if __name__ == "__main__":
    with engine.connect() as connection:
        print("Database connection established successfully!")
        try:
            result = connection.execute(text("select 1"))
            print(result.all())
        except Exception as e:
            print("Database connection is not working")
            print(e)
        connection.close()
        print("Database connection closed")
"""

