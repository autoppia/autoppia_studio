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
    runtimeMetrics?: {
        runtimeKind?: "browser" | "api" | "hybrid" | string;
        creditsSpent?: number;
        durationSeconds?: number;
        lastStepSeconds?: number;
        browserActionCount?: number;
        connectorActionCount?: number;
        stepLatencyCount?: number;
        traceIds?: string[];
    };
    runtimePolicyBoundary?: {
        boundaries?: {
            read?: number;
            draft?: number;
            write?: number;
            send?: number;
        };
        approvalRequiredFor?: string[];
        pendingApprovalCount?: number;
        approvedApprovalCount?: number;
        artifactCount?: number;
        hasHumanBoundary?: boolean;
    };
    runtimeTimeline?: {
        index?: number;
        action?: string;
        label: string;
        activity: "browser" | "skill" | "tool" | "done" | string;
        status: "ok" | "failed" | "pending" | string;
        emittedAt?: string;
        elapsedSeconds?: number;
        traceId?: string;
        toolCallId?: string;
        approvalKey?: string;
        artifactId?: string;
        skillId?: string;
    }[];
    runtimeEvidence?: {
        summary?: {
            runtimeKind?: string;
            toolCalls?: number;
            browserSteps?: number;
            artifacts?: number;
            pendingApprovals?: number;
            creditsSpent?: number;
            durationSeconds?: number;
        };
        trace?: {
            traceIds?: string[];
            traceCount?: number;
            timelineSteps?: number;
            failedSteps?: number;
            pendingSteps?: number;
            lastTraceId?: string;
            replayReady?: boolean;
        };
        capabilityRefs?: {
            skillId?: string;
            skillName?: string;
            workItemId?: string;
            runId?: string;
            linked?: boolean;
        };
        approvalBoundary?: {
            approvalRequiredFor?: string[];
            hasHumanBoundary?: boolean;
            pendingConnectorApproval?: string;
        };
        outputs?: {
            artifactCount?: number;
            hasBusinessOutput?: boolean;
        };
    };
    runtimeLab?: {
        controlPlane?: {
            sessionId?: string;
            runtimeKind?: string;
            sourceKind?: string;
            agentId?: string;
            agentName?: string;
            workItemId?: string;
            runId?: string;
        };
        timeline?: {
            steps?: number;
            browserSteps?: number;
            toolSteps?: number;
            skillSteps?: number;
            failedSteps?: number;
            pendingSteps?: number;
            lastAction?: string;
            lastActivityAt?: string;
            traceIds?: string[];
            replayReady?: boolean;
        };
        toolCalls?: {
            total?: number;
            approved?: number;
            pendingApproval?: string;
            sample?: Array<{
                index?: number;
                action?: string;
                label?: string;
                status?: string;
                traceId?: string;
                elapsedSeconds?: number;
            }>;
        };
        skillMatch?: {
            matched?: boolean;
            skillId?: string;
            skillName?: string;
        };
        approvals?: {
            pending?: number;
            approvedConnectorCalls?: number;
            requiredFor?: string[];
            hasHumanBoundary?: boolean;
        };
        outputs?: {
            artifacts?: number;
            hasBusinessOutput?: boolean;
            creditsSpent?: number;
            durationSeconds?: number;
            lastStepSeconds?: number;
        };
    };
    runtimeAuditTrail?: {
        sessionId?: string;
        uniform?: boolean;
        eventCount?: number;
        events?: Array<{
            event?: string;
            actor?: string;
            boundary?: string;
            action?: string;
            status?: string;
            at?: string;
            traceId?: string;
            description?: string;
            skillId?: string;
        }>;
        boundaries?: {
            read?: number;
            draft?: number;
            write?: number;
            send?: number;
        };
        approvalRequiredFor?: string[];
        hasHumanBoundary?: boolean;
        artifactCount?: number;
        pendingApprovalCount?: number;
    };
    sessionContract?: {
        contractVersion?: string;
        sessionId?: string;
        agentRuntime?: {
            runtimeKind?: "browser" | "api" | "hybrid" | string;
            sourceKind?: string;
            agentId?: string;
            agentName?: string;
            workItemId?: string;
            runId?: string;
        };
        selectedSkill?: {
            matched?: boolean;
            skillId?: string;
            skillName?: string;
        };
        approvalState?: {
            pending?: number;
            approvedConnectorCalls?: number;
            requiredFor?: string[];
            hasHumanBoundary?: boolean;
        };
        artifactState?: {
            count?: number;
            hasBusinessOutput?: boolean;
        };
        costState?: {
            creditsSpent?: number;
            durationSeconds?: number;
            lastStepSeconds?: number;
        };
        traceState?: {
            traceIds?: string[];
            traceCount?: number;
            timelineSteps?: number;
            replayReady?: boolean;
        };
    };
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
    traceIds?: string[];
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

