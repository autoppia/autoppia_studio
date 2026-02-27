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
  actionResults?: boolean[];
  screenshots?: string[];
  thinking?: string;
  state?: string;
}