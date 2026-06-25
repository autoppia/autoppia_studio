export interface SessionItem {
    sessionId: string;
    email: string;
    companyId?: string;
    socketioPath?: string;
    prompt: string;
    initialUrl: string;
    sessionPath?: string;
    lastUrl?: string;
    provider?: string;
    agentId?: string;
    agentName?: string;
    runtimeState?: Record<string, any>;
    actionCount?: number;
    chatCount?: number;
    runtimeKind?: "browser" | "api" | "hybrid";
    browserActionCount?: number;
    connectorActionCount?: number;
    hasBrowserActivity?: boolean;
    hasConnectorActivity?: boolean;
    matchedSkillId?: string;
    matchedSkillName?: string;
    approvedConnectorToolCalls?: string[];
    approvedConnectorToolCallCount?: number;
    pendingConnectorApproval?: string;
    pendingApprovalCount?: number;
    artifactCount?: number;
    sourceKind?: string;
    workItemId?: string;
    runId?: string;
    creditsSpent?: number;
    latestAction?: string;
    latestActivityLabel?: string;
    latestActivityAt?: string;
    createdAt?: string | Date;
}

export type HistoryItem = SessionItem;

export interface ChatItem {
  role: string;
  content?: string;
  actions?: string[];
  actionMetadata?: ({ skill?: Record<string, any>; router?: Record<string, any>; tool?: Record<string, any> } | undefined)[];
  actionResults?: (boolean | undefined)[];
  actionTimings?: ({ elapsedSeconds?: number; emittedAt?: string } | undefined)[];
  screenshots?: string[];
  artifacts?: SessionArtifact[];
  thinking?: string;
  state?: string;
  reasoning?: string;
}

export interface SessionArtifact {
  artifactId: string;
  name: string;
  url?: string;
  title?: string;
  artifactType?: string;
  content?: string;
  fileName?: string;
  kind?: string;
  contentType?: string;
  size?: number | string;
  sourceTool?: string;
  metadata?: Record<string, any>;
}

