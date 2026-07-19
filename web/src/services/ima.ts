import axios from "axios";

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type ImaTargetType = "note" | "knowledge_base";
export type ImaSyncStatus = "success" | "failed" | "skipped" | "partial" | "none";
export type ImaTriggerType = "manual" | "auto" | "job";
export type ImaSyncScope = "daily_report_job" | "ima_sync_job";

export type ImaOption = {
  label: string;
  value: string;
};

export type ImaCredentialPreview = {
  client_id: string;
  api_key: string;
};

export type ImaAccount = {
  id: number;
  created_at: string;
  updated_at: string;
  name: string;
  client_id: string;
  api_key: string;
  client_id_masked: string;
  is_enabled: boolean;
  is_default: boolean;
  remark?: string | null;
  default_target_type: ImaTargetType;
  default_note_folder_id?: string | null;
  default_note_folder_name?: string | null;
  default_knowledge_base_id?: string | null;
  default_knowledge_base_name?: string | null;
  default_knowledge_folder_id?: string | null;
  default_knowledge_folder_name?: string | null;
  last_test_at?: string | null;
  last_test_status?: string | null;
  last_test_message?: string | null;
};

export type ImaAccountPayload = {
  name: string;
  client_id: string;
  api_key: string;
  is_enabled: boolean;
  is_default: boolean;
  remark?: string | null;
  default_target_type: ImaTargetType;
  default_note_folder_id?: string | null;
  default_note_folder_name?: string | null;
  default_knowledge_base_id?: string | null;
  default_knowledge_base_name?: string | null;
  default_knowledge_folder_id?: string | null;
  default_knowledge_folder_name?: string | null;
};

export type ImaSyncSettings = {
  id: number;
  created_at: string;
  updated_at: string;
  default_account_id?: number | null;
  default_account_name?: string | null;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_sync_summary?: string | null;
  next_run_at?: string | null;
};

export type ImaSyncSettingsPayload = {
  default_account_id?: number | null;
};

export type ImaSyncRecord = {
  id: number;
  created_at: string;
  updated_at: string;
  batch_id?: string | null;
  trigger_type: ImaTriggerType;
  source_type: string;
  source_path?: string | null;
  source_name?: string | null;
  source_size?: number | null;
  source_mtime?: string | null;
  ima_account_id?: number | null;
  ima_account_name?: string | null;
  sync_job_id?: number | null;
  sync_job_name?: string | null;
  sync_scope: ImaSyncScope;
  task_id?: number | null;
  task_name?: string | null;
  job_id?: number | null;
  job_name?: string | null;
  execution_id?: number | null;
  target_type: ImaTargetType;
  note_folder_id?: string | null;
  note_folder_name?: string | null;
  knowledge_base_id?: string | null;
  knowledge_base_name?: string | null;
  knowledge_folder_id?: string | null;
  knowledge_folder_name?: string | null;
  status: ImaSyncStatus;
  skip_reason?: string | null;
  error_code?: number | null;
  error_explanation?: string | null;
  error_message?: string | null;
  remote_doc_id?: string | null;
  remote_media_id?: string | null;
};

export type ImaSyncJob = {
  id: number;
  created_at: string;
  updated_at: string;
  name: string;
  is_enabled: boolean;
  ima_account_id?: number | null;
  ima_account_name?: string | null;
  target_type: ImaTargetType;
  note_folder_id?: string | null;
  note_folder_name?: string | null;
  knowledge_base_id?: string | null;
  knowledge_base_name?: string | null;
  knowledge_folder_id?: string | null;
  knowledge_folder_name?: string | null;
  local_sync_path: string;
  recursive_enabled: boolean;
  allowed_extensions: ("md" | "txt")[];
  schedule_frequency: "daily" | "weekly";
  schedule_weekday?: number | null;
  schedule_time: string;
  webhook_id?: number | null;
  webhook_name?: string | null;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_sync_summary?: string | null;
  next_run_at?: string | null;
};

