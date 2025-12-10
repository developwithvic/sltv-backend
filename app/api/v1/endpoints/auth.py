from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from app.core import security
from app.core.config import settings
from app.repositories.user_repository import UserRepository
from app.api import deps
from app.schemas.user import UserRead
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

@router.post("/login/access-token", response_model=dict)
@limiter.limit("5/minute")
async def login_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    user_repo: UserRepository = Depends(deps.get_user_repository)
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = await user_repo.get_by_email(form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password",
        )
    elif not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    # Optional: Check if user is verified
    # if not user.is_verified:
    #     raise HTTPException(status_code=400, detail="Email not verified")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
        "name": user.full_name,
    }

@router.post("/verify-email")
async def verify_email(
    token: str,
    user_repo: UserRepository = Depends(deps.get_user_repository)
) -> Any:
    """
    Verify email address using token.
    """
    email = security.verify_email_token(token, "verification")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")

    user = await user_repo.get_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_verified:
        return {"message": "Email already verified"}

    user.is_verified = True
    await user_repo.update(user, {"is_verified": True})
    return {"message": "Email verified successfully"}

@router.post("/forgot-password")
async def forgot_password(
    email: str,
    background_tasks: BackgroundTasks,
    user_repo: UserRepository = Depends(deps.get_user_repository)
) -> Any:
    """
    Send password reset email.
    """
    user = await user_repo.get_by_email(email)
    if not user:
        # Don't reveal that the user doesn't exist
        return {"message": "If the email exists, a reset link has been sent."}

    token = security.create_email_token(email, "reset")
    from app.services.email_service import email_service
    reset_link = f"https://sltv-frontend.vercel.app/reset-password?token={token}"
    email_service.send_password_reset_email(background_tasks, email, user.full_name or "User", reset_link)

    return {"message": "If the email exists, a reset link has been sent."}

@router.post("/reset-password")
async def reset_password(
    token: str,
    new_password: str,
    user_repo: UserRepository = Depends(deps.get_user_repository)
) -> Any:
    """
    Reset password using token.
    """
    email = security.verify_email_token(token, "reset")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")

    user = await user_repo.get_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed_password = security.get_password_hash(new_password)
    user.hashed_password = hashed_password
    await user_repo.update(user, {"hashed_password": hashed_password})

    return {"message": "Password reset successfully"}
