import axios from "axios";

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type ChatRecordProvider = "chatlog" | "weflow";

export type ChatRecordSettings = {
  id: number;
  provider: ChatRecordProvider;
  chatlog_base_url: string;
  chatlog_timeout_sec: number;
  chatlog_decrypt_before_fetch: boolean;
  chatlog_decrypt_cache_enabled: boolean;
  chatlog_decrypt_timeout_sec: number;
  chatlog_decrypt_cache_buffer_sec: number;
  chatlog_work_dir: string;
  weflow_base_url: string;
  has_weflow_token: boolean;
  weflow_page_limit: number;
  weflow_page_timeout_sec: number;
  weflow_empty_page_retry: number;
  weflow_include_media: boolean;
};

export type ChatRecordSettingsPayload = Omit<ChatRecordSettings, "id" | "has_weflow_token" | "weflow_include_media"> & {
  weflow_token?: string;
};

export type ChatRecordStatus = {
  provider: ChatRecordProvider;
  status: string;
  message: string;
};

export type Chatroom = {
  name: string;
  display_name: string;
  owner?: string | null;
  user_count: number;
};

export async function fetchChatRecordSettings(): Promise<ChatRecordSettings> {
  const response = await axios.get<ApiResponse<ChatRecordSettings>>("/api/chat-records/settings");
  return response.data.data;
}

export async function updateChatRecordSettings(payload: ChatRecordSettingsPayload): Promise<ChatRecordSettings> {
  const response = await axios.put<ApiResponse<ChatRecordSettings>>("/api/chat-records/settings", payload);
  return response.data.data;
}

export async function testChatRecordSettings(payload: ChatRecordSettingsPayload) {
  const response = await axios.post<ApiResponse<{ ok: boolean; provider: ChatRecordProvider; status: string; message: string }>>(
    "/api/chat-records/settings/test",
    payload
  );
  return response.data.data;
}

export async function fetchChatRecordStatus(): Promise<ChatRecordStatus> {
  const response = await axios.get<ApiResponse<ChatRecordStatus>>("/api/chat-records/status");
  return response.data.data;
}

export async function fetchChatrooms(keyword?: string, talkers?: string[]): Promise<Chatroom[]> {
  const response = await axios.get<ApiResponse<Chatroom[]>>("/api/chat-records/chatrooms", {
    params: {
      keyword: keyword?.trim() || undefined,
      talkers: talkers && talkers.length ? talkers.join(",") : undefined
    }
  });
  return response.data.data;
}
