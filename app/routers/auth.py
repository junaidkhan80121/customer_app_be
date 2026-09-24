from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser
from app.schemas import AdminCreate, AdminOut, AdminUpdate, LoginRequest, TokenResponse
from app.security import create_access_token, get_current_admin, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login_json(body: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    admin = db.scalar(select(AdminUser).where(AdminUser.email == body.email.lower()))
    if not admin or not admin.is_active or not verify_password(body.password, admin.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(str(admin.id)))


@router.post("/auth/login-form", response_model=TokenResponse, include_in_schema=False)
def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    admin = db.scalar(select(AdminUser).where(AdminUser.email == form.username.lower()))
    if not admin or not admin.is_active or not verify_password(form.password, admin.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(str(admin.id)))


@router.get("/auth/me", response_model=AdminOut)
def me(admin: Annotated[AdminUser, Depends(get_current_admin)]) -> AdminUser:
    return admin


@router.get("/admins", response_model=list[AdminOut])
def list_admins(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> list[AdminUser]:
    return list(db.scalars(select(AdminUser).order_by(AdminUser.created_at)).all())


@router.post("/admins", response_model=AdminOut, status_code=status.HTTP_201_CREATED)
def create_admin(
    body: AdminCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> AdminUser:
    email = body.email.lower()
    if db.scalar(select(AdminUser).where(AdminUser.email == email)):
        raise HTTPException(status_code=400, detail="Email already registered")
    admin = AdminUser(email=email, name=body.name, hashed_password=hash_password(body.password))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@router.patch("/admins/{admin_id}", response_model=AdminOut)
def update_admin(
    admin_id: str,
    body: AdminUpdate,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[AdminUser, Depends(get_current_admin)],
) -> AdminUser:
    admin = db.get(AdminUser, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    if body.is_active is False and admin.id == current.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    if body.is_active is False:
        active_count = db.scalar(
            select(func.count()).select_from(AdminUser).where(AdminUser.is_active.is_(True))
        )
        if active_count <= 1 and admin.is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last active admin")
    if body.name is not None:
        admin.name = body.name
    if body.password is not None:
        admin.hashed_password = hash_password(body.password)
    if body.is_active is not None:
        admin.is_active = body.is_active
    db.commit()
    db.refresh(admin)
    return admin