export interface ArtifactApprovalRelation {
  linked?: boolean;
  approvalId?: string;
  approvalKey?: string;
  state?: string;
  boundary?: string;
  requiresReview?: boolean;
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
  approvalRelation?: ArtifactApprovalRelation;
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
  taskContract?: {
    businessIntent?: string;
    initialState?: Record<string, any>;
    initialUrl?: string;
    allowedSystems?: string[];
    expectedArtifacts?: string[];
    successCriteria?: string;
    riskClass?: string;
    completeness?: {
      checks?: Record<string, boolean>;
      passedChecks?: number;
      totalChecks?: number;
      score?: number;
      state?: string;
    };
  };
  judgeType?: "manual" | "llm" | string;
  evaluationHarness?: {
    strategy?: string;
    preferredOrder?: string[];
    deterministicFirst?: boolean;
    statefulReplay?: boolean;
    llmAsComplement?: boolean;
    humanOverride?: boolean;
    layers?: Array<{
      key?: string;
      label?: string;
      enabled?: boolean;
      role?: string;
      summary?: string;
    }>;
  };
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
  allowedDomains?: string[];
  browserAllowedDomains?: string[];
  browserRestrictedByDomain?: boolean;
  browserDefaultUse?: string;
  approvalRequiredFor?: string[];
  runtimeClasses?: string[];
  maxSteps?: number;
  maxCreditsPerRun?: number;
  tools?: {
    browser?: boolean;
    connectors?: boolean;
    skills?: boolean;
    knowledge?: boolean;
  };
}

export interface EnterpriseRuntimePolicy {
  runtimeClass: "api" | "browser" | "hybrid" | string;
  runtimeType: string;
  runtimeTypes: string[];
  browser: {
    enabled?: boolean;
    mode?: string;
    allowedDomains?: string[];
    restrictedByDomain?: boolean;
    defaultUse?: string;
    riskLevel?: string;
    notes?: string;
    requiresSandbox?: boolean;
    leastPrivilege?: boolean;
  };
  api: {
    enabled?: boolean;
    connectorToolsEnabled?: boolean;
    toolCount?: number;
  };
  approvals: {
    humanApprovalForWrites?: boolean;
    requiredFor?: string[];
    requiredBoundaries?: string[];
    requiredTools?: string[];
  };
  budgets: {
    maxCreditsPerRun?: number;
    maxSteps?: number;
  };
  policyBoundaries: string[];
  resources: {
    total?: number;
    indexed?: number;
    citable?: number;
  };
}

export interface AgentRuntimeContract {
  runtimeCapabilities?: RuntimeCapabilities;
  runtimeSpec?: RuntimeSpec;
  browserPolicy?: EnterpriseRuntimePolicy["browser"];
  enterpriseRuntime?: EnterpriseRuntimePolicy;
  entities?: Record<string, any>;
  resources?: Record<string, any>[];
  resourceGrounding?: {
    total?: number;
    indexed?: number;
    citable?: number;
    readTools?: string[];
  };
  toolGovernance?: {
    total?: number;
    governed?: number;
    approvalRequiredTools?: string[];
    riskCounts?: Record<string, number>;
    policyBoundaries?: string[];
  };
  tools?: AgentCallable[];
  skills?: AgentCallable[];
  skillPackages?: {
    total?: number;
    manifestReady?: number;
    publishable?: number;
    withIoContract?: number;
    withRegressionSuite?: number;
    blocked?: number;
    packages?: Array<{
      skillId?: string;
      name?: string;
      version?: number | string;
      manifestReady?: boolean;
      publishable?: boolean;
      checks?: Record<string, boolean>;
      blockers?: string[];
      progressiveDisclosure?: Record<string, any>;
    }>;
  };
  toolCalls?: string[];
  unavailableToolCalls?: Array<{
    name?: string;
    runtimeAvailability?: {
      required?: string[];
      available?: boolean;
      unavailable?: string[];
    };
  }>;
}

