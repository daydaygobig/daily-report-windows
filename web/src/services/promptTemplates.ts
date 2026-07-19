import axios from "axios";

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type PromptTemplate = {
  id: number;
  name: string;
  content: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
};

export type PromptTemplatePayload = {
  name: string;
  content: string;
  description?: string;
};

export async function fetchPromptTemplates(): Promise<PromptTemplate[]> {
  const response = await axios.get<ApiResponse<PromptTemplate[]>>("/api/prompt-templates/");
  return response.data.data;
}

export async function createPromptTemplate(payload: PromptTemplatePayload): Promise<PromptTemplate> {
  const response = await axios.post<ApiResponse<PromptTemplate>>("/api/prompt-templates/", payload);
  return response.data.data;
}

export async function updatePromptTemplate(id: number, payload: PromptTemplatePayload): Promise<PromptTemplate> {
  const response = await axios.put<ApiResponse<PromptTemplate>>(`/api/prompt-templates/${id}`, payload);
  return response.data.data;
}

export async function deletePromptTemplate(id: number): Promise<void> {
  await axios.delete<ApiResponse<null>>(`/api/prompt-templates/${id}`);
}
