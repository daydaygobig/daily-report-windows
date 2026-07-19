import axios from "axios";

export type Alert = {
  id: number;
  category: string;
  message: string;
  level: string;
  execution_id?: number | null;
  created_at: string;
};

export async function fetchAlerts(): Promise<Alert[]> {
  const response = await axios.get("/api/alerts/");
  return response.data.data as Alert[];
}
