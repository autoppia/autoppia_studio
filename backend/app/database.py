import os
import logging

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

MONGO_CONNECTION_URI = os.getenv("MONGO_CONNECTION_URI", "mongodb://localhost:27017/automata")

client = AsyncIOMotorClient(MONGO_CONNECTION_URI)
db = client.get_default_database(default="automata")

users_collection = db["users"]
sessions_collection = db["sessions"]
profiles_collection = db["profiles"]
api_keys_collection = db["api_keys"]
skills_collection = db["skills"]
evals_collection = db["evals"]
eval_runs_collection = db["eval_runs"]


async def ensure_indexes():
    """Create indexes on startup."""
    await users_collection.create_index("email", unique=True)
    await sessions_collection.create_index("email")
    await sessions_collection.create_index("createdAt")
    await profiles_collection.create_index("email")
    await api_keys_collection.create_index("email")
    await api_keys_collection.create_index("keyHash", unique=True)
    await skills_collection.create_index("email")
    await skills_collection.create_index("skillId", unique=True)
    await evals_collection.create_index("email")
    await evals_collection.create_index("evalId", unique=True)
    await eval_runs_collection.create_index("evalId")
    await eval_runs_collection.create_index("runId", unique=True)
    logger.info("MongoDB indexes ensured")
