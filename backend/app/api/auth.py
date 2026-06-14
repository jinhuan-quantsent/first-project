"""
认证 API 路由
V4.0：Supabase Auth 作为身份源 + 后端自签 JWT
端点：register / login / logout / verify-email
"""
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.core.auth import create_access_token
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["认证"])


# ============================================================
# 请求/响应模型
# ============================================================
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    token: str


class UserInfo(BaseModel):
    user_id: str
    email: str
    created_at: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo


class VerifyEmailResponse(BaseModel):
    access_token: str
    user_id: str


# ============================================================
# 密码强度校验
# ============================================================
def _validate_password(password: str) -> Optional[str]:
    if len(password) < 8:
        return "密码长度至少 8 位"
    if not re.search(r"[A-Za-z]", password):
        return "密码需包含字母"
    if not re.search(r"\d", password):
        return "密码需包含数字"
    return None


# ============================================================
# Supabase Auth 客户端
# ============================================================
def _get_supabase_client():
    """懒加载 Supabase 客户端"""
    try:
        from supabase import create_client
        return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": 50301, "data": None, "message": f"认证服务不可用: {e}"},
        )


# ============================================================
# POST /auth/register
# ============================================================
@router.post("/register", status_code=status.HTTP_201)
async def register(req: RegisterRequest) -> dict:
    """用户注册（通过 Supabase Auth）"""
    # AUTH_DISABLED 模式不允许注册
    if settings.AUTH_DISABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40301, "data": None, "message": "当前认证已禁用"},
        )

    # 密码强度校验
    pwd_err = _validate_password(req.password)
    if pwd_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40001, "data": None, "message": pwd_err},
        )

    supabase = _get_supabase_client()

    try:
        response = supabase.auth.sign_up_with_email(
            email=req.email,
            password=req.password,
        )
    except Exception as e:
        err_msg = str(e).lower()
        if "already" in err_msg or "registered" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": 40901, "data": None, "message": "邮箱已注册"},
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 50001, "data": None, "message": f"注册失败: {e}"},
        )

    user = response.user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 50001, "data": None, "message": "注册失败：未获取到用户信息"},
        )

    return {
        "code": 0,
        "data": {
            "user_id": user.id,
            "email": user.email,
            "email_confirmed": bool(user.email_confirmed_at),
            "message": "注册成功，请查收验证邮件" if not user.email_confirmed_at else "注册成功",
        },
        "message": "ok",
    }


# ============================================================
# POST /auth/login
# ============================================================
@router.post("/login")
async def login(req: LoginRequest) -> dict:
    """用户登录（通过 Supabase Auth，后端自签 JWT）"""
    if settings.AUTH_DISABLED:
        # 降级模式：直接签发 demo_user token
        token = create_access_token("demo_user", "demo@localhost")
        return {
            "code": 0,
            "data": {
                "access_token": token,
                "token_type": "bearer",
                "expires_in": settings.JWT_EXPIRE_SECONDS,
                "user": {
                    "user_id": "demo_user",
                    "email": "demo@localhost",
                    "created_at": None,
                },
            },
            "message": "ok",
        }

    supabase = _get_supabase_client()

    try:
        response = supabase.auth.sign_in_with_password(
            email=req.email,
            password=req.password,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40101, "data": None, "message": "邮箱或密码错误"},
        )

    user = response.user
    session = response.session
    if not user or not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40101, "data": None, "message": "邮箱或密码错误"},
        )

    # 后端自签 JWT
    access_token = create_access_token(
        user_id=user.id,
        email=user.email or "",
    )

    return {
        "code": 0,
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_EXPIRE_SECONDS,
            "user": {
                "user_id": user.id,
                "email": user.email or "",
                "created_at": str(user.created_at) if user.created_at else None,
            },
        },
        "message": "ok",
    }


# ============================================================
# POST /auth/logout
# ============================================================
@router.post("/logout")
async def logout() -> dict:
    """用户登出（客户端清除 token 即可，服务端无状态）"""
    return {
        "code": 0,
        "data": None,
        "message": "登出成功",
    }


# ============================================================
# POST /auth/verify-email
# ============================================================
@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest) -> dict:
    """邮箱验证（验证 Supabase OTP 后签发 JWT）"""
    if settings.AUTH_DISABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40301, "data": None, "message": "当前认证已禁用"},
        )

    supabase = _get_supabase_client()

    try:
        response = supabase.auth.verify_otp(
            email=req.email,
            token=req.token,
            type="email",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40001, "data": None, "message": f"验证失败: {e}"},
        )

    user = response.user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40001, "data": None, "message": "验证失败：无效的验证信息"},
        )

    access_token = create_access_token(
        user_id=user.id,
        email=user.email or "",
    )

    return {
        "code": 0,
        "data": {
            "access_token": access_token,
            "user_id": user.id,
        },
        "message": "邮箱验证成功",
    }
