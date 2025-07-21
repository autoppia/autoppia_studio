import httpx
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="x-api-key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.autoppia.com/api-keys/verify",
                json={"credential": api_key},
            )
            response_data = response.json()

        if not response_data.get("is_valid", False):
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid API key")

    except Exception as e:
        print(f"Error during API key verification: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API key")
