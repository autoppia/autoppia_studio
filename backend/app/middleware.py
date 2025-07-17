from fastapi import Request
from fastapi.responses import JSONResponse
import httpx

async def verify_api_key(request: Request, call_next):
    try:
        api_key = request.headers.get("x-api-key")
        if not api_key:
            return JSONResponse(status_code=401, content={"error": "Unauthorized: Missing API key"})

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.autoppia.com/api-keys/verify",
                json={"credential": api_key},
            )
            response_data = response.json()

        if not response_data.get("is_valid", False):
            return JSONResponse(status_code=401, content={"error": "Unauthorized: Invalid API key"})

        return await call_next(request)

    except Exception as e:
        print(f"Error during API key verification: {e}")
        return JSONResponse(status_code=401, content={"error": "Unauthorized: Invalid API key"})