export type ImaSyncJobPayload = {
  name: string;
  is_enabled: boolean;
  ima_account_id: number;
  target_type: ImaTargetType;
  note_folder_id?: string | null;
  note_folder_name?: string | null;
  knowledge_base_id?: string | null;
  knowledge_base_name?: string | null;
  knowledge_folder_id?: string | null;
  knowledge_folder_name?: string | null;
  local_sync_path: string;
  recursive_enabled: boolean;
  allowed_extensions: ("md" | "txt")[];
  schedule_frequency: "daily" | "weekly";
  schedule_weekday?: number | null;
  schedule_time: string;
  webhook_id?: number | null;
};

export type ImaSyncBatch = {
  batch_id: string;
  created_at: string;
  trigger_type: ImaTriggerType;
  sync_scope: ImaSyncScope;
  ima_account_id?: number | null;
  ima_account_name?: string | null;
  sync_job_id?: number | null;
  sync_job_name?: string | null;
  task_id?: number | null;
  task_name?: string | null;
  job_id?: number | null;
  job_name?: string | null;
  execution_id?: number | null;
  target_type: ImaTargetType;
  target_display: string;
  total_count: number;
  success_count: number;
  skipped_count: number;
  failed_count: number;
  status: ImaSyncStatus;
  summary: string;
};

export type ImaSyncBatchQuery = {
  page: number;
  page_size: number;
  ima_account_id?: number;
  task_id?: number;
  job_id?: number;
  sync_job_id?: number;
  sync_scope?: ImaSyncScope;
  status?: string;
  trigger_type?: string;
  execution_id?: number;
  batch_id?: string;
  query?: string;
  start_time?: string;
  end_time?: string;
};

export type ImaSyncBatchPage = {
  items: ImaSyncBatch[];
  total: number;
  page: number;
  page_size: number;
};

export type ImaSyncRecordQuery = {
  page: number;
  page_size: number;
  ima_account_id?: number;
  task_id?: number;
  job_id?: number;
  sync_job_id?: number;
  sync_scope?: ImaSyncScope;
  status?: string;
  trigger_type?: string;
  execution_id?: number;
  batch_id?: string;
  query?: string;
  start_time?: string;
  end_time?: string;
};

export type ImaSyncRecordPage = {
  items: ImaSyncRecord[];
  total: number;
  page: number;
  page_size: number;
};

export type ImaManualSyncResult = {
  batch_id: string;
  scanned_count: number;
  success_count: number;
  skipped_count: number;
  failed_count: number;
  message: string;
};

export async function fetchImaSettings(): Promise<ImaSyncSettings> {
  const response = await axios.get<ApiResponse<ImaSyncSettings>>("/api/ima/settings");
  return response.data.data;
}

export async function updateImaSettings(payload: ImaSyncSettingsPayload): Promise<ImaSyncSettings> {
  const response = await axios.put<ApiResponse<ImaSyncSettings>>("/api/ima/settings", payload);
  return response.data.data;
}

export async function fetchImaAccounts(): Promise<ImaAccount[]> {
  const response = await axios.get<ApiResponse<ImaAccount[]>>("/api/ima/accounts");
  return response.data.data;
}

export async function createImaAccount(payload: ImaAccountPayload): Promise<ImaAccount> {
  const response = await axios.post<ApiResponse<ImaAccount>>("/api/ima/accounts", payload);
  return response.data.data;
}

export async function updateImaAccount(accountId: number, payload: ImaAccountPayload): Promise<ImaAccount> {
  const response = await axios.put<ApiResponse<ImaAccount>>(`/api/ima/accounts/${accountId}`, payload);
  return response.data.data;
}

export async function deleteImaAccount(accountId: number): Promise<void> {
  await axios.delete<ApiResponse<null>>(`/api/ima/accounts/${accountId}`);
}

export async function testImaAccount(accountId: number): Promise<{ ok: boolean; message: string }> {
  const response = await axios.post<ApiResponse<{ ok: boolean; message: string }>>(`/api/ima/accounts/${accountId}/test`);
  return response.data.data;
}

export async function testImaSettings(): Promise<{ ok: boolean; message: string }> {
  const response = await axios.post<ApiResponse<{ ok: boolean; message: string }>>("/api/ima/settings/test");
  return response.data.data;
}

export async function testImaSettingsPreview(payload: ImaCredentialPreview): Promise<{ ok: boolean; message: string }> {
  const response = await axios.post<ApiResponse<{ ok: boolean; message: string }>>("/api/ima/settings/test", payload);
  return response.data.data;
}

