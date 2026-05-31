export interface SessionItem {
    sessionId: string;
    email: string;
    socketioPath: string;
    prompt: string;
    initialUrl: string;
    sessionPath: string;
    createdAt?: Date;
}

export type HistoryItem = SessionItem;

export interface ChatItem {
  role: string;
  content?: string;
  actions?: string[];
  actionResults?: (boolean | undefined)[];
  screenshots?: string[];
  thinking?: string;
  state?: string;
  reasoning?: string;
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
  email?: string;
  prompt: string;
  initialUrl: string;
  benchmarkId?: string;
  benchmarkName?: string;
  operatorId?: string;
  operatorName?: string;
  operatorTaskName?: string;
  successCriteria?: string;
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
  operatorId?: string;
  operatorName?: string;
  operatorTaskName?: string;
  actions: any[];
  label: "pass" | "fail" | "pending";
  screenshots?: string[];
  createdAt?: string;
}

export interface OperatorTask {
  name: string;
  prompt: string;
  successCriteria?: string;
  status?: string;
  trajectoryId?: string;
}

export interface OperatorTrajectory {
  trajectoryId?: string;
  operatorId?: string;
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

export interface OperatorWeb {
  webId: string;
  operatorId: string;
  name: string;
  baseUrl: string;
  authRequired: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface OperatorCapability {
  capabilityId: string;
  operatorId: string;
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

export interface Operator {
  operatorId: string;
  email: string;
  name: string;
  websiteUrl: string;
  runtimeEndpoint: string;
  runtimeType: string;
  status: string;
  trainingStatus: string;
  harvester?: string;
  apiSpecUrl?: string;
  apiAuthConfigured?: boolean;
  tasks: OperatorTask[];
  trajectories: OperatorTrajectory[];
  successCriteria: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface ParameterizeResult {
  name: string;
  goal: string;
  instructions: string;
  parameters: SkillParameter[];
  actions: any[];
}
