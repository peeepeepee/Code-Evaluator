# Description: This script creates all the tables in the database.
# It is used to create the tables in the database when the application is first run.
# It is also used to create the tables in the database when the application is deployed to a new environment.
import sys
import os

# Add the current directory to the system path
sys.path.append(os.getcwd())


from app.db.database import engine
from app.db.models import Base

"""
-The Base class is the parent class for all database models
-It tracks all the tables in the database
-Base.metadata has the table definitions registered
-Base.metadata.create_all() creates all the tables in the database
"""

def create_all_tables():
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")

if __name__ == "__main__":
    create_all_tables()