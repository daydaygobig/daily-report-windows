import axios from "axios";

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type GithubDeployment = {
  id: number;
  execution_id: number | null;
  job_id: number | null;
  task_id: number | null;
  github_config_id: number | null;
  job_name?: string | null;
  task_name?: string | null;
  config_name?: string | null;
  artifact_type?: string | null;
  artifact_label?: string | null;
  repo_full_name?: string | null;
  branch?: string | null;
  repo_path?: string | null;
  github_file_url?: string | null;
  status: string;
  pages_url?: string | null;
  error_msg?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
};

export type GithubDeploymentQuery = {
  page: number;
  page_size: number;
  task_id?: number;
  job_id?: number;
  config_id?: number;
  status?: string;
  start_time?: string;
  end_time?: string;
  record_id?: number;
};

export type GithubDeploymentPage = {
  total: number;
  page: number;
  page_size: number;
  items: GithubDeployment[];
};

export async function fetchGithubDeployments(params: GithubDeploymentQuery): Promise<GithubDeploymentPage> {
  const response = await axios.get<ApiResponse<GithubDeploymentPage>>("/api/github-deployments/", { params });
  return response.data.data;
}
