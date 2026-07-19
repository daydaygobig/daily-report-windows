"""IMA OpenAPI client helpers."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import quote

import httpx


class ImaApiError(RuntimeError):
    """Raised when IMA API returns an error."""

    def __init__(
        self,
        message: str,
        *,
        code: Optional[int] = None,
        explanation: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.explanation = explanation
        self.raw = raw or {}

    def __str__(self) -> str:
        if self.code is None:
            return self.message
        if self.explanation and self.explanation != self.message:
            return f"[{self.code}] {self.message}（{self.explanation}）"
        return f"[{self.code}] {self.message}"


@dataclass
class ImaCredentials:
    client_id: str
    api_key: str


@dataclass
class ImaTarget:
    target_type: str
    note_folder_id: Optional[str] = None
    note_folder_name: Optional[str] = None
    knowledge_base_id: Optional[str] = None
    knowledge_base_name: Optional[str] = None
    knowledge_folder_id: Optional[str] = None
    knowledge_folder_name: Optional[str] = None


NOTE_ERROR_EXPLANATIONS: Dict[int, str] = {
    0: "成功",
    100001: "参数错误",
    100002: "携带无效的 ID",
    100003: "服务器内部错误",
    100004: "拉取的 size 不合法（超出范围）或用户空间不够",
    100005: "不能获取私有笔记的访客信息或不是笔记的作者",
    100006: "笔记已被删除",
    100008: "版本冲突",
    100009: "单篇笔记超过最大限制",
    310001: "笔记本不存在",
    20002: "apiKey 超过最大限频",
    20004: "apikey 鉴权失败",
}

WIKI_ERROR_EXPLANATIONS: Dict[int, str] = {
    0: "成功",
    110001: "参数非法",
    110002: "配置非法",
    110010: "下游网络错误",
    110011: "下游逻辑错误",
    110012: "接口无效",
    110013: "客户端取消",
    110020: "安全打击",
    110021: "请求频控",
    110030: "无权限",
    20004: "apikey 鉴权失败",
}


class ImaClient:
    def __init__(self, credentials: ImaCredentials, *, timeout: float = 30.0) -> None:
        self._credentials = credentials
        self._timeout = timeout

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "ima-openapi-clientid": self._credentials.client_id,
            "ima-openapi-apikey": self._credentials.api_key,
        }

    async def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"https://ima.qq.com/{path.lstrip('/')}"
        namespace = _resolve_namespace(path)
        try:
            status_code, text = await asyncio.to_thread(self._post_sync, url, payload)
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {}
            code = _extract_error_code(data)
            message = (
                data.get("errmsg")
                or data.get("errMsg")
                or data.get("message")
                or data.get("msg")
                or body
                or f"HTTP {exc.code}"
            )
            raise ImaApiError(
                str(message),
                code=code,
                explanation=_resolve_error_explanation(namespace, code),
                raw=data,
            ) from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}
        if status_code >= 400:
            code = _extract_error_code(data)
            message = (
                data.get("errmsg")
                or data.get("errMsg")
                or data.get("message")
                or data.get("msg")
                or text
                or f"HTTP {status_code}"
            )
            raise ImaApiError(
                str(message),
                code=code,
                explanation=_resolve_error_explanation(namespace, code),
                raw=data,
            )
        code = data.get("retcode", data.get("errCode", data.get("code", -1)))
        message = data.get("errmsg", data.get("errMsg", data.get("message", data.get("msg", "请求失败"))))
        if code != 0:
            raise ImaApiError(
                str(message),
                code=code,
                explanation=_resolve_error_explanation(namespace, code),
                raw=data,
            )
        if "data" in data and isinstance(data["data"], dict):
            return data["data"]
        return data

    def _post_sync(self, url: str, payload: Dict[str, Any]) -> tuple[int, str]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib_request.Request(
            url,
            data=body,
            headers=self._headers,
            method="POST",
        )
        with urllib_request.urlopen(request, timeout=self._timeout) as response:
            text = response.read().decode("utf-8", errors="ignore")
            return response.status, text

    async def list_note_folders(self) -> List[Dict[str, Any]]:
        cursor = "0"
        results: List[Dict[str, Any]] = []
        while True:
            payload = {"cursor": cursor, "limit": 20}
            data = await self.post("openapi/note/v1/list_notebook", payload)
            items = data.get("note_folder_infos") or []
            for item in items:
                if isinstance(item, dict):
                    results.append(item)
            if data.get("is_end"):
                break
            cursor = data.get("next_cursor") or ""
            if not cursor:
                break
        return results

    async def list_knowledge_bases(self) -> List[Dict[str, Any]]:
        cursor = ""
        results: List[Dict[str, Any]] = []
        while True:
            payload = {"query": "", "cursor": cursor, "limit": 20}
            data = await self.post("openapi/wiki/v1/search_knowledge_base", payload)
            items = data.get("info_list") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                knowledge_base_id = item.get("kb_id")
                knowledge_base_name = item.get("kb_name")
                if knowledge_base_id and knowledge_base_name:
                    normalized = dict(item)
                    normalized["id"] = knowledge_base_id
                    normalized["name"] = knowledge_base_name
                    results.append(normalized)
            if data.get("is_end"):
                break
            cursor = data.get("next_cursor") or ""
            if not cursor:
                break
        return results

    async def list_knowledge_folders(self, knowledge_base_id: str) -> List[Dict[str, Any]]:
        root = {
            "label": "根目录",
            "value": "",
            "folder_id": "",
            "path": "根目录",
        }
        folders: List[Dict[str, Any]] = [root]
        await self._collect_folders(knowledge_base_id, None, "根目录", folders)
        return folders

    async def _collect_folders(
        self,
        knowledge_base_id: str,
        folder_id: Optional[str],
        current_path: str,
        collector: List[Dict[str, Any]],
    ) -> None:
        cursor = ""
        while True:
            payload: Dict[str, Any] = {
                "knowledge_base_id": knowledge_base_id,
                "cursor": cursor,
                "limit": 50,
            }
            if folder_id:
                payload["folder_id"] = folder_id
            data = await self.post("openapi/wiki/v1/get_knowledge_list", payload)
            items = data.get("knowledge_list") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_folder_id = item.get("folder_id") or item.get("media_id")
                title = item.get("name") or item.get("title")
                if not item_folder_id or not isinstance(item_folder_id, str):
                    continue
                if not item_folder_id.startswith("folder_"):
                    continue
                label = f"{current_path} / {title}" if current_path else title
                collector.append(
                    {
                        "label": label,
                        "value": item_folder_id,
                        "folder_id": item_folder_id,
                        "path": label,
                    }
                )
                await self._collect_folders(knowledge_base_id, item_folder_id, label, collector)
            if data.get("is_end"):
                break
            cursor = data.get("next_cursor") or ""
            if not cursor:
                break

    async def check_kb_duplicate(
        self,
        *,
        knowledge_base_id: str,
        file_name: str,
        media_type: int,
        folder_id: Optional[str],
    ) -> bool:
        payload: Dict[str, Any] = {
            "params": [{"name": file_name, "media_type": media_type}],
            "knowledge_base_id": knowledge_base_id,
        }
        if folder_id:
            payload["folder_id"] = folder_id
        data = await self.post("openapi/wiki/v1/check_repeated_names", payload)
        results = data.get("results") or []
        if not results:
            return False
        first = results[0]
        return bool(first.get("is_repeated"))

    async def search_note_by_title(self, title: str, folder_id: Optional[str]) -> bool:
        data = await self.post(
            "openapi/note/v1/search_note",
            {"search_type": 0, "query_info": {"title": title}, "start": 0, "end": 20},
        )
        search_note_infos = data.get("search_note_infos") or []
        for item in search_note_infos:
            note_info = ((item or {}).get("note_book_info") or {})
            note_ext_info = note_info.get("note_ext_info") or {}
            doc_title = note_info.get("title")
            doc_folder_id = note_ext_info.get("folder_id")
            if doc_title == title and (folder_id is None or folder_id == doc_folder_id):
                return True
        return False

    async def import_note(self, *, title: str, content: str, folder_id: Optional[str]) -> str:
        note_content = f"# {title}\n\n{content}".strip()
        payload: Dict[str, Any] = {"content_format": 1, "content": note_content}
        if folder_id:
            payload["folder_id"] = folder_id
        data = await self.post("openapi/note/v1/import_doc", payload)
        note_id = _extract_first(data, [["note_id"]])
        if not note_id:
            raise ImaApiError("写入 ima 笔记成功但未返回 note_id")
        return note_id

    async def upload_file_to_kb(
        self,
        *,
        file_path: Path,
        target: ImaTarget,
        media_type: int,
        content_type: str,
        file_ext: str,
    ) -> str:
        if not target.knowledge_base_id:
            raise ImaApiError("缺少知识库 ID")
        file_name = file_path.name
        file_size = file_path.stat().st_size
        create_payload = {
            "file_name": file_name,
            "file_size": file_size,
            "content_type": content_type,
            "knowledge_base_id": target.knowledge_base_id,
            "file_ext": file_ext,
        }
        media_data = await self.post("openapi/wiki/v1/create_media", create_payload)
        media_id = _extract_first(media_data, [["media_id"], ["data", "media_id"]])
        credential = media_data.get("cos_credential") or {}
        if not media_id or not credential:
            raise ImaApiError("创建媒体成功但返回数据不完整")
        await self._upload_to_cos(file_path, credential, content_type)
        add_payload: Dict[str, Any] = {
            "media_type": media_type,
            "media_id": media_id,
            "title": file_name,
            "knowledge_base_id": target.knowledge_base_id,
            "file_info": {
                "cos_key": credential.get("cos_key"),
                "file_size": file_size,
                "file_name": file_name,
            },
        }
        if target.knowledge_folder_id:
            add_payload["folder_id"] = target.knowledge_folder_id
        add_data = await self.post("openapi/wiki/v1/add_knowledge", add_payload)
        final_media_id = _extract_first(
            add_data,
            [
                ["media_id"],
                ["data", "media_id"],
                ["media_info", "media_id"],
                ["knowledge_info", "media_id"],
            ],
        )
        if not final_media_id:
            raise ImaApiError("同步到 ima 知识库成功但未返回 media_id")
        return final_media_id

    async def _upload_to_cos(self, file_path: Path, credential: Dict[str, Any], content_type: str) -> None:
        file_bytes = file_path.read_bytes()
        bucket = credential["bucket_name"]
        region = credential["region"]
        hostname = f"{bucket}.cos.{region}.myqcloud.com"
        cos_key = credential["cos_key"]
        pathname = f"/{cos_key}"
        start_time = str(credential.get("start_time"))
        expired_time = str(credential.get("expired_time"))
        headers_to_sign = {
            "content-length": str(len(file_bytes)),
            "host": hostname,
        }
        authorization = _build_cos_authorization(
            secret_id=credential["secret_id"],
            secret_key=credential["secret_key"],
            method="PUT",
            pathname=pathname,
            headers=headers_to_sign,
            start_time=start_time,
            expired_time=expired_time,
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.put(
                f"https://{hostname}{pathname}",
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(file_bytes)),
                    "Authorization": authorization,
                    "x-cos-security-token": credential["token"],
                },
                content=file_bytes,
            )
        response.raise_for_status()


def _extract_first(data: Dict[str, Any], paths: List[List[str]]) -> Optional[str]:
    for path in paths:
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if isinstance(current, str) and current:
            return current
    return None


def _extract_error_code(data: Dict[str, Any]) -> Optional[int]:
    for key in ("retcode", "errCode", "code"):
        value = data.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _resolve_namespace(path: str) -> str:
    normalized = path.lstrip("/")
    if normalized.startswith("openapi/note/"):
        return "note"
    if normalized.startswith("openapi/wiki/"):
        return "wiki"
    return "generic"


def _resolve_error_explanation(namespace: str, code: Optional[int]) -> Optional[str]:
    if code is None:
        return None
    if namespace == "note":
        return NOTE_ERROR_EXPLANATIONS.get(code)
    if namespace == "wiki":
        return WIKI_ERROR_EXPLANATIONS.get(code)
    return NOTE_ERROR_EXPLANATIONS.get(code) or WIKI_ERROR_EXPLANATIONS.get(code)


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _hmac_sha1(key: str, data: str) -> str:
    return hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).hexdigest()


def _build_cos_authorization(
    *,
    secret_id: str,
    secret_key: str,
    method: str,
    pathname: str,
    headers: Dict[str, str],
    start_time: str,
    expired_time: str,
) -> str:
    key_time = f"{start_time};{expired_time}"
    sign_key = _hmac_sha1(secret_key, key_time)
    header_keys = sorted(headers.keys())
    http_headers = "&".join(f"{key.lower()}={quote(headers[key], safe='')}" for key in header_keys)
    http_string = f"{method.lower()}\n{pathname}\n\n{http_headers}\n"
    string_to_sign = f"sha1\n{key_time}\n{_sha1(http_string)}\n"
    signature = _hmac_sha1(sign_key, string_to_sign)
    header_list = ";".join(key.lower() for key in header_keys)
    return "&".join(
        [
            "q-sign-algorithm=sha1",
            f"q-ak={secret_id}",
            f"q-sign-time={key_time}",
            f"q-key-time={key_time}",
            f"q-header-list={header_list}",
            "q-url-param-list=",
            f"q-signature={signature}",
        ]
    )