export interface ToolApprovalPolicy {
  required?: boolean;
  mode?: "always" | "auto" | "never" | string;
  reasons?: string[];
  boundary?: string;
  humanReview?: boolean;
  [key: string]: any;
}

export interface ToolContract {
  contractVersion?: string;
  toolId?: string;
  name?: string;
  connectorId?: string;
  connectorName?: string;
  action?: string;
  atomic?: boolean;
  sideEffects?: string;
  policyBoundary?: string;
  riskLevel?: string;
  scopes?: string[];
  approvalPolicy?: ToolApprovalPolicy;
  schemas?: {
    input?: any;
    output?: any;
  };
  entities?: {
    input?: string[];
    output?: string;
  };
  runtime?: {
    executionType?: string;
    surface?: string;
    requirements?: string[];
  };
  [key: string]: any;
}

export interface AgentCallable {
  id?: string;
  name: string;
  description?: string;
  inputSchema?: any;
  outputSchema?: any;
  riskLevel?: string;
  sideEffects?: string;
  policyBoundary?: string;
  approvalPolicy?: ToolApprovalPolicy;
  scopes?: string[];
  toolContract?: ToolContract;
  [key: string]: any;
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
  tools?: AgentCallable[];
  skills?: AgentCallable[];
  entities?: Record<string, any>;
  resources?: any[];
  knowledge?: any[];
  memory?: Record<string, any>;
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
  systemFactory?: {
    connectorMap: {
      total: number;
      entityMapped: number;
      entitySourceReady: number;
      entityPending: number;
      typedToolReady: number;
      toolSynthesisPending: number;
      candidateTasksReady: number;
      ingestionReady: number;
      ingestionBlocked: number;
      readyStages: number;
      totalStages: number;
      sample: Array<{
        connectorId: string;
        name: string;
        entityMapping: string;
        businessObjects: string[];
        readyForToolBinding: boolean;
        typedToolCount: number;
        governedToolCount: number;
        candidateTasksRecommended: boolean;
        ingestionState: string;
        readyStages: number;
        totalStages: number;
      }>;
      gaps: Array<{ key: string; label: string; target: string }>;
    };
  };
  resourceMap?: {
    documents: {
      total: number;
      indexed: number;
      withResourceContract: number;
      withVectorStore: number;
      acl?: {
        withAcl: number;
        companyVisible: number;
        restricted: number;
        visibility: CompanySetupCount[];
        roles: string[];
        users: string[];
      };
      status: CompanySetupCount[];
      readTools: string[];
      sample: Array<{
        documentId: string;
        resourceId: string;
        name: string;
        resourceKind: string;
        status: string;
        vectorDatabaseId: string;
        aclVisibility?: string;
        readTools: string[];
        runtimeGate?: {
          state?: string;
          readyForRuntime?: boolean;
          blockers?: string[];
        };
      }>;
      runtimeGate?: {
        ready: number;
        blocked: number;
        states: CompanySetupCount[];
        blockers: CompanySetupCount[];
      };
    };
    vectorStores: {
      total: number;
      linked: number;
      collections: string[];
    };
    gaps: Array<{ key: string; label: string; target: string }>;
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
    publishableSkillPackages?: number;
  };
  runtime: {
    sessions: number;
    runtimeKinds: CompanySetupCount[];
    sessionContracts?: {
      total: number;
      withContract: number;
      selectedSkill: number;
      pendingApprovals: number;
      artifactOutputs: number;
      traceIds: number;
      replayReady: number;
      creditsSpent: number;
      runtimeKinds: CompanySetupCount[];
    };
    artifacts: number;
    pendingApprovals: number;
    approvedApprovals: number;
    workItems: number;
    runningWorkItems: number;
    reviewWorkItems: number;
  };
  runtimePolicyMap?: {
    defaultBrowserUse: string;
    browserRestrictedByDomain: boolean;
    runtimeClasses: {
      declared: CompanySetupCount[];
      observed: CompanySetupCount[];
      apiCapabilities: number;
      browserCapabilities: number;
      browserSessions: number;
    };
    approvalBoundaries: {
      skills: CompanySetupCount[];
      tools: CompanySetupCount[];
      all: CompanySetupCount[];
    };
    humanApproval: {
      pending: number;
      approved: number;
      writesProtected: boolean;
      sendsProtected: boolean;
    };
    gaps: Array<{ key: string; label: string; target: string }>;
  };
  workOrchestration?: {
    queues: {
      total: number;
      byStatus: CompanySetupCount[];
      running: number;
      review: number;
      blockedByApproval: number;
    };
    triggers: {
      manual: number;
      scheduled: number;
      due: number;
      upcoming: number;
      frequencies: CompanySetupCount[];
    };
    budgets: {
      budgetedItems: number;
      exhaustedItems: number;
      totalMaxBudgetCredits: number;
      latestCreditsSpent: number;
    };
    retries: {
      itemsRetried: number;
      maxRetryCount: number;
      totalRetryCount: number;
    };
    approvalBoundary: {
      pendingApprovals: number;
      workItemsBlocked: number;
      linkedApprovalWorkItems: number;
    };
    sla: {
      reviewBlocked: number;
      scheduledDue: number;
      budgetExhausted: number;
      needsAttention: number;
    };
  };
  governance: {
    credentials: number;
    allowedOrigins: string[];
    allowedOriginHosts: string[];
    hostJwtConfigured: boolean;
    discoveredDomains: string[];
    skillPolicies: CompanySetupCount[];
    resourceAcl?: {
      documents: number;
      withAcl: number;
      companyVisible: number;
      restricted: number;
      visibility: CompanySetupCount[];
    };
  };
  integration?: {
    systems: number;
    secrets: number;
    environments: CompanySetupCount[];
    domainAllowlist: string[];
    approvalBoundary: {
      pending: number;
      approved: number;
      skillPolicies: CompanySetupCount[];
    };
    acl: {
      ownerEmail: string;
      hostJwtConfigured: boolean;
      allowedOrigins: string[];
      resourceVisibility?: CompanySetupCount[];
      resourcesWithAcl?: number;
      resourceAclComplete?: boolean;
    };
    compliance: {
      browserRestrictedByDomain: boolean;
      humanApprovalConfigured: boolean;
      resourceAclComplete?: boolean;
      auditEvidence: {
        sessions: number;
        artifacts: number;
        evalRuns: number;
      };
    };
  };
  capabilityMap?: {
    taskContracts: {
      total: number;
      ready: number;
      coverageRatio: number;
      businessIntents: CompanySetupCount[];
      allowedSystems: string[];
      expectedArtifacts: string[];
      riskClasses: CompanySetupCount[];
    };
    benchmarks: {
      total: number;
      verticals: CompanySetupCount[];
      tasks: number;
      evalRuns: number;
    };
    evalGate?: {
      totalSkills: number;
      benchmarkLinked: number;
      regressionLinked: number;
      passing: number;
      failing: number;
      pending: number;
      missing: number;
      blockedByRegression: number;
      sample: Array<{
        skillId: string;
        name: string;
        state: string;
        benchmarkIds: string[];
        evalIds: string[];
        latestLabel: string;
        blockers: string[];
      }>;
    };
    tools: {
      total: number;
      typed: number;
      typedRatio: number;
      sideEffects: CompanySetupCount[];
      mappedEntities: string[];
    };
    skills: {
      total: number;
      ready: number;
      hardened: number;
      hardenedRatio: number;
      expectedArtifacts: string[];
      policies: CompanySetupCount[];
      packages?: {
        total: number;
        manifestReady: number;
        publishable: number;
        withIoContract: number;
        withExpectedArtifacts: number;
        withRegressionSuite: number;
        versioned: number;
        blocked: number;
        packages?: Array<{
          skillId: string;
          name: string;
          manifestReady: boolean;
          publishable: boolean;
          checks: {
            activation: boolean;
            instructions: boolean;
            riskPolicy: boolean;
            sourceTrajectory: boolean;
            ioContract: boolean;
            expectedArtifacts: boolean;
            regressionSuite: boolean;
          };
          blockers: string[];
          versioned: boolean;
        }>;
      };
    };
    gaps: Array<{ key: string; label: string; target: string }>;
  };
  readiness?: {
    score: number;
    passed: number;
    total: number;
    checks: Record<string, boolean>;
    gaps: Array<{ key: string; label: string; target: string }>;
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
  allowedDomains?: string[];
  browserRestrictedByDomain?: boolean;
  browserDefaultUse?: string;
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
    orchestration?: {
      queueState?: string;
      triggerType?: string;
      schedule?: {
        frequency?: string;
        time?: string;
        dayOfWeek?: number;
        nextRunAt?: string;
        deadlineState?: string;
      };
      budget?: {
        maxCreditsPerRun?: number;
        maxBudgetCredits?: number;
        latestCreditsSpent?: number;
        remainingCredits?: number;
        exhausted?: boolean;
      };
      retry?: {
        runAttempts?: number;
        retryCount?: number;
        maxSteps?: number;
      };
      approval?: {
        pendingApprovalCount?: number;
        reviewBlocked?: boolean;
      };
      browserPolicy?: {
        enabled?: boolean;
        defaultUse?: string;
        restrictedByDomain?: boolean;
        allowedDomains?: string[];
        requiresSandbox?: boolean;
        leastPrivilege?: boolean;
        state?: string;
      };
      sla?: {
        state?: string;
        deadlineState?: string;
        dueAt?: string;
        minutesUntilDue?: number | null;
        overdueMinutes?: number;
        needsAttention?: boolean;
        needsHumanReview?: boolean;
      };
      automationGate?: {
        state?: string;
        canRunUnattended?: boolean;
        blockers?: string[];
        nextActions?: string[];
        policy?: {
          requiresSchedule?: boolean;
          requiresApprovalClearance?: boolean;
          requiresBudget?: boolean;
          requiresBrowserAllowlist?: boolean;
          maxSteps?: number;
        };
      };
      auditTrail?: {
        uniform?: boolean;
        eventCount?: number;
        events?: Array<{
          event?: string;
          actor?: string;
          state?: string;
          count?: number;
          creditsSpent?: number;
          pendingApprovalCount?: number;
          at?: string;
          description?: string;
        }>;
        hasApprovalCheckpoint?: boolean;
        hasBudgetCheckpoint?: boolean;
        hasRetryCheckpoint?: boolean;
        hasScheduleCheckpoint?: boolean;
        hasBrowserPolicyCheckpoint?: boolean;
      };
    };
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
  capabilityDiscovery?: {
    mode?: string;
    status?: string;
    surface?: string;
    docs?: {
      available?: boolean;
      urls?: string[];
      surfaceUrls?: string[];
      generationStatus?: string;
    };
    auth?: {
      required?: boolean;
      requiredFields?: string[];
      configuredFields?: number;
      totalFields?: number;
    };
    entityDiscovery?: {
      source?: string;
      status?: string;
    };
    entityMapping?: {
      status?: "mapped" | "source_ready" | "pending" | string;
      businessObjectCount?: number;
      businessObjects?: string[];
      source?: string;
      sourceUrls?: string[];
      permissions?: {
        readTools?: string[];
        writeTools?: string[];
      };
      readyForToolBinding?: boolean;
      nextAction?: string;
    };
    toolSynthesis?: {
      toolCount?: number;
      typedToolCount?: number;
      typedTools?: string[];
      writeToolCount?: number;
      writeTools?: string[];
      runtimeRequirements?: string[];
    };
    candidateTasks?: {
      recommended?: boolean;
      source?: string;
      reason?: string;
    };
    ingestionPipeline?: {
      state?: string;
      readyStages?: number;
      totalStages?: number;
      nextStage?: {
        key?: string;
        label?: string;
        status?: string;
        target?: string;
        summary?: string;
      } | null;
      stages?: Array<{
        key?: string;
        label?: string;
        status?: string;
        target?: string;
        summary?: string;
      }>;
    };
    gaps?: { key?: string; label?: string; target?: string }[];
  };
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
  resourceId?: string;
  resourceKind?: "document" | string;
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
  resourceContract?: {
    resourceId?: string;
    resourceKind?: "document" | string;
    surface?: string;
    readOnly?: boolean;
    status?: string;
    indexing?: {
      indexed?: boolean;
      vectorDatabaseId?: string;
      vectorDatabaseName?: string;
      vectorCollectionName?: string;
    };
    governance?: {
      companyId?: string;
      connectorId?: string;
      source?: string;
      contentType?: string;
      size?: number;
      acl?: {
        visibility?: string;
        allowedRoles?: string[];
        allowedUsers?: string[];
      };
      versioning?: {
        version?: number;
        versionLabel?: string;
        createdAt?: string;
        updatedAt?: string;
      };
      freshness?: {
        lastIndexedAt?: string;
        stale?: boolean;
        status?: string;
      };
      citability?: {
        citable?: boolean;
        citationLabel?: string;
        sourceUrl?: string;
      };
    };
    readTools?: string[];
    resourceGate?: {
      state?: "ready" | "blocked" | "indexing" | string;
      readyForRuntime?: boolean;
      blockers?: string[];
      nextActions?: string[];
      checks?: Record<string, boolean>;
    };
  };
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
  entityMapping?: {
    businessObject?: string;
    aliases?: string[];
    systemObjects?: {
      sourceConnectorId?: string;
      source?: string;
      schemaName?: string;
      sourcePaths?: string[];
    };
    relationshipTargets?: string[];
    permissions?: {
      readTools?: string[];
      writeTools?: string[];
      scopes?: string[];
    };
    readiness?: {
      status?: string;
      gaps?: string[];
      hasIdentifier?: boolean;
      hasRelationships?: boolean;
    };
  };
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

export type CapabilityGraphNodeKind = "connector" | "entity" | "tool" | "benchmark" | "task" | "trajectory" | "skill" | string;

export interface CapabilityGraphNode {
  id: string;
  kind: CapabilityGraphNodeKind;
  refId: string;
  label: string;
  payload?: Record<string, any>;
}

export interface CapabilityGraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  evidence?: Record<string, any>;
}

export interface CapabilityGraphCoverage {
  entities?: {
    total?: number;
    linked?: boolean;
  };
  resources?: {
    total?: number;
    indexed?: number;
    citable?: number;
    withResourceContract?: number;
    withReadTools?: number;
    vectorStores?: number;
    linkedVectorStores?: number;
    linkedToConnectors?: boolean;
    linkedToTools?: boolean;
    linkedToTasks?: boolean;
    linkedToSkills?: boolean;
  };
  tools?: {
    total?: number;
    ready?: number;
    governed?: number;
  };
  policies?: {
    policyNodes?: number;
    writeCapabilities?: number;
    writesProtected?: boolean;
    sendProtected?: boolean;
    browserCapabilities?: number;
    browserSandboxed?: boolean;
    domainRestricted?: boolean;
    highRiskTools?: number;
    approvalModes?: string[];
  };
  benchmarks?: {
    total?: number;
    tasks?: number;
    tasksWithContracts?: number;
  };
  verticalDemos?: {
    total?: number;
    ready?: number;
    partial?: number;
    missing?: number;
    linkedToBenchmarks?: boolean;
    runtimeReplayReady?: number;
  };
  evals?: {
    runs?: number;
    pass?: number;
    fail?: number;
    pending?: number;
    linkedToTasks?: boolean;
    linkedToSkills?: boolean;
    linkedToRuntime?: boolean;
  };
  trajectories?: {
    total?: number;
    approved?: number;
  };
  skills?: {
    total?: number;
    ready?: number;
    reusable?: number;
    packages?: {
      manifestReady?: number;
      activation?: number;
      instructions?: number;
      ioContracts?: number;
      expectedArtifacts?: number;
      riskPolicies?: number;
      sourceTrajectories?: number;
      regressionSuites?: number;
      publishable?: number;
      versioned?: number;
    };
  };
  runtime?: {
    sessions?: number;
    sessionContracts?: {
      withContract?: number;
      selectedSkill?: number;
      pendingApprovals?: number;
      artifactOutputs?: number;
      traceIds?: number;
      replayReady?: number;
      creditsSpent?: number;
    };
    approvals?: number;
    pendingApprovals?: number;
    artifacts?: number;
    linkedSessions?: boolean;
    linkedApprovals?: boolean;
    linkedArtifacts?: boolean;
  };
  work?: {
    total?: number;
    scheduled?: number;
    running?: number;
    review?: number;
    blockedByApproval?: number;
    orchestration?: {
      withContract?: number;
      scheduled?: number;
      budgeted?: number;
      budgetExhausted?: number;
      retryConfigured?: number;
      runAttempts?: number;
      slaTracked?: number;
      slaNeedsAttention?: number;
      approvalGates?: number;
      auditTrails?: number;
      browserPolicies?: number;
      browserAllowlists?: number;
      unattendedReady?: number;
    };
    linkedToTasks?: boolean;
    linkedToRuntime?: boolean;
    linkedToCapabilities?: boolean;
  };
  promotionPath?: {
    hasTaskToTrajectory?: boolean;
    hasTrajectoryToSkill?: boolean;
    hasToolToSkill?: boolean;
  };
}

export interface CapabilityGraph {
  companyId: string;
  nodes: CapabilityGraphNode[];
  edges: CapabilityGraphEdge[];
  coverage?: CapabilityGraphCoverage;
}

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
  policyBoundary?: string;
  approvalPolicy?: ToolApprovalPolicy;
  scopes?: string[];
  toolContract?: ToolContract;
  riskLevel: string;
  status: string;
  source: string;
  discovererName?: string;
  discovererVersion?: string;
  discoveryScope?: string;
  discoveryRelevance?: Record<string, any>;
  discoveryEvidence?: any[];
  toolSynthesis?: {
    toolId?: string;
    action?: string;
    atomic?: boolean;
    typedInput?: boolean;
    typedOutput?: boolean;
    sideEffects?: string;
    riskLevel?: string;
    riskClassification?: {
      level?: string;
      requiresApproval?: boolean;
      approvalMode?: string;
    };
    permissions?: {
      scopes?: string[];
      readTools?: string[];
      writeTools?: string[];
      approval?: string;
    };
    entityBindings?: {
      inputEntities?: string[];
      outputEntity?: string;
      declared?: boolean;
    };
    readiness?: {
      status?: string;
      gaps?: string[];
    };
  };
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

export interface RuntimePolicy {
  policy: string;
  approvalMode: "always" | "auto" | "never" | string;
  approvalRequiredFor: string[];
  writesRequireApproval: boolean;
  sendsRequireApproval: boolean;
  browserRuntime: boolean;
  runtimeClass: "api" | "browser" | "hybrid" | string;
  runtimeType?: string;
  runtimeTypes?: string[];
  runtimeRequirements: string[];
  browserPolicy?: {
    defaultUse?: string;
    restrictedByDomain?: boolean;
    allowedDomains?: string[];
    requiresSandbox?: boolean;
    leastPrivilege?: boolean;
  };
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
  policyBoundary?: string;
  approvalPolicy?: ToolApprovalPolicy;
  scopes?: string[];
  toolContract?: ToolContract;
  riskPolicy: string;
  runtimePolicy?: RuntimePolicy;
  runtime: string;
  status: string;
  promotionStatus?: string;
  version?: number;
  versionLabel?: string;
  publishedAt?: string;
  readyAt?: string;
  archivedAt?: string;
  lastPromotedAt?: string;
  versionHistory?: {
    version?: number;
    versionLabel?: string;
    promotionStatus?: string;
    reason?: string;
    createdAt?: string;
  }[];
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
  skillPackage?: {
    format?: string;
    manifestVersion?: number;
    packageId?: string;
    metadata?: {
      name?: string;
      description?: string;
      version?: number;
      versionLabel?: string;
      promotionStatus?: string;
      source?: string;
      createdAt?: string;
      updatedAt?: string;
    };
    activation?: {
      description?: string;
      preconditions?: string[];
    };
    interface?: {
      inputEntities?: string[];
      outputEntity?: string;
      expectedArtifacts?: string[];
      outputCard?: Record<string, any>;
      ioContract?: {
        inputs?: {
          entities?: string[];
          preconditions?: string[];
        };
        outputs?: {
          entity?: string;
          artifacts?: string[];
          outputCard?: Record<string, any>;
        };
        declared?: boolean;
      };
    };
    ioContract?: {
      inputs?: {
        entities?: string[];
        preconditions?: string[];
      };
      outputs?: {
        entity?: string;
        artifacts?: string[];
        outputCard?: Record<string, any>;
      };
      declared?: boolean;
    };
    execution?: {
      instructions?: string;
      connectorIds?: string[];
      toolIds?: string[];
      trajectoryIds?: string[];
      runtimeRequirements?: string[];
      runtime?: string;
    };
    policies?: {
      riskPolicy?: string;
      permissions?: Record<string, any>;
      runtimePolicy?: RuntimePolicy;
    };
    productionGate?: {
      state?: "publishable" | "blocked" | "needs_regression" | string;
      canPublish?: boolean;
      blockers?: string[];
      nextActions?: string[];
      checks?: Record<string, boolean>;
      latestRegression?: CompanySkill["latestRegression"];
    };
    evidence?: {
      lineage?: CompanySkill["lineage"];
      sourceTrajectories?: Array<{
        trajectoryId?: string;
        taskId?: string;
        benchmarkId?: string;
        evalId?: string;
        name?: string;
        status?: string;
        judgeLabel?: string;
        connectorIds?: string[];
        toolIds?: string[];
        actionCount?: number;
        createdAt?: string;
        updatedAt?: string;
      }>;
      latestRegression?: CompanySkill["latestRegression"];
      hardeningStatus?: CompanySkill["hardeningStatus"];
      versionHistory?: CompanySkill["versionHistory"];
      regressionSuite?: {
        benchmarkIds?: string[];
        evalIds?: string[];
        cases?: Array<{
          source?: string;
          taskId?: string;
          evalId?: string;
          benchmarkId?: string;
          name?: string;
          businessIntent?: string;
          successCriteria?: string;
          riskClass?: string;
          expectedArtifacts?: string[];
          allowedSystems?: string[];
        }>;
        publishable?: boolean;
      };
    };
    progressiveDisclosure?: {
      summaryFields?: string[];
      fullFields?: string[];
    };
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
  skillId?: string;
  trajectoryId?: string;
  toolId?: string;
  workItemId?: string;
  capabilityRefs?: {
    skillId?: string;
    trajectoryId?: string;
    toolId?: string;
    workItemId?: string;
    linked?: boolean;
  };
  artifactContract?: {
    artifactId?: string;
    outputKind?: string;
    businessOutput?: boolean;
    separatedFromTrace?: boolean;
    runtimeLinked?: boolean;
    capabilityLinked?: boolean;
    workLinked?: boolean;
    source?: {
      sessionId?: string;
      sourceTool?: string;
      skillId?: string;
      trajectoryId?: string;
      toolId?: string;
      workItemId?: string;
    };
    governance?: {
      approvalState?: string;
      requiresReview?: boolean;
      approvalRelation?: ArtifactApprovalRelation;
      knowledgeReady?: boolean;
    };
    nextActions?: string[];
  };
  title: string;
  artifactType: string;
  description: string;
  content: string;
  fileName: string;
  sourceTool?: string;
  approvalRelation?: ArtifactApprovalRelation;
  metadata?: Record<string, any>;
  createdAt?: string;
  updatedAt?: string;
}
