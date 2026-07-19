import axios from "axios";

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type Webhook = {
  id: number;
  name: string;
  headers?: Record<string, unknown> | null;
  card_mode: "markdown" | "template" | "custom_json";
  card_header_enabled: boolean;
  card_header_title?: string | null;
  card_header_subtitle?: string | null;
  card_header_color?: string | null;
  image_render_engine: "satori" | "svg" | "typst";
  feishu_app_id?: string | null;
  has_feishu_app_secret: boolean;
  created_at: string;
  updated_at: string;
};

export type WebhookCreatePayload = {
  name: string;
  url: string;
  headers?: Record<string, unknown> | null;
  card_mode?: "markdown" | "template" | "custom_json";
  card_header_enabled?: boolean;
  card_header_title?: string | null;
  card_header_subtitle?: string | null;
  card_header_color?: string | null;
  image_render_engine?: "satori" | "svg" | "typst";
  feishu_app_id?: string | null;
  feishu_app_secret?: string | null;
};

export type WebhookUpdatePayload = Partial<WebhookCreatePayload>;

export async function fetchWebhooks(): Promise<Webhook[]> {
  const response = await axios.get<ApiResponse<Webhook[]>>("/api/webhooks/");
  return response.data.data;
}

export async function createWebhook(payload: WebhookCreatePayload): Promise<Webhook> {
  const response = await axios.post<ApiResponse<Webhook>>("/api/webhooks/", payload);
  return response.data.data;
}

export async function updateWebhook(webhookId: number, payload: WebhookUpdatePayload): Promise<Webhook> {
  const response = await axios.put<ApiResponse<Webhook>>(`/api/webhooks/${webhookId}`, payload);
  return response.data.data;
}

export async function deleteWebhook(webhookId: number): Promise<void> {
  await axios.delete<ApiResponse<null>>(`/api/webhooks/${webhookId}`);
}

export async function testWebhookImage(
  webhookId: number,
  payload: { app_id?: string | null; app_secret?: string | null; send_image?: boolean }
): Promise<{ ok: boolean; message: string; image_key?: string | null }> {
  const response = await axios.post<ApiResponse<{ ok: boolean; message: string; image_key?: string | null }>>(
    `/api/webhooks/${webhookId}/test-image`,
    payload
  );
  return response.data.data;
}
