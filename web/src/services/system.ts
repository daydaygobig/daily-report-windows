import axios from "axios";

type SystemStatus = {
  app_name: string;
  server_time: string;
  chatlog_status: string;
  chat_record_provider?: "chatlog" | "weflow";
  chat_record_status?: string;
  chat_record_status_message?: string;
  next_execution: string | null;
  executions_today: number;
  tasks: number;
  jobs: number;
};

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const response = await axios.get("/api/system/status");
  return response.data.data as SystemStatus;
}

export async function downloadSystemLog(name: string): Promise<Blob> {
  const response = await axios.get(`/api/system/logs`, {
    params: { name },
    responseType: "blob"
  });
  return response.data as Blob;
}
