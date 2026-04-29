import os
import random
import logging
import datetime

import bcrypt
import jwt
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app.database import users_collection
from app.email_sender import EmailSender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

JWT_SECRET = os.getenv("JWT_SECRET", "autoppia-automata-secret-key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7



# ── Request models ───────────────────────────────────────────────

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    verification_code: str


class ResendOTPRequest(BaseModel):
    email: EmailStr


class GoogleAuthRequest(BaseModel):
    access_token: str


class ChangePasswordRequest(BaseModel):
    email: EmailStr
    current_password: str
    new_password: str


# ── Helpers ──────────────────────────────────────────────────────

def _create_token(email: str) -> str:
    payload = {
        "email": email,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=JWT_EXPIRATION_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _generate_verification_code() -> str:
    return str(random.randint(100000, 999999))


def _send_otp_email(email: str, code: str) -> None:
    sender = EmailSender()
    sender.send_email(
        email,
        "Automata - Account Verification",
        f"Your verification code is: {code}. This code will expire in 1 minute.",
    )


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/signup")
async def signup(body: SignUpRequest):
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    existing = await users_collection.find_one({"email": body.email})

    hashed = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt())
    code = _generate_verification_code()
    expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=1)

    if existing:
        if existing.get("is_verified", True):
            raise HTTPException(status_code=409, detail="Email already registered")
        # Unverified user re-signing up: update password and resend OTP
        await users_collection.update_one(
            {"email": body.email},
            {"$set": {
                "password": hashed.decode("utf-8"),
                "verification_code": code,
                "verification_code_expiry": expiry,
            }},
        )
    else:
        new_user = {
            "email": body.email,
            "password": hashed.decode("utf-8"),
            "instructions": "",
            "is_verified": False,
            "auth_provider": "email",
            "verification_code": code,
            "verification_code_expiry": expiry,
        }
        await users_collection.insert_one(new_user)

    _send_otp_email(body.email, code)
    return {"message": "Verification code sent to your email", "email": body.email}


@router.post("/signin")
async def signin(body: SignInRequest):
    user = await users_collection.find_one({"email": body.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.get("auth_provider") == "google" and not user.get("password"):
        raise HTTPException(
            status_code=400,
            detail="This account uses Google sign-in. Please use the Google button.",
        )

    stored_password = user.get("password", "")
    if not stored_password or not bcrypt.checkpw(
        body.password.encode("utf-8"), stored_password.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.get("is_verified", False):
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Please check your email for the verification code.",
        )

    token = _create_token(body.email)
    return {
        "token": token,
        "user": {
            "email": user["email"],
            "instructions": user.get("instructions", ""),
        },
    }


@router.post("/verify")
async def verify_otp(body: VerifyOTPRequest):
    user = await users_collection.find_one({"email": body.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("is_verified"):
        raise HTTPException(status_code=400, detail="Account already verified")

    if user.get("verification_code") != body.verification_code:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    expiry = user.get("verification_code_expiry")
    if expiry and datetime.datetime.utcnow() > expiry:
        raise HTTPException(
            status_code=400,
            detail="Verification code has expired. Please request a new one.",
        )

    await users_collection.update_one(
        {"email": body.email},
        {"$set": {
            "is_verified": True,
            "verification_code": "",
            "verification_code_expiry": None,
        }},
    )
    token = _create_token(body.email)
    return {
        "message": "Account verified successfully",
        "token": token,
        "user": {
            "email": user["email"],
            "instructions": user.get("instructions", ""),
        },
    }


@router.post("/resend-otp")
async def resend_otp(body: ResendOTPRequest):
    user = await users_collection.find_one({"email": body.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("is_verified"):
        raise HTTPException(status_code=400, detail="Account already verified")

    # Rate-limit: reject if current code hasn't expired yet
    expiry = user.get("verification_code_expiry")
    if expiry and datetime.datetime.utcnow() < expiry:
        remaining = int((expiry - datetime.datetime.utcnow()).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {remaining} seconds before requesting a new code",
        )

    code = _generate_verification_code()
    await users_collection.update_one(
        {"email": body.email},
        {"$set": {
            "verification_code": code,
            "verification_code_expiry": datetime.datetime.utcnow() + datetime.timedelta(minutes=1),
        }},
    )
    _send_otp_email(body.email, code)
    return {"message": "Verification code sent successfully"}


@router.post("/google")
async def google_auth(body: GoogleAuthRequest):
    # Verify the access token by calling Google's userinfo endpoint
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {body.access_token}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid Google token")

    userinfo = resp.json()
    email = userinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not found in Google account")

    user = await users_collection.find_one({"email": email})

    if not user:
        new_user = {
            "email": email,
            "password": "",
            "instructions": "",
            "is_verified": True,
            "auth_provider": "google",
            "verification_code": "",
            "verification_code_expiry": None,
        }
        await users_collection.insert_one(new_user)
        user = new_user

    token = _create_token(email)
    return {
        "token": token,
        "user": {
            "email": email,
            "instructions": user.get("instructions", ""),
        },
    }


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest):
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user = await users_collection.find_one({"email": body.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("auth_provider") == "google" and not user.get("password"):
        raise HTTPException(
            status_code=400,
            detail="This account uses Google sign-in. Use Google account settings to change your password.",
        )

    stored_password = user.get("password", "")
    if not stored_password or not bcrypt.checkpw(
        body.current_password.encode("utf-8"), stored_password.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    hashed = bcrypt.hashpw(body.new_password.encode("utf-8"), bcrypt.gensalt())
    await users_collection.update_one(
        {"email": body.email},
        {"$set": {"password": hashed.decode("utf-8")}},
    )
    return {"message": "Password changed successfully"}
