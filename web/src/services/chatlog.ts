import axios from "axios";

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type Chatroom = {
  name: string;
  display_name: string;
  owner?: string | null;
  user_count: number;
};

export async function fetchChatrooms(keyword?: string, talkers?: string[]): Promise<Chatroom[]> {
  const response = await axios.get<ApiResponse<Chatroom[]>>("/api/chat-records/chatrooms", {
    params: {
      keyword: keyword?.trim() || undefined,
      talkers: talkers && talkers.length ? talkers.join(",") : undefined
    }
  });
  return response.data.data;
}
