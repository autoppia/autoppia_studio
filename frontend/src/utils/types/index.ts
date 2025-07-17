export interface HistoryItem {
    email: string;
    socketioPath: string;
    prompt: string;
    initialUrl: string;
    historyPath: string;
    createdAt?: Date;
}

export interface ChatItem {
  role: string;
  content?: string;
  socketId?: string;
  actions?: string[];
  actionResults?: boolean[];
  thinking?: string;
  state?: string;
}