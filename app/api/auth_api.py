from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError
from pydantic import BaseModel, EmailStr
from typing import Optional
import os

from app.db.database import get_db
from app.db import models
from app.services.auth_service import authenticate_user, create_user, get_user_by_email
from app.utils.jwt_utils import create_access_token, decode_token

# Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class AdminCreate(UserCreate):
    admin_secret: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    
    class Config:
        from_attributes = True

# OAuth2 scheme for token validation
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Setup auth router
router = APIRouter(prefix="/auth", tags=["Authentication"])

# Dependencies
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Get current user from JWT token
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_token(token)
        email: str = payload.get("sub")
        
        if email is None:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
        
    user = get_user_by_email(db, email)
    
    if user is None:
        raise credentials_exception
        
    return user

async def get_current_admin(current_user: models.User = Depends(get_current_user)):
    """
    Check if current user is admin
    """
    if current_user.role != models.UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return current_user

# Routes
@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user
    """
    existing_user = get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    user = create_user(db, user_data.email, user_data.password)
    return user

@router.post("/admin/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def admin_signup(admin_data: AdminCreate, db: Session = Depends(get_db)):
    """
    Create a new admin user with secret key verification
    """
    # Verify admin secret
    admin_secret = os.getenv("ADMIN_SECRET_KEY")
    if not admin_secret or admin_data.admin_secret != admin_secret:
        # Use a generic error message to avoid revealing if the secret exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin secret key"
        )
    
    # Check if user already exists
    existing_user = get_user_by_email(db, admin_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create admin user
    user = create_user(db, admin_data.email, admin_data.password, role=models.UserRole.admin)
    return user

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Authenticate and get token
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email})
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(current_user: models.User = Depends(get_current_user)):
    """
    Logout user
    
    Note: JWT tokens cannot be invalidated on the server side,
    so this endpoint is mostly for client-side cleanup.
    """
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: models.User = Depends(get_current_user)):
    """
    Get current user information
    """
    return current_user