import apiClient from "./apiClient";

export type Alert = {
  id: number;
  category: string;
  message: string;
  level: string;
  execution_id?: number | null;
  created_at: string;
};

export async function fetchAlerts(): Promise<Alert[]> {
  const response = await apiClient.get("/api/alerts/");
  return response.data.data as Alert[];
}
