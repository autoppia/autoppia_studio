import os
import logging

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

MONGO_CONNECTION_URI = os.getenv("MONGO_CONNECTION_URI", "mongodb://localhost:27017/automata")

client = AsyncIOMotorClient(MONGO_CONNECTION_URI)
db = client.get_default_database(default="automata")

users_collection = db["users"]
sessions_collection = db["sessions"]


async def ensure_indexes():
    """Create indexes on startup."""
    await users_collection.create_index("email", unique=True)
    await sessions_collection.create_index("email")
    await sessions_collection.create_index("createdAt")
    logger.info("MongoDB indexes ensured")
