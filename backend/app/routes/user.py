from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import users_collection

router = APIRouter()


class UserUpdateRequest(BaseModel):
    email: str
    instructions: str


@router.get("/user")
async def get_user(email: str):
    """Get user by email, create if doesn't exist."""
    try:
        user = await users_collection.find_one({"email": email})
        if user:
            return {
                "user": {
                    "email": user["email"],
                    "instructions": user.get("instructions", ""),
                }
            }
        else:
            new_user = {"email": email, "instructions": ""}
            await users_collection.insert_one(new_user)
            return {
                "user": {
                    "email": email,
                    "instructions": "",
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/update")
async def update_user(body: UserUpdateRequest):
    """Update user instructions."""
    try:
        result = await users_collection.find_one_and_update(
            {"email": body.email},
            {"$set": {"instructions": body.instructions}},
            return_document=True,
        )
        if result:
            return {
                "user": {
                    "email": result["email"],
                    "instructions": result.get("instructions", ""),
                }
            }
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
