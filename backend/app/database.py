import os
import logging

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

MONGO_CONNECTION_URI = os.getenv("MONGO_CONNECTION_URI", "mongodb://localhost:27017/automata")

client = AsyncIOMotorClient(MONGO_CONNECTION_URI)
db = client.get_default_database(default="automata")

users_collection = db["users"]
sessions_collection = db["sessions"]
session_documents_collection = db["session_documents"]
profiles_collection = db["profiles"]
api_keys_collection = db["api_keys"]
skills_collection = db["skills"]
agents_collection = db["agents"]
companies_collection = db["companies"]
connectors_collection = db["connectors"]
credentials_collection = db["credentials"]
knowledge_documents_collection = db["knowledge_documents"]
onboarding_sessions_collection = db["onboarding_sessions"]
evals_collection = db["evals"]
eval_runs_collection = db["eval_runs"]
benchmarks_collection = db["benchmarks"]
benchmark_tasks_collection = db["benchmark_tasks"]
agent_creation_jobs_collection = db["agent_creation_jobs"]
agent_webs_collection = db["agent_webs"]
trajectories_collection = db["trajectories"]
capabilities_collection = db["capabilities"]
tools_collection = db["tools"]
harvester_runs_collection = db["harvester_runs"]
work_boards_collection = db["work_boards"]
work_items_collection = db["work_items"]
notifications_collection = db["notifications"]
tool_runs_collection = db["tool_runs"]
trajectory_runs_collection = db["trajectory_runs"]
capability_grants_collection = db["capability_grants"]
validator_rounds_collection = db["validator_rounds"]
validator_round_tasks_collection = db["validator_round_tasks"]
validator_agent_runs_collection = db["validator_agent_runs"]
validator_evaluations_collection = db["validator_evaluations"]
validator_task_logs_collection = db["validator_task_logs"]
worker_locks_collection = db["worker_locks"]


async def ensure_indexes():
    """Create indexes on startup."""
    await users_collection.create_index("email", unique=True)
    await sessions_collection.create_index("email")
    await sessions_collection.create_index("createdAt")
    await session_documents_collection.create_index("sessionId")
    await session_documents_collection.create_index("documentId", unique=True)
    await session_documents_collection.create_index("email")
    await session_documents_collection.create_index("companyId")
    await profiles_collection.create_index("email")
    await api_keys_collection.create_index("email")
    await api_keys_collection.create_index("keyHash", unique=True)
    await skills_collection.create_index("email")
    await skills_collection.create_index("skillId", unique=True)
    await agents_collection.create_index("email")
    await agents_collection.create_index("agentId", unique=True)
    await companies_collection.create_index("email")
    await companies_collection.create_index("companyId", unique=True)
    await connectors_collection.create_index("email")
    await connectors_collection.create_index("companyId")
    await connectors_collection.create_index("connectorId", unique=True)
    await credentials_collection.create_index("email")
    await credentials_collection.create_index("companyId")
    await credentials_collection.create_index("credentialId", unique=True)
    await credentials_collection.create_index("secretRef", unique=True)
    await knowledge_documents_collection.create_index("email")
    await knowledge_documents_collection.create_index("companyId")
    await knowledge_documents_collection.create_index("documentId", unique=True)
    await onboarding_sessions_collection.create_index("email")
    await onboarding_sessions_collection.create_index("sessionId", unique=True)
    await evals_collection.create_index("email")
    await evals_collection.create_index("evalId", unique=True)
    await evals_collection.create_index("agentId")
    await eval_runs_collection.create_index("evalId")
    await eval_runs_collection.create_index("email")
    await eval_runs_collection.create_index("agentId")
    await eval_runs_collection.create_index("runId", unique=True)
    await benchmarks_collection.create_index("email")
    await benchmarks_collection.create_index("companyId")
    await benchmarks_collection.create_index("agentId")
    await benchmarks_collection.create_index("benchmarkId", unique=True)
    await benchmark_tasks_collection.create_index("email")
    await benchmark_tasks_collection.create_index("companyId")
    await benchmark_tasks_collection.create_index("agentId")
    await benchmark_tasks_collection.create_index("benchmarkId")
    await benchmark_tasks_collection.create_index("taskId", unique=True)
    await agent_creation_jobs_collection.create_index("agentId")
    await agent_creation_jobs_collection.create_index("jobId", unique=True)
    await agent_webs_collection.create_index("agentId")
    await agent_webs_collection.create_index("webId", unique=True)
    await trajectories_collection.create_index("agentId")
    await trajectories_collection.create_index("webId")
    await trajectories_collection.create_index("trajectoryId", unique=True)
    await capabilities_collection.create_index("agentId")
    await capabilities_collection.create_index("companyId")
    await capabilities_collection.create_index("webId")
    await capabilities_collection.create_index("capabilityId", unique=True)
    await tools_collection.create_index("email")
    await tools_collection.create_index("companyId")
    await tools_collection.create_index("connectorId")
    await tools_collection.create_index("toolId", unique=True)
    await harvester_runs_collection.create_index("email")
    await harvester_runs_collection.create_index("companyId")
    await harvester_runs_collection.create_index("agentId")
    await harvester_runs_collection.create_index("connectorId")
    await harvester_runs_collection.create_index("harvesterRunId", unique=True)
    await work_boards_collection.create_index("email")
    await work_boards_collection.create_index("companyId")
    await work_boards_collection.create_index("boardId", unique=True)
    await work_items_collection.create_index("email")
    await work_items_collection.create_index("companyId")
    await work_items_collection.create_index("boardId")
    await work_items_collection.create_index("agentId")
    await work_items_collection.create_index("status")
    await work_items_collection.create_index("nextRunAt")
    await work_items_collection.create_index("workItemId", unique=True)
    await notifications_collection.create_index("email")
    await notifications_collection.create_index("companyId")
    await notifications_collection.create_index("notificationId", unique=True)
    await notifications_collection.create_index("read")
    await notifications_collection.create_index("createdAt")
    await tool_runs_collection.create_index("toolId")
    await tool_runs_collection.create_index("agentId")
    await tool_runs_collection.create_index("companyId")
    await tool_runs_collection.create_index("runId", unique=True)
    await trajectory_runs_collection.create_index("trajectoryId")
    await trajectory_runs_collection.create_index("companyId")
    await trajectory_runs_collection.create_index("runId", unique=True)
    await capability_grants_collection.create_index("companyId")
    await capability_grants_collection.create_index("agentId")
    await capability_grants_collection.create_index("capabilityId")
    await validator_rounds_collection.create_index("validator_round_id", unique=True)
    await validator_rounds_collection.create_index("season_number")
    await validator_rounds_collection.create_index("round_number_in_season")
    await validator_round_tasks_collection.create_index("validator_round_id")
    await validator_round_tasks_collection.create_index("task_id")
    await validator_agent_runs_collection.create_index("validator_round_id")
    await validator_agent_runs_collection.create_index("agent_run_id", unique=True)
    await validator_evaluations_collection.create_index("validator_round_id")
    await validator_evaluations_collection.create_index("agent_run_id")
    await validator_evaluations_collection.create_index("evaluation_id")
    await validator_task_logs_collection.create_index("validator_round_id")
    await validator_task_logs_collection.create_index("task_id")
    await worker_locks_collection.create_index("lockId", unique=True)
    await worker_locks_collection.create_index("expiresAt")
    logger.info("MongoDB indexes ensured")
