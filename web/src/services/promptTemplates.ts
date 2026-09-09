import apiClient from "./apiClient";
import type { ApiResponse } from "./apiClient";

export type PromptTemplate = {
  id: number;
  name: string;
  content: string;
  description?: string | null;
  template_type: "regular" | "image";
  image_split_enabled: boolean;
  image_split_prompt?: string | null;
  created_at: string;
  updated_at: string;
};

export type PromptTemplatePayload = {
  name: string;
  content: string;
  description?: string;
  template_type?: "regular" | "image";
  image_split_enabled?: boolean;
  image_split_prompt?: string | null;
};

export const DEFAULT_IMAGE_SPLIT_PROMPT = [
  "请将最终结果拆分成一个或多个独立内容块，每个内容块对应一张图片。",
  "",
  "每个内容块必须严格按照以下格式输出：",
  "",
  "${block_start}",
  "请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。",
  "${block_end}",
  "",
  "不要把两个独立内容合并到同一个内容块；不要在开始和结束标识之外输出其他正文。"
].join("\n");

const IMAGE_SPLIT_PROMPT_REPLACEMENTS: Array<[string, string]> = [
  [
    "请把最终结果拆分成一个或多个独立内容块：一个完整职场案例对应一个内容块，也对应一张图片。",
    "请将最终结果拆分成一个或多个独立内容块，每个内容块对应一张图片。"
  ],
  ["这里放一个案例的完整生图提示词", "请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。"],
  ["这里放一个案例的完整 Markdown 内容", "请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。"],
  ["这里输出一个案例的完整 Markdown 内容", "请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。"],
  [
    "请根据聊天记录生成该话题的完整正文，不要原样输出本行说明。",
    "请根据输入内容生成该内容块的完整正文，不要原样输出本行说明。"
  ],
  ["不要把两个案例放进同一个内容块", "不要把两个独立内容合并到同一个内容块"]
];

export const normalizeImageSplitPrompt = (value?: string | null): string =>
  IMAGE_SPLIT_PROMPT_REPLACEMENTS.reduce(
    (result, [source, target]) => result.replace(source, target),
    value || DEFAULT_IMAGE_SPLIT_PROMPT
  );

export async function fetchPromptTemplates(): Promise<PromptTemplate[]> {
  const response = await apiClient.get<ApiResponse<PromptTemplate[]>>("/api/prompt-templates/");
  return response.data.data;
}

export async function createPromptTemplate(payload: PromptTemplatePayload): Promise<PromptTemplate> {
  const response = await apiClient.post<ApiResponse<PromptTemplate>>("/api/prompt-templates/", payload);
  return response.data.data;
}

export async function updatePromptTemplate(id: number, payload: PromptTemplatePayload): Promise<PromptTemplate> {
  const response = await apiClient.put<ApiResponse<PromptTemplate>>(`/api/prompt-templates/${id}`, payload);
  return response.data.data;
}

export async function deletePromptTemplate(id: number): Promise<void> {
  await apiClient.delete<ApiResponse<null>>(`/api/prompt-templates/${id}`);
}
