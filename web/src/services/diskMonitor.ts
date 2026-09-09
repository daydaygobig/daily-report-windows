import apiClient from "./apiClient";
import type { ApiResponse } from "./apiClient";

export type DiskIoRecord = {
  id: number;
  created_at: string;
  updated_at: string;
  execution_id?: number | null;
  task_id?: number | null;
  job_id?: number | null;
  task_name?: string | null;
  job_name?: string | null;
  task_type: string;
  is_manual: boolean;
  provider: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  backend_read_bytes?: number | null;
  backend_write_bytes?: number | null;
  weflow_read_bytes?: number | null;
  weflow_write_bytes?: number | null;
  weflow_captured: boolean;
  weflow_process?: string | null;
  exported_file_bytes: number;
  chatlog_decrypt_write_bytes: number;
  chatlog_decrypt_status?: string | null;
  chatlog_work_dir?: string | null;
  disk_write_bytes: number;
  total_read_bytes: number;
  total_write_bytes: number;
  media_enabled: boolean;
  is_warning: boolean;
  warning_reason?: string | null;
  job_alert_threshold_bytes: number;
  job_alert_triggered: boolean;
  job_alert_sent: boolean;
  job_alert_error?: string | null;
  raw_snapshot?: Record<string, unknown> | null;
};

export type DiskIoSummary = {
  label: string;
  hours?: number | null;
  start_time: string;
  end_time: string;
  total_write_bytes: number;
  total_read_bytes: number;
  max_single_write_bytes: number;
  warning_count: number;
  record_count: number;
  chatlog_decrypt_count: number;
  weflow_media_count: number;
};

export type DiskIoRecordPage = {
  items: DiskIoRecord[];
  total: number;
  page: number;
  page_size: number;
};

export type DiskIoQuery = {
  page: number;
  page_size: number;
  execution_id?: number;
  task_id?: number;
  job_id?: number;
  provider?: string;
  task_type?: string;
  is_warning?: boolean;
  start_time?: string;
  end_time?: string;
  sort_by?: "disk_write_bytes" | "exported_file_bytes";
  sort_order?: "asc" | "desc";
};

export type DiskIoAggregate = {
  summary: {
    disk_write_bytes: number;
    max_single_disk_write_bytes: number;
    record_count: number;
    warning_count: number;
  };
  monthly_trend: Array<{
    month: string;
    disk_write_bytes: number;
    record_count: number;
  }>;
  task_ranking: Array<{
    task_name?: string | null;
    job_name?: string | null;
    record_count: number;
    disk_write_bytes: number;
    avg_disk_write_bytes: number;
  }>;
};

export type DiskInspectionJob = {
  id: number;
  created_at: string;
  updated_at: string;
  name: string;
  is_enabled: boolean;
  schedule_type: string;
  schedule_time: string;
  schedule_weekday?: number | null;
  schedule_month_day?: number | null;
  cron_expression?: string | null;
  interval_enabled: boolean;
  interval_minutes?: number | null;
  window_start: string;
  window_end: string;
  window_hours: number;
  threshold_bytes: number;
  webhook_ids: number[];
  cooldown_hours: number;
  weflow_process_names?: string | null;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_alert_at?: string | null;
};

export type DiskInspectionJobPayload = Omit<DiskInspectionJob, "id" | "created_at" | "updated_at" | "last_run_at" | "next_run_at" | "last_alert_at">;

export type DiskInspectionRun = {
  id: number;
  created_at: string;
  updated_at: string;
  inspection_job_id?: number | null;
  inspection_job_name?: string | null;
  status: string;
  inspected_at: string;
  window_start: string;
  window_end: string;
  window_hours: number;
  threshold_bytes: number;
  total_write_bytes: number;
  total_read_bytes: number;
  max_single_write_bytes: number;
  warning_count: number;
  record_count: number;
  chatlog_decrypt_count: number;
  weflow_media_count: number;
  alert_sent: boolean;
  alert_error?: string | null;
  webhook_ids?: number[] | null;
  summary?: string | null;
};

export type DiskInspectionRunPage = {
  items: DiskInspectionRun[];
  total: number;
  page: number;
  page_size: number;
};

export type DiskInspectionRunQuery = {
  page: number;
  page_size: number;
  inspection_job_id?: number;
  status?: string;
  start_time?: string;
  end_time?: string;
};

export async function fetchDiskIoRecords(params: DiskIoQuery): Promise<DiskIoRecordPage> {
  const response = await apiClient.get<ApiResponse<DiskIoRecordPage>>("/api/disk-monitor/records", { params });
  return response.data.data;
}

export async function fetchDiskIoSummaries(): Promise<DiskIoSummary[]> {
  const response = await apiClient.get<ApiResponse<DiskIoSummary[]>>("/api/disk-monitor/records/summary");
  return response.data.data;
}

export async function fetchDiskIoAggregate(params: { start_time: string; end_time: string }): Promise<DiskIoAggregate> {
  const response = await apiClient.get<ApiResponse<DiskIoAggregate>>("/api/disk-monitor/records/aggregate", { params });
  return response.data.data;
}

export async function fetchDiskIoRecord(recordId: number): Promise<DiskIoRecord> {
  const response = await apiClient.get<ApiResponse<DiskIoRecord>>(`/api/disk-monitor/records/${recordId}`);
  return response.data.data;
}

export async function fetchDiskInspectionJobs(): Promise<DiskInspectionJob[]> {
  const response = await apiClient.get<ApiResponse<DiskInspectionJob[]>>("/api/disk-monitor/inspection-jobs");
  return response.data.data;
}

export async function createDiskInspectionJob(payload: DiskInspectionJobPayload): Promise<DiskInspectionJob> {
  const response = await apiClient.post<ApiResponse<DiskInspectionJob>>("/api/disk-monitor/inspection-jobs", payload);
  return response.data.data;
}

export async function updateDiskInspectionJob(jobId: number, payload: DiskInspectionJobPayload): Promise<DiskInspectionJob> {
  const response = await apiClient.put<ApiResponse<DiskInspectionJob>>(`/api/disk-monitor/inspection-jobs/${jobId}`, payload);
  return response.data.data;
}

export async function deleteDiskInspectionJob(jobId: number): Promise<void> {
  await apiClient.delete<ApiResponse<null>>(`/api/disk-monitor/inspection-jobs/${jobId}`);
}

export async function runDiskInspectionJob(jobId: number): Promise<DiskInspectionRun> {
  const response = await apiClient.post<ApiResponse<DiskInspectionRun>>(`/api/disk-monitor/inspection-jobs/${jobId}/run`);
  return response.data.data;
}

export async function fetchDiskInspectionRuns(params: DiskInspectionRunQuery): Promise<DiskInspectionRunPage> {
  const response = await apiClient.get<ApiResponse<DiskInspectionRunPage>>("/api/disk-monitor/inspection-runs", { params });
  return response.data.data;
}

export async function fetchDiskInspectionRun(runId: number): Promise<DiskInspectionRun> {
  const response = await apiClient.get<ApiResponse<DiskInspectionRun>>(`/api/disk-monitor/inspection-runs/${runId}`);
  return response.data.data;
}