export interface SessionDocument {
  documentId: string;
  sessionId: string;
  email: string;
  companyId?: string;
  filename: string;
  contentType: string;
  size: number;
  status: string;
  source: string;
  knowledgeDocumentId?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface SkillParameter {
  name: string;
  description: string;
  defaultValue: string;
}

export interface Skill {
  skillId: string;
  name: string;
  goal: string;
  instructions: string;
  parameters: SkillParameter[];
  actions: any[];
  createdAt?: string;
}

export interface EvalItem {
  evalId: string;
  taskId?: string;
  email?: string;
  companyId?: string;
  prompt: string;
  initialUrl: string;
  benchmarkId?: string;
  benchmarkName?: string;
  agentId?: string;
  agentName?: string;
  agentTaskName?: string;
  successCriteria?: string;
  judgeType?: "manual" | "llm" | string;
  status?: string;
  source?: string;
  createdAt?: string;
}

export interface EvalRun {
  runId: string;
  benchmarkRunId?: string;
  evalId: string;
  sessionId: string;
  prompt?: string;
  initialUrl?: string;
  benchmarkId?: string;
  benchmarkName?: string;
  agentId?: string;
  agentName?: string;
  agentTaskName?: string;
  actions: any[];
  label: "pass" | "fail" | "pending";
  judgeType?: "manual" | "llm" | string;
  labelSource?: string;
  manualOverride?: boolean;
  judge?: Record<string, any>;
  screenshots?: string[];
  createdAt?: string;
}

export interface AgentTask {
  name: string;
  prompt: string;
  successCriteria?: string;
  status?: string;
  trajectoryId?: string;
}

export interface AgentTrajectory {
  trajectoryId?: string;
  agentId?: string;
  webId?: string;
  name?: string;
  taskName?: string;
  prompt?: string;
  successCriteria?: string;
  status?: string;
  source?: string;
  actions?: any[];
  screenshots?: string[];
  createdAt?: string;
  updatedAt?: string;
}

export interface AgentWeb {
  webId: string;
  agentId: string;
  name: string;
  baseUrl: string;
  authRequired: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface AgentCapability {
  capabilityId: string;
  agentId: string;
  webId?: string;
  name: string;
  description: string;
  type?: "web" | "api" | "hybrid" | string;
  parameters: any[];
  trajectoryIds: string[];
  runtime: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface RuntimeCapabilities {
  browser?: boolean;
  apiCalls?: boolean;
  knowledge?: boolean;
  python?: boolean;
  humanApprovalForWrites?: boolean;
}

export interface RuntimeSpec {
  browserEnabled?: boolean;
  browserMode?: "visible" | "headless";
  maxCreditsPerRun?: number;
  tools?: {
    browser?: boolean;
    connectors?: boolean;
    skills?: boolean;
    knowledge?: boolean;
  };
}

export interface AgentConfig {
  agentConfigId?: string;
  agentId: string;
  email: string;
  companyId?: string;
  name: string;
  websiteUrl: string;
  runtimeEndpoint: string;
  runtimeType: string;
  status: string;
  trainingStatus: string;
  harvester?: string;
  runtimeCapabilities?: RuntimeCapabilities;
  runtimeSpec?: RuntimeSpec;
  apiSpecUrl?: string;
  apiAuthConfigured?: boolean;
  tasks: AgentTask[];
  trajectories: AgentTrajectory[];
  successCriteria: string;
  createdAt?: string;
  updatedAt?: string;
}


export interface AgentCreationStep {
  key: string;
  label: string;
  status: string;
  message?: string;
  updatedAt?: string;
}

export interface AgentCreationJob {
  jobId: string;
  agentId: string;
  companyId?: string;
  email?: string;
  status: string;
  currentStep: string;
  steps: AgentCreationStep[];
  events: Array<{ type: string; message: string; createdAt?: string }>;
  createdAt?: string;
  updatedAt?: string;
}

export interface EmbedSettings {
  enabled?: boolean;
  publicToken?: string;
  allowedOrigins?: string[];
  hostJwtConfigured?: boolean;
  updatedAt?: string;
}

export interface Company {
  companyId: string;
  email: string;
  name: string;
  description?: string;
  industry?: string;
  status?: string;
  embedSettings?: EmbedSettings;
  createdAt?: string;
  updatedAt?: string;
}

export interface CompanySetupConnector {
  connectorId: string;
  name: string;
  type: string;
  category: string;
  status: string;
  provider: string;
  surface: string;
  authRequired?: boolean;
  runtimeRequirements?: string[];
  domains?: string[];
}

export interface CompanySetupCount {
  name: string;
  count: number;
}

export interface CompanySetupContract {
  integrationContractVersion: string;
  profile: {
    companyId: string;
    name: string;
    industry?: string;
    description?: string;
    status?: string;
  };
  systems: {
    summary: {
      totalConnectors: number;
      connectedConnectors: number;
      connectorsNeedingAuth: number;
      customConnectors: number;
    };
    categoryCoverage: CompanySetupCount[];
    surfaceCoverage: CompanySetupCount[];
    connectors: CompanySetupConnector[];
  };
  context: {
    resources: number;
    vectorStores: number;
    entities: number;
    typedTools: number;
  };
  factory: {
    agents: number;
    tools: number;
    benchmarks: number;
    benchmarkTasks: number;
    evals: number;
    evalRuns: number;
    trajectories: number;
    approvedTrajectories: number;
    skills: number;
    readySkills: number;
  };
  runtime: {
    sessions: number;
    runtimeKinds: CompanySetupCount[];
    artifacts: number;
    pendingApprovals: number;
    approvedApprovals: number;
    workItems: number;
    runningWorkItems: number;
    reviewWorkItems: number;
  };
  governance: {
    credentials: number;
    allowedOrigins: string[];
    allowedOriginHosts: string[];
    hostJwtConfigured: boolean;
    discoveredDomains: string[];
    skillPolicies: CompanySetupCount[];
  };
}

export interface AgentToolkit {
  toolkitId: string;
  name: string;
  connectorName?: string;
  connectorId?: string;
  category: string;
  status?: string;
  runtimeRequirements: string[];
  authFields?: string[];
  configFields?: string[];
  permissions?: Record<string, any>;
  tools: Array<{
    name: string;
    description: string;
    sideEffects: string;
    inputSchema?: any;
  }>;
}

export interface RuntimeEvent {
  runId: string;
  agentId: string;
  companyId?: string;
  eventType: string;
  stepIndex?: number | null;
  toolName?: string;
  status?: string;
  payload?: Record<string, any>;
  result?: Record<string, any>;
  error?: string;
  createdAt?: string;
}

export type WorkStatus = "TODO" | "RUNNING" | "REVIEW" | "DONE" | "FAILED";
export type WorkRunTarget = "selected" | "all";

export interface WorkBoard {
  boardId: string;
  email: string;
  companyId?: string;
  name: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface WorkItem {
  workItemId: string;
  email: string;
  companyId?: string;
  boardId?: string;
  title: string;
  prompt: string;
  successCriteria?: string;
  agentId?: string;
  agentName?: string;
  runTarget: WorkRunTarget;
  browserEnabled: boolean;
  browserMode: "visible" | "headless";
  maxCreditsPerRun: number;
  maxBudgetCredits?: number;
  maxSteps?: number;
  triggerType?: "manual" | "scheduled";
  scheduleFrequency?: "none" | "daily" | "weekly";
  scheduleTime?: string;
  scheduleDayOfWeek?: number;
  nextRunAt?: string;
  triggerConfig?: Record<string, any>;
  sourceTaskId?: string;
  sourceBenchmarkId?: string;
  judgeImplementation?: string;
  status: WorkStatus;
  report?: {
    runId?: string;
    target?: WorkRunTarget;
    resultCount?: number;
    results?: Array<{
      agentId: string;
      agentName?: string;
      status: "ok" | "failed";
      result?: Record<string, any>;
      error?: string;
      steps?: any[];
      stepCount?: number;
      finalUrl?: string;
    }>;
    summary?: string;
  };
  judge?: {
    label?: "success" | "needs_review" | "failed" | string;
    reason?: string;
    judgeType?: string;
  };
  runHistory?: any[];
  operational?: {
    approvalCount?: number;
    pendingApprovalCount?: number;
    latestArtifactCount?: number;
    persistedArtifactCount?: number;
    latestToolCallCount?: number;
    latestMatchedSkillIds?: string[];
    latestMatchedSkillNames?: string[];
    latestMatchedTrajectoryIds?: string[];
    latestToolNames?: string[];
    latestToolIds?: string[];
    latestSessionIds?: string[];
    latestCreditsSpent?: number;
    reviewBlocked?: boolean;
  };
  lastRunId?: string;
  createdAt?: string;
  updatedAt?: string;
  startedAt?: string;
  completedAt?: string;
}

export type NotificationLevel = "info" | "success" | "warning" | "error";

export interface AppNotification {
  notificationId: string;
  title: string;
  message?: string;
  level: NotificationLevel;
  source?: string;
  entityType?: string;
  entityId?: string;
  actionUrl?: string;
  metadata?: Record<string, any>;
  read: boolean;
  createdAt?: string;
  readAt?: string;
}

export interface RunningWorkItem {
  workItemId: string;
  title: string;
  agentName?: string;
  runTarget?: WorkRunTarget;
  startedAt?: string;
  lastRunId?: string;
  sessionId?: string;
}

export interface ActivityStatusCounts {
  runningTasks: number;
  queuedTasks: number;
  reviewTasks: number;
  doneTasks: number;
  failedTasks: number;
  scheduledDue: number;
  scheduledUpcoming: number;
  activeSessions: number;
  evalRunsPending: number;
  evalRunsPassed: number;
  evalRunsFailed: number;
  harvestersRunning: number;
  harvestersCompleted: number;
  harvestersFailed: number;
}

export interface ActivitySummary {
  status: ActivityStatusCounts;
  running: RunningWorkItem[];
  notifications: {
    unreadCount: number;
    recent: AppNotification[];
  };
}

export interface Connector {
  connectorId: string;
  companyId: string;
  email: string;
  name: string;
  type: string;
  category: string;
  description: string;
  status: string;
  provider?: string;
  generationStatus?: string;
  surface?: string;
  authRequired?: boolean;
  discoveryStatus?: string;
  discoveryMode?: string;
  runtimeRequirements?: string[];
  config?: Record<string, any>;
  vectorIndex?: VectorIndex;
  credentialFields?: Record<string, { configured: boolean }>;
  lastTestAt?: string;
  lastTestStatus?: string;
  lastTestMessage?: string;
  toolkit: AgentToolkit;
  createdAt?: string;
  updatedAt?: string;
}

export interface Credential {
  credentialId: string;
  secretRef: string;
  email: string;
  companyId?: string;
  name: string;
  type: string;
  createdFor: string;
  metadata?: Record<string, any>;
  configured: boolean;
  maskedValue: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface VectorIndex {
  vectorDatabaseId?: string;
  name?: string;
  provider: string;
  collectionName: string;
  embeddingProvider?: string;
  embeddingModel?: string;
  indexedDocuments?: number;
  documentCount?: number;
  totalSize?: number;
  connectorId?: string;
  status?: string;
}

export interface VectorDatabase extends VectorIndex {
  vectorDatabaseId: string;
  email: string;
  companyId: string;
  name: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface KnowledgeDocument {
  documentId: string;
  email: string;
  companyId: string;
  filename: string;
  contentType: string;
  size: number;
  status: string;
  source: string;
  connectorId?: string;
  vectorDatabaseId?: string;
  vectorDatabaseName?: string;
  vectorCollectionName?: string;
  createdAt?: string;
  updatedAt?: string;
}

export type EntityFieldRole =
  | "identifier"
  | "display"
  | "reference"
  | "status"
  | "date"
  | "amount"
  | "metadata"
  | string;

export type EntityRelationshipKind =
  | "belongsTo"
  | "hasOne"
  | "hasMany"
  | "manyToMany"
  | "references"
  | string;

export type EntitySource = "manual" | "openapi" | "llm_mapper" | "imported" | string;

export interface EntityField {
  name: string;
  type?: string;
  description?: string;
  role?: EntityFieldRole;
  required?: boolean;
  ref?: string;
  target?: string;
  sourcePath?: string;
  examples?: any[];
}

export interface EntityRelationship {
  name: string;
  kind?: EntityRelationshipKind;
  target: string;
  via?: string;
  description?: string;
}

export interface EntityModel {
  entityId: string;
  companyId: string;
  email: string;
  name: string;
  description?: string;
  fields: EntityField[];
  relationships: EntityRelationship[];
  sourceConnectorId?: string;
  source?: EntitySource;
  metadata?: Record<string, any>;
  createdAt?: string;
  updatedAt?: string;
}

export interface EntityGraphNode {
  id: string;
  entityId: string;
  name: string;
  description?: string;
  fieldCount: number;
  sourceConnectorId?: string;
  source?: EntitySource;
}

export interface EntityGraphEdge {
  from: string;
  to: string;
  name?: string;
  kind?: EntityRelationshipKind;
  via?: string;
  description?: string;
}

export interface EntityGraph {
  nodes: EntityGraphNode[];
  edges: EntityGraphEdge[];
  entities: EntityModel[];
}

export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired" | string;

export interface ApprovalRequest {
  approvalId: string;
  companyId: string;
  email: string;
  agentId?: string;
  runId?: string;
  workItemId?: string;
  sessionId?: string;
  sourceKind?: string;
  approvalKey: string;
  toolName?: string;
  title: string;
  message?: string;
  proposedAction: {
    name?: string;
    arguments?: Record<string, any>;
    [key: string]: any;
  };
  entityRef?: Record<string, any>;
  status: ApprovalStatus;
  decidedBy?: string;
  decisionReason?: string;
  createdAt?: string;
  updatedAt?: string;
  expiresAt?: string;
  decidedAt?: string;
  metadata?: Record<string, any>;
  auditTrail?: Array<{
    event?: string;
    at?: string;
    by?: string;
    reason?: string;
  }>;
}

export interface CompanyTool {
  capabilityId: string;
  capabilityKind: "tool";
  toolId: string;
  companyId: string;
  connectorId: string;
  connectorName: string;
  name: string;
  displayName: string;
  description: string;
  inputSchema?: any;
  outputSchema?: any;
  inputEntities?: string[];
  outputEntity?: string;
  outputCard?: Record<string, any>;
  executionType: string;
  surface: string;
  runtimeRequirements?: string[];
  sideEffects: string;
  permissions?: Record<string, any>;
  riskLevel: string;
  status: string;
  source: string;
  discovererName?: string;
  discovererVersion?: string;
  discoveryScope?: string;
  discoveryRelevance?: Record<string, any>;
  discoveryEvidence?: any[];
  lastTestAt?: string;
  lastTestStatus?: string;
  lastTestResult?: any;
  createdAt?: string;
  updatedAt?: string;
}

export interface CompanyTrajectory {
  capabilityId: string;
  capabilityKind: "trajectory";
  trajectoryId: string;
  companyId: string;
  agentId?: string;
  taskId?: string;
  connectorIds: string[];
  toolIds: string[];
  runtimeRequirements?: string[];
  name: string;
  intent: string;
  description: string;
  successCriteria?: string;
  benchmarkId?: string;
  evalId?: string;
  finalUrl?: string;
  judge?: Record<string, any>;
  review?: Record<string, any>;
  harvester?: Record<string, any>;
  trajectory?: any[];
  steps: any[];
  validations: any[];
  recoverySteps: any[];
  status: string;
  source: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface CompanySkill {
  capabilityId: string;
  capabilityKind: "skill";
  skillId: string;
  companyId: string;
  agentId?: string;
  connectorIds: string[];
  toolIds?: string[];
  trajectoryIds: string[];
  runtimeRequirements?: string[];
  name: string;
  description: string;
  whenToUse: string;
  instructions?: string;
  preconditions?: string[];
  expectedArtifacts?: string[];
  benchmarkId?: string;
  evalId?: string;
  inputEntities?: string[];
  outputEntity?: string;
  outputCard?: Record<string, any>;
  permissions?: Record<string, any>;
  riskPolicy: string;
  runtime: string;
  status: string;
  promotionStatus?: string;
  version?: number;
  versionLabel?: string;
  publishedAt?: string;
  readyAt?: string;
  archivedAt?: string;
  source?: string;
  harvesterType?: string;
  harvesterRunId?: string;
  judge?: Record<string, any>;
  lineage?: {
    trajectoryIds?: string[];
    benchmarkIds?: string[];
    evalIds?: string[];
    connectorIds?: string[];
    toolIds?: string[];
    sources?: string[];
  };
  latestRegression?: {
    evalId?: string;
    runId?: string;
    label?: "pass" | "fail" | "pending" | "";
    createdAt?: string;
  } | null;
  hardeningStatus?: {
    checks?: Record<string, boolean>;
    passedChecks?: number;
    totalChecks?: number;
    score?: number;
    state?: string;
  };
  createdAt?: string;
  updatedAt?: string;
}

export interface HarvesterRun {
  harvesterRunId: string;
  runKind?: "tool_publication" | "harvester" | string;
  email?: string;
  companyId: string;
  connectorId: string;
  connectorName: string;
  benchmarkId?: string;
  evalId?: string;
  harvesterType?: string;
  surface?: string;
  status: string;
  discoveredTools: number;
  generatedTrajectories: number;
  generatedSkills: number;
  logs: string[];
  errors: string[];
  startedAt?: string;
  completedAt?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface CompanyCapabilities {
  tools: CompanyTool[];
  trajectories: CompanyTrajectory[];
  skills: CompanySkill[];
}

export interface ParameterizeResult {
  name: string;
  goal: string;
  instructions: string;
  parameters: SkillParameter[];
  actions: any[];
}

export interface Artifact {
  artifactId: string;
  companyId: string;
  email: string;
  sessionId?: string;
  title: string;
  artifactType: string;
  description: string;
  content: string;
  fileName: string;
  sourceTool?: string;
  metadata?: Record<string, any>;
  createdAt?: string;
  updatedAt?: string;
}
