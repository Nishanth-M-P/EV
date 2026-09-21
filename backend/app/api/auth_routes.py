from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.app.database.database import get_db
from backend.app.services.auth_service import AuthService
from backend.app.models.database_models import User

class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: Optional[bool] = False

class ForgotPasswordRequest(BaseModel):
    email: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool

class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: UserResponse
    message: str = "Login successful"

def get_token_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()
    return authorization

def get_current_user(
    token: Optional[str] = Depends(get_token_from_header),
    db: Session = Depends(get_db)
) -> User:
    """Dependency enforcing valid authentication."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required"
        )
    user = AuthService.get_user_by_token(db, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token"
        )
    return user

def get_optional_user(
    token: Optional[str] = Depends(get_token_from_header),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Dependency allowing optional authentication (maintains backwards compatibility)."""
    if not token:
        return None
    return AuthService.get_user_by_token(db, token)

def create_auth_router():
    router = APIRouter(prefix="/api/auth", tags=["Authentication"])

    @router.post("/login", response_model=LoginResponse)
    def login(req: LoginRequest, db: Session = Depends(get_db)):
        result = AuthService.authenticate(db, req.username, req.password)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username/email or password"
            )
        user, token = result
        return LoginResponse(
            token=token,
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                role=user.role or "admin",
                is_active=user.is_active
            ),
            message="Authenticated successfully"
        )

    @router.post("/logout")
    def logout(
        token: Optional[str] = Depends(get_token_from_header),
        db: Session = Depends(get_db)
    ):
        if token:
            AuthService.logout(db, token)
        return {"status": "success", "message": "Logged out successfully"}

    @router.get("/me", response_model=UserResponse)
    def get_me(current_user: User = Depends(get_current_user)):
        return UserResponse(
            id=current_user.id,
            username=current_user.username,
            email=current_user.email,
            role=current_user.role or "admin",
            is_active=current_user.is_active
        )

    @router.post("/forgot-password")
    def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
        # For demo/local enterprise simulator, simulate standard reset link notification
        return {
            "status": "success",
            "message": f"Password reset instructions have been dispatched to {req.email}. Default credentials: admin@gridwise.ai / GridWise@2026"
        }

    return router
