from fastapi import APIRouter, Depends

from models.schemas import AuthRequest, AuthResponse, RegisterRequest, UserPublic
from services.auth_service import authenticate_user, create_token, create_user, current_user

router = APIRouter()


@router.post("/api/auth/register", response_model=AuthResponse)
async def register(payload: RegisterRequest):
    user = create_user(payload.name, payload.email, payload.mobile, payload.password)
    return AuthResponse(token=create_token(user["id"]), user=UserPublic(**user))


@router.post("/api/auth/login", response_model=AuthResponse)
async def login(payload: AuthRequest):
    user = authenticate_user(payload.identifier, payload.password)
    return AuthResponse(token=create_token(user["id"]), user=UserPublic(**user))


@router.get("/api/auth/me", response_model=UserPublic)
async def me(user: dict[str, str] = Depends(current_user)):
    return UserPublic(**user)
