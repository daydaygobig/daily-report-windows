import apiClient from "./apiClient";
import type { ApiResponse } from "./apiClient";

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
  model_type: "text" | "image";
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
  model_type?: "text" | "image";
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
  model_type?: "text" | "image";
};

export type ModelTestResult = {
  ok: boolean;
  preview?: string;
};

export type RemoteModelsPayload = {
  model_id?: number;
  base_url?: string | null;
  api_key?: string;
};

export async function fetchModels(): Promise<Model[]> {
  const response = await apiClient.get<ApiResponse<Model[]>>("/api/models/");
  return response.data.data;
}

export async function createModel(payload: ModelCreatePayload): Promise<Model> {
  const response = await apiClient.post<ApiResponse<Model>>("/api/models/", payload);
  return response.data.data;
}

export async function updateModel(modelId: number, payload: ModelUpdatePayload): Promise<Model> {
  const response = await apiClient.put<ApiResponse<Model>>(`/api/models/${modelId}`, payload);
  return response.data.data;
}

export async function deleteModel(modelId: number): Promise<void> {
  await apiClient.delete<ApiResponse<null>>(`/api/models/${modelId}`);
}

export async function fetchRemoteModels(payload: RemoteModelsPayload): Promise<string[]> {
  const response = await apiClient.post<ApiResponse<{ models: string[] }>>("/api/models/fetch-remote-models", payload);
  return response.data.data.models ?? [];
}

export async function testModelConnection(payload: ModelTestPayload): Promise<ModelTestResult> {
  const response = await apiClient.post<ApiResponse<ModelTestResult>>(`/api/models/test-connection`, payload);
  return response.data.data;
}
