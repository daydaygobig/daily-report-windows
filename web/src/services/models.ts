import axios from "axios";

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type Model = {
  id: number;
  name: string;
  provider: string;
  base_url?: string | null;
  api_key?: string | null;
  max_tokens?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  extra?: Record<string, unknown> | null;
  request_standard: string;
  created_at: string;
  updated_at: string;
};

export type ModelCreatePayload = {
  name: string;
  provider: string;
  base_url?: string | null;
  api_key: string;
  max_tokens?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  extra?: Record<string, unknown> | null;
  request_standard?: string;
};

export type ModelUpdatePayload = Partial<Omit<ModelCreatePayload, "api_key">> & {
  api_key?: string;
};

export type ModelTestPayload = {
  model_id?: number;
  provider?: string;
  base_url?: string | null;
  api_key?: string;
  max_tokens?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  extra?: Record<string, unknown> | null;
  timeout?: number;
  prompt?: string;
  request_standard?: string;
};

export type RemoteModelsPayload = {
  model_id?: number;
  base_url?: string | null;
  api_key?: string;
};

export async function fetchModels(): Promise<Model[]> {
  const response = await axios.get<ApiResponse<Model[]>>("/api/models/");
  return response.data.data;
}

export async function createModel(payload: ModelCreatePayload): Promise<Model> {
  const response = await axios.post<ApiResponse<Model>>("/api/models/", payload);
  return response.data.data;
}

export async function updateModel(modelId: number, payload: ModelUpdatePayload): Promise<Model> {
  const response = await axios.put<ApiResponse<Model>>(`/api/models/${modelId}`, payload);
  return response.data.data;
}

export async function deleteModel(modelId: number): Promise<void> {
  await axios.delete<ApiResponse<null>>(`/api/models/${modelId}`);
}

export async function fetchRemoteModels(payload: RemoteModelsPayload): Promise<string[]> {
  const response = await axios.post<ApiResponse<{ models: string[] }>>("/api/models/fetch-remote-models", payload);
  return response.data.data.models ?? [];
}

export async function testModelConnection(payload: ModelTestPayload): Promise<void> {
  await axios.post<ApiResponse<{ ok: boolean }>>(`/api/models/test-connection`, payload);
}
