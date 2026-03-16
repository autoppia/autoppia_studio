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

export interface ParameterizeResult {
  name: string;
  goal: string;
  instructions: string;
  parameters: SkillParameter[];
  actions: any[];
}