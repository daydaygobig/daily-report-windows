/**
 * 全站唯一的 API 客户端与响应类型。
 *
 * - `apiClient`：共享 axios 实例，后续如需统一拦截器/超时只改这一处；
 * - `ApiResponse<T>`：后端统一包络 { code, message, data }（此前在 10 个 service 文件里各复制一份）；
 * - `getErrorMessage`：错误信息归一化（此前在 5 个页面各实现一份）。
 */
import axios from "axios";

export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

const apiClient = axios.create();

export default apiClient;

type ErrorDetail = { message?: string };
type ErrorBody = { detail?: string | ErrorDetail; message?: string };

const extractDetailMessage = (detail: string | ErrorDetail | undefined): string | undefined => {
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return detail.message ?? "请求失败";
  }
  return undefined;
};

export function getErrorMessage(error: unknown, fallback = "请求失败"): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ErrorBody | undefined;
    const detailMessage = extractDetailMessage(body?.detail);
    if (detailMessage) {
      return detailMessage;
    }
    if (body?.message) {
      return body.message;
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}
