from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import timedelta
from typing import Optional, Dict

from app.db import models
from app.utils.jwt_utils import create_access_token

# Password context for hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Hash password
    """
    return pwd_context.hash(password)

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """
    Get user by email
    """
    return db.query(models.User).filter(models.User.email == email).first()

def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """
    Authenticate a user with email and password
    """
    user = get_user_by_email(db, email)
    
    if not user:
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    return user

def create_user(db: Session, email: str, password: str, role: models.UserRole = models.UserRole.user) -> models.User:
    """
    Create a new user
    """
    hashed_password = get_password_hash(password)
    
    new_user = models.User(
        email=email,
        hashed_password=hashed_password,
        role=role
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

def generate_auth_token(user: models.User) -> Dict:
    """
    Generate authentication token for a user
    """
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }