import apiClient from "./apiClient";
import type { ApiResponse } from "./apiClient";

export type GithubConfig = {
  id: number;
  name: string;
  owner: string;
  repo: string;
  branch: string;
  path_prefix?: string | null;
  filename_template: string;
  pages_base_url?: string | null;
  view_url_mode: "github_pages" | "custom_template";
  view_url_template?: string | null;
  is_default: boolean;
  description?: string | null;
  has_token: boolean;
  token?: string | null;
  created_at: string;
  updated_at: string;
};

export type GithubConfigPayload = {
  name: string;
  owner: string;
  repo: string;
  branch?: string;
  path_prefix?: string | null;
  filename_template?: string;
  pages_base_url?: string | null;
  view_url_mode?: "github_pages" | "custom_template";
  view_url_template?: string | null;
  is_default?: boolean;
  description?: string | null;
  // 编辑模式下 token 可不下发（后端保留原值），故为可选
  token?: string;
};

export type GithubConfigUpdatePayload = Partial<Omit<GithubConfigPayload, "token">> & {
  token?: string;
};

export type GithubRepoInfo = {
  owner: string;
  repo: string;
  full_name: string;
  default_branch: string;
  private: boolean;
  pages_base_url: string;
};

export type GithubTokenTestResult = {
  login: string;
  repos: GithubRepoInfo[];
};

export async function fetchGithubConfigs(): Promise<GithubConfig[]> {
  const response = await apiClient.get<ApiResponse<GithubConfig[]>>("/api/github-configs/");
  return response.data.data;
}

export async function createGithubConfig(payload: GithubConfigPayload): Promise<GithubConfig> {
  const response = await apiClient.post<ApiResponse<GithubConfig>>("/api/github-configs/", payload);
  return response.data.data;
}

export async function updateGithubConfig(id: number, payload: GithubConfigUpdatePayload): Promise<GithubConfig> {
  const response = await apiClient.put<ApiResponse<GithubConfig>>(`/api/github-configs/${id}`, payload);
  return response.data.data;
}

export async function deleteGithubConfig(id: number): Promise<void> {
  await apiClient.delete<ApiResponse<null>>(`/api/github-configs/${id}`);
}

export async function testGithubToken(token: string, owner?: string, per_page = 50): Promise<GithubTokenTestResult> {
  const response = await apiClient.post<ApiResponse<GithubTokenTestResult>>("/api/github-configs/test", {
    token,
    owner,
    per_page
  });
  return response.data.data;
}