export async function fetchImaNoteFolders(accountId?: number): Promise<ImaOption[]> {
  const response = await axios.get<ApiResponse<ImaOption[]>>("/api/ima/options/note-folders", {
    params: accountId ? { account_id: accountId } : undefined
  });
  return response.data.data;
}

export async function fetchImaNoteFoldersPreview(payload: ImaCredentialPreview): Promise<ImaOption[]> {
  const response = await axios.post<ApiResponse<ImaOption[]>>("/api/ima/options/note-folders/preview", payload);
  return response.data.data;
}

export async function fetchImaKnowledgeBases(accountId?: number): Promise<ImaOption[]> {
  const response = await axios.get<ApiResponse<ImaOption[]>>("/api/ima/options/knowledge-bases", {
    params: accountId ? { account_id: accountId } : undefined
  });
  return response.data.data;
}

export async function fetchImaKnowledgeBasesPreview(payload: ImaCredentialPreview): Promise<ImaOption[]> {
  const response = await axios.post<ApiResponse<ImaOption[]>>("/api/ima/options/knowledge-bases/preview", payload);
  return response.data.data;
}

export async function fetchImaKnowledgeFolders(
  knowledgeBaseId: string,
  accountId?: number,
  forceRefresh?: boolean
): Promise<ImaOption[]> {
  const response = await axios.get<ApiResponse<ImaOption[]>>("/api/ima/options/knowledge-folders", {
    params: {
      knowledge_base_id: knowledgeBaseId,
      ...(accountId ? { account_id: accountId } : {}),
      ...(forceRefresh ? { force_refresh: true } : {})
    }
  });
  return response.data.data;
}

export async function fetchImaKnowledgeFoldersPreview(
  payload: ImaCredentialPreview & { knowledge_base_id: string }
): Promise<ImaOption[]> {
  const response = await axios.post<ApiResponse<ImaOption[]>>("/api/ima/options/knowledge-folders/preview", payload);
  return response.data.data;
}

export async function runImaManualSync(): Promise<ImaManualSyncResult> {
  const response = await axios.post<ApiResponse<ImaManualSyncResult>>("/api/ima/manual-sync");
  return response.data.data;
}

export async function fetchImaSyncJobs(): Promise<ImaSyncJob[]> {
  const response = await axios.get<ApiResponse<ImaSyncJob[]>>("/api/ima/sync-jobs");
  return response.data.data;
}

export async function createImaSyncJob(payload: ImaSyncJobPayload): Promise<ImaSyncJob> {
  const response = await axios.post<ApiResponse<ImaSyncJob>>("/api/ima/sync-jobs", payload);
  return response.data.data;
}

export async function updateImaSyncJob(syncJobId: number, payload: ImaSyncJobPayload): Promise<ImaSyncJob> {
  const response = await axios.put<ApiResponse<ImaSyncJob>>(`/api/ima/sync-jobs/${syncJobId}`, payload);
  return response.data.data;
}

export async function deleteImaSyncJob(syncJobId: number): Promise<void> {
  await axios.delete<ApiResponse<null>>(`/api/ima/sync-jobs/${syncJobId}`);
}

export async function runImaSyncJob(syncJobId: number): Promise<ImaManualSyncResult> {
  const response = await axios.post<ApiResponse<ImaManualSyncResult>>(`/api/ima/sync-jobs/${syncJobId}/run`);
  return response.data.data;
}

export async function fetchImaSyncRecords(params: ImaSyncRecordQuery): Promise<ImaSyncRecordPage> {
  const response = await axios.get<ApiResponse<ImaSyncRecordPage>>("/api/ima/records", { params });
  return response.data.data;
}

export async function fetchImaSyncBatches(params: ImaSyncBatchQuery): Promise<ImaSyncBatchPage> {
  const response = await axios.get<ApiResponse<ImaSyncBatchPage>>("/api/ima/records/batches", { params });
  return response.data.data;
}

export async function fetchImaBatchItems(batchId: string): Promise<ImaSyncRecord[]> {
  const response = await axios.get<ApiResponse<ImaSyncRecord[]>>(`/api/ima/records/batches/${batchId}/items`);
  return response.data.data;
}
