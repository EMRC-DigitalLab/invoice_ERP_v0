from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_user_from_refresh_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    AuthData,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled.",
        )
    return LoginResponse(
        data=AuthData(
            user=UserOut.model_validate(user),
            token=create_access_token({"sub": user.id}),
            refresh_token=create_refresh_token({"sub": user.id}),
        )
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    user = get_user_from_refresh_token(body.refresh_token, db)
    return LoginResponse(
        data=AuthData(
            user=UserOut.model_validate(user),
            token=create_access_token({"sub": user.id}),
            # Rotated on every use — extends the session while it's actively used,
            # and limits how long a leaked refresh token stays valid unused.
            refresh_token=create_refresh_token({"sub": user.id}),
        )
    )
