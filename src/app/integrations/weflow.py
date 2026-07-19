"""Client for WeFlow HTTP API."""

from __future__ import annotations

import html
import asyncio
import re
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


class WeFlowError(RuntimeError):
    """Raised when WeFlow API interaction fails."""


SYSTEM_MESSAGE_LABEL = "\u7cfb\u7edf\u6d88\u606f"
PLACEHOLDERS = {
    "image": "\u56fe\u7247",
    "voice": "\u8bed\u97f3",
    "video": "\u89c6\u9891",
    "emoji": "\u8868\u60c5",
    "file": "\u6587\u4ef6",
    "link_file": "\u94fe\u63a5/\u6587\u4ef6",
    "non_text": "\u975e\u6587\u672c\u6d88\u606f",
    "system": "\u7cfb\u7edf\u6d88\u606f",
    "quote": "\u5f15\u7528",
    "app": "App\u6d88\u606f",
    "money": "\u7ea2\u5305/\u8f6c\u8d26",
    "link": "\u94fe\u63a5",
    "finder": "\u89c6\u9891\u53f7",
    "forward_chat": "\u8f6c\u53d1\u804a\u5929\u8bb0\u5f55",
}


@dataclass
class WeFlowConfig:
    base_url: str
    token: str
    page_limit: int = 1000
    page_timeout_sec: int = 180
    empty_page_retry: int = 2


def _headers(config: WeFlowConfig) -> Dict[str, str]:
    return {"Authorization": f"Bearer {config.token}"}


def _timestamp(value: datetime) -> int:
    return int(value.timestamp())


async def probe_health(config: WeFlowConfig) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{config.base_url}/health")
        response.raise_for_status()
        token_response = await client.get(
            f"{config.base_url}/api/v1/sessions",
            params={"limit": 1},
            headers=_headers(config),
        )
        if token_response.status_code in (401, 403):
            raise WeFlowError("WeFlow Token 鏍￠獙澶辫触")
        token_response.raise_for_status()


async def list_sessions(config: WeFlowConfig, *, keyword: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": limit}
    if keyword:
        params["keyword"] = keyword
    async with httpx.AsyncClient(timeout=config.page_timeout_sec) as client:
        response = await client.get(f"{config.base_url}/api/v1/sessions", params=params, headers=_headers(config))
        response.raise_for_status()
        payload = response.json()
    return payload.get("sessions") or []


async def list_group_members(config: WeFlowConfig, talker: str) -> Dict[str, str]:
    async with httpx.AsyncClient(timeout=config.page_timeout_sec) as client:
        response = await client.get(
            f"{config.base_url}/api/v1/group-members",
            params={"chatroomId": talker},
            headers=_headers(config),
        )
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        payload = response.json()
    mapping: Dict[str, str] = {}
    for member in payload.get("members") or []:
        wxid = member.get("wxid")
        if not wxid:
            continue
        display = (
            member.get("groupNickname")
            or member.get("displayName")
            or member.get("remark")
            or member.get("nickname")
            or wxid
        )
        mapping[wxid] = display
    return mapping


async def fetch_messages(
    config: WeFlowConfig,
    *,
    talker: str,
    start: Optional[datetime],
    end: Optional[datetime],
) -> List[Dict[str, Any]]:
    offset = 0
    empty_retries = 0
    messages: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    params_base: Dict[str, Any] = {
        "talker": talker,
        "limit": config.page_limit,
        "media": 0,
    }
    if start:
        params_base["start"] = _timestamp(start)
    if end:
        params_base["end"] = _timestamp(end)

    async with httpx.AsyncClient(timeout=config.page_timeout_sec) as client:
        while True:
            params = {**params_base, "offset": offset}
            response = await client.get(f"{config.base_url}/api/v1/messages", params=params, headers=_headers(config))
            response.raise_for_status()
            payload = response.json()
            page = payload.get("messages") or []
            if page:
                for item in page:
                    key = _message_key(item)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    messages.append(item)
                empty_retries = 0
            else:
                empty_retries += 1
                if empty_retries <= config.empty_page_retry:
                    await asyncio.sleep(1)
                    continue
                break
            has_more = bool(payload.get("hasMore"))
            if not has_more or len(page) < config.page_limit:
                break
            offset += config.page_limit
    return messages


def _message_key(message: Dict[str, Any]) -> str:
    local_id = message.get("localId")
    if local_id not in (None, ""):
        return f"local:{local_id}"
    return "fallback:{server}:{time}:{sender}".format(
        server=message.get("serverId") or "",
        time=message.get("createTime") or "",
        sender=message.get("senderUsername") or "",
    )


def _forward_message_lookup(messages: List[Dict[str, Any]]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for message in messages:
        server_id = str(message.get("serverId") or "").strip()
        if not server_id:
            continue
        raw = _raw_message_value(message)
        if _is_forward_chat_record(raw):
            lookup[server_id] = raw
    return lookup


def messages_to_chatlog_text(
    messages: List[Dict[str, Any]],
    *,
    member_names: Dict[str, str],
) -> str:
    lines: List[str] = []
    sorted_messages = sorted(messages, key=lambda item: int(item.get("createTime") or 0))
    forward_lookup = _forward_message_lookup(sorted_messages)
    for message in sorted_messages:
        created = datetime.fromtimestamp(int(message.get("createTime") or 0))
        if _is_system_message(message):
            lines.append(f"{SYSTEM_MESSAGE_LABEL} {created.strftime('%m-%d %H:%M:%S')}")
            lines.append(_system_message_content(message))
            lines.append("")
            continue

        sender = message.get("senderUsername") or ("me" if message.get("isSend") else "unknown")
        nickname = member_names.get(sender) or sender
        content = _message_content(message, member_names=member_names, forward_lookup=forward_lookup)
        lines.append(f"{nickname}({sender}) {created.strftime('%m-%d %H:%M:%S')}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines).strip()


def _is_system_message(message: Dict[str, Any]) -> bool:
    if str(message.get("localType") or "") == "10000":
        return True
    if not message.get("senderUsername") and not message.get("isSend"):
        return True
    raw = _raw_message_value(message)
    return "<sysmsg" in raw


def _system_message_content(message: Dict[str, Any]) -> str:
    raw = _raw_message_value(message)
    root = _parse_xml_fragment(raw)
    if root is not None:
        for path in ("./revokemsg/content", ".//content"):
            text = _find_text(root, path)
            if text:
                return text
    text = _strip_xml(raw).strip()
    return _placeholder("system") if not text else text


def _message_content(
    message: Dict[str, Any],
    *,
    member_names: Dict[str, str],
    forward_lookup: Optional[Dict[str, str]] = None,
) -> str:
    media_type = (message.get("mediaType") or "").strip().lower()
    if media_type:
        return _media_placeholder(media_type)
    raw = _raw_message_value(message)
    app_content = _app_message_content(raw, member_names=member_names, forward_lookup=forward_lookup)
    if app_content:
        return app_content
    local_type = str(message.get("localType") or "")
    if local_type in {"3", "34", "43", "47"}:
        return _media_placeholder(local_type)
    text = _strip_xml(str(raw)).strip()
    if text:
        return text
    return _placeholder("non_text")


def _raw_message_value(message: Dict[str, Any]) -> str:
    for key in ("rawContent", "content", "parsedContent"):
        value = message.get(key)
        if value and _has_xml(value):
            return str(value)
    return str(message.get("parsedContent") or message.get("content") or message.get("rawContent") or "")


def _app_message_content(
    raw: str,
    *,
    member_names: Dict[str, str],
    forward_lookup: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    root = _parse_xml_fragment(raw)
    if root is None:
        return _app_message_content_soup(raw, member_names=member_names)
    appmsg = root.find(".//appmsg")
    if appmsg is None:
        return None

    app_type = _find_text(appmsg, "./type")
    if app_type == "57":
        return _refer_message_content(appmsg, member_names=member_names, forward_lookup=forward_lookup)
    return _share_message_content(appmsg)


def _app_message_content_soup(
    raw: str,
    *,
    member_names: Dict[str, str],
    forward_lookup: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    soup = _parse_html_fragment(raw)
    if soup is None:
        return None
    appmsg = soup.find("appmsg")
    if appmsg is None:
        return None
    app_type = _soup_text(appmsg, "type")
    if app_type == "57":
        return _refer_message_content_soup(appmsg, member_names=member_names, forward_lookup=forward_lookup)
    return _share_message_content_soup(appmsg)


def _refer_message_content_soup(
    appmsg: Any,
    *,
    member_names: Dict[str, str],
    forward_lookup: Optional[Dict[str, str]] = None,
) -> str:
    reply = _soup_text(appmsg, "title")
    refer = appmsg.find("refermsg", recursive=False)
    lines: List[str] = []
    if refer is not None:
        chatusr = _soup_text(refer, "chatusr")
        display = _soup_text(refer, "displayname")
        nickname = member_names.get(chatusr) if chatusr else None
        nickname = nickname or display or chatusr or "unknown"
        created = _format_refer_time(_soup_text(refer, "createtime"))
        header = f"> {nickname}({chatusr or 'unknown'})"
        if created:
            header = f"{header} {created}"
        lines.append(header)
        quote = _summarize_refer_content_soup(refer, forward_lookup=forward_lookup)
        for quote_line in quote.splitlines() or [_placeholder("quote")]:
            lines.append(f"> {quote_line}")
    if reply:
        lines.append(reply)
    return "\n".join(lines).strip() or _placeholder("quote")


def _summarize_refer_content_soup(refer: Any, *, forward_lookup: Optional[Dict[str, str]] = None) -> str:
    refer_type = _soup_text(refer, "type")
    content = _soup_markup(refer, "content") or _soup_text(refer, "content")
    if refer_type in {"3", "34", "43", "47"}:
        return _media_placeholder(refer_type)
    if refer_type == "49":
        full_forward = _forward_content_from_lookup(_soup_text(refer, "svrid"), forward_lookup)
        if full_forward:
            return full_forward
        shared = _embedded_app_summary(content) if content else None
        if shared:
            return shared
        text = _strip_xml(content).strip() if content else ""
        return text or _placeholder("link_file")
    if content:
        shared = _app_message_content(content, member_names={}, forward_lookup=forward_lookup)
        if shared:
            return shared
        text = _strip_xml(content).strip()
        if text:
            return text
    return _placeholder("quote")


def _share_message_content_soup(appmsg: Any) -> str:
    app_type = _soup_text(appmsg, "type")
    title = _soup_text(appmsg, "title")
    desc = _soup_text(appmsg, "des")
    url = _soup_text(appmsg, "url") or _soup_text(appmsg, "lowurl")
    filename = _soup_text(appmsg, "appattach/filename")

    forward = _forward_chat_record_content(str(appmsg), title=title, quoted=False, app_type=app_type)
    if forward:
        return forward
    if _is_finder_app_soup(appmsg, app_type=app_type):
        return _placeholder("finder")
    if url and _is_money_url(url):
        return _placeholder("money")
    if app_type in {"2000", "2001"}:
        return _placeholder("money")
    if app_type == "6":
        return _bracket_value("file", filename or title or PLACEHOLDERS["file"])
    if url:
        label = title or desc or PLACEHOLDERS["link"]
        return f"{_bracket_value('link', label)}({url})"
    if title:
        return _bracket_value("app", title)
    return _placeholder("non_text")


def _refer_message_content(
    appmsg: ET.Element,
    *,
    member_names: Dict[str, str],
    forward_lookup: Optional[Dict[str, str]] = None,
) -> str:
    reply = _find_text(appmsg, "./title")
    refer = appmsg.find("./refermsg")
    lines: List[str] = []
    if refer is not None:
        chatusr = _find_text(refer, "./chatusr")
        display = _find_text(refer, "./displayname")
        nickname = member_names.get(chatusr) if chatusr else None
        nickname = nickname or display or chatusr or "unknown"
        created = _format_refer_time(_find_text(refer, "./createtime"))
        header = f"> {nickname}({chatusr or 'unknown'})"
        if created:
            header = f"{header} {created}"
        lines.append(header)
        quote = _summarize_refer_content(refer, forward_lookup=forward_lookup)
        for quote_line in quote.splitlines() or [_placeholder("quote")]:
            lines.append(f"> {quote_line}")
    if reply:
        lines.append(reply)
    return "\n".join(lines).strip() or _placeholder("quote")


def _summarize_refer_content(refer: ET.Element, *, forward_lookup: Optional[Dict[str, str]] = None) -> str:
    refer_type = _find_text(refer, "./type")
    content = _find_text(refer, "./content")
    if refer_type in {"3", "34", "43", "47"}:
        return _media_placeholder(refer_type)
    if refer_type == "49":
        full_forward = _forward_content_from_lookup(_find_text(refer, "./svrid"), forward_lookup)
        if full_forward:
            return full_forward
        shared = _embedded_app_summary(content) if content else None
        if shared:
            return shared
        text = _strip_xml(content).strip() if content else ""
        return text or _placeholder("link_file")
    if content:
        shared = _app_message_content(content, member_names={}, forward_lookup=forward_lookup)
        if shared:
            return shared
        text = _strip_xml(content).strip()
        if text:
            return text
    return _placeholder("quote")


def _share_message_content(appmsg: ET.Element) -> str:
    app_type = _find_text(appmsg, "./type")
    title = _find_text(appmsg, "./title")
    desc = _find_text(appmsg, "./des")
    url = _find_text(appmsg, "./url") or _find_text(appmsg, "./lowurl")
    filename = _find_text(appmsg, "./appattach/filename")

    forward = _forward_chat_record_content(
        ET.tostring(appmsg, encoding="unicode", method="xml"),
        title=title,
        quoted=False,
        app_type=app_type,
    )
    if forward:
        return forward
    if _is_finder_app(appmsg, app_type=app_type):
        return _placeholder("finder")
    if url and _is_money_url(url):
        return _placeholder("money")
    if app_type in {"2000", "2001"}:
        return _placeholder("money")
    if app_type == "6":
        return _bracket_value("file", filename or title or PLACEHOLDERS["file"])
    if url:
        label = title or desc or PLACEHOLDERS["link"]
        return f"{_bracket_value('link', label)}({url})"
    if title:
        return _bracket_value("app", title)
    return _placeholder("non_text")


def _embedded_app_summary(raw: str) -> Optional[str]:
    root = _parse_xml_fragment(raw)
    if root is not None:
        appmsg = root.find(".//appmsg")
        if appmsg is not None:
            return _embedded_app_summary_element(appmsg)

    soup = _parse_html_fragment(raw)
    if soup is not None:
        appmsg_soup = soup.find("appmsg")
        if appmsg_soup is not None:
            return _embedded_app_summary_soup(appmsg_soup)
    return None


def _embedded_app_summary_element(appmsg: ET.Element) -> str:
    app_type = _find_text(appmsg, "./type")
    title = _clean_plain_text(_find_text(appmsg, "./title"))
    forward = _forward_chat_record_content(
        ET.tostring(appmsg, encoding="unicode", method="xml"),
        title=title,
        quoted=True,
        app_type=app_type,
    )
    if forward:
        return forward
    if _is_finder_app(appmsg, app_type=app_type):
        return _placeholder("finder")
    if app_type == "57":
        return title or _placeholder("quote")
    if app_type in {"3", "34", "43", "47"}:
        return _media_placeholder(app_type)
    return _share_message_content(appmsg)


def _embedded_app_summary_soup(appmsg: Any) -> str:
    app_type = _soup_text(appmsg, "type")
    title = _clean_plain_text(_soup_text(appmsg, "title"))
    forward = _forward_chat_record_content(str(appmsg), title=title, quoted=True, app_type=app_type)
    if forward:
        return forward
    if _is_finder_app_soup(appmsg, app_type=app_type):
        return _placeholder("finder")
    if app_type == "57":
        return title or _placeholder("quote")
    if app_type in {"3", "34", "43", "47"}:
        return _media_placeholder(app_type)
    return _share_message_content_soup(appmsg)


def _is_finder_app(appmsg: ET.Element, *, app_type: str) -> bool:
    if app_type == "51":
        return True
    xml_text = ET.tostring(appmsg, encoding="unicode", method="xml").lower()
    return "finder" in xml_text or "视频号" in xml_text


def _is_finder_app_soup(appmsg: Any, *, app_type: str) -> bool:
    if app_type == "51":
        return True
    text = str(appmsg).lower()
    return "finder" in text or "视频号" in text


def _is_money_url(url: str) -> bool:
    lowered = url.lower()
    money_markers = (
        "tenpay.com",
        "mmpay",
        "mmpayhb",
        "wcpay",
        "wxpay",
        "wxhb_",
        "hongbao",
        "payapp",
    )
    return any(marker in lowered for marker in money_markers)


def _is_forward_chat_record(raw: str) -> bool:
    normalized = _normalize_forward_source(raw)
    if not normalized:
        return False
    lowered = normalized.lower()
    if "<recorditem" in lowered or "<dataitem" in lowered:
        return True
    app_type = _extract_xml_text(normalized, "type")
    return app_type == "19"


def _forward_content_from_lookup(svrid: str, forward_lookup: Optional[Dict[str, str]]) -> Optional[str]:
    if not svrid or not forward_lookup:
        return None
    raw = forward_lookup.get(str(svrid).strip())
    if not raw:
        return None
    return _forward_chat_record_content(raw, quoted=True)


def _forward_chat_record_content(raw: str, *, title: str = "", quoted: bool, app_type: str = "") -> Optional[str]:
    normalized = _normalize_forward_source(raw)
    if not normalized:
        return None
    if app_type != "19" and "<recorditem" not in normalized.lower() and "<dataitem" not in normalized.lower():
        return None

    forward_title = (
        _clean_plain_text(title)
        or _extract_xml_text(normalized, "nickname")
        or _extract_xml_text(normalized, "title")
        or _extract_xml_text(normalized, "des")
        or PLACEHOLDERS["forward_chat"]
    )
    records = _parse_forward_chat_records(normalized)
    header = _bracket_value("forward_chat", forward_title)
    fallback_desc = _extract_xml_text(normalized, "des") or _extract_xml_text(normalized, "desc")
    if not records:
        fallback_lines = _clean_plain_text(fallback_desc).splitlines()
        if fallback_lines:
            item_prefix = "" if quoted else "> "
            return "\n".join([header, *(f"{item_prefix}{line}" for line in fallback_lines if line.strip())])
        return header

    lines = [header]
    item_prefix = "" if quoted else "> "
    for record in records:
        lines.extend(_format_forward_record_lines(record, prefix=item_prefix))
    return "\n".join(line for line in lines if line).strip()


def _normalize_forward_source(raw: str) -> str:
    value = _remove_sender_prefix(str(raw or "")).strip()
    for _ in range(3):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    return value


def _parse_forward_chat_records(raw: str) -> List[Dict[str, Any]]:
    segments = _forward_segments(raw)
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for segment in segments:
        for attrs, body in _iter_xml_elements(segment, "dataitem"):
            item = _parse_forward_dataitem(attrs, body)
            if not item:
                continue
            key = "|".join(
                [
                    str(item.get("datatype") or ""),
                    item.get("sourcename") or "",
                    item.get("sourcetime") or "",
                    item.get("datadesc") or "",
                    item.get("datatitle") or "",
                    item.get("url") or "",
                ]
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
    return items


def _forward_segments(raw: str) -> List[str]:
    segments: List[str] = []
    candidates = [raw]
    candidates.extend(match.group(1) for match in re.finditer(r"<!\[CDATA\[([\s\S]*?)\]\]>", raw, re.IGNORECASE))
    for _, body in _iter_xml_elements(raw, "recorditem"):
        candidates.append(body)
    for candidate in candidates:
        if not candidate:
            continue
        value = _normalize_forward_source(candidate)
        if value and value not in segments:
            segments.append(value)
    return segments


def _parse_forward_dataitem(attrs: str, body: str) -> Optional[Dict[str, Any]]:
    datatype = _extract_attr(attrs, "datatype") or _extract_xml_text(body, "datatype") or "0"
    sourcename = _extract_xml_text(body, "sourcename")
    sourcetime = _extract_xml_text(body, "sourcetime")
    datadesc = _extract_xml_text(body, "datadesc") or _extract_xml_text(body, "content")
    datatitle = _extract_xml_text(body, "datatitle")
    url = (
        _extract_xml_text(body, "dataurl")
        or _extract_xml_text(body, "url")
        or _extract_xml_text(body, "cdnurl")
    )
    if not any((sourcename, datadesc, datatitle, url)) and datatype in {"", "0"}:
        return None
    return {
        "datatype": datatype,
        "sourcename": sourcename,
        "sourcetime": sourcetime,
        "datadesc": datadesc,
        "datatitle": datatitle,
        "url": url,
    }


def _format_forward_record_lines(record: Dict[str, Any], *, prefix: str) -> List[str]:
    header_parts = []
    if record.get("sourcename"):
        header_parts.append(record["sourcename"])
    created = _format_refer_time(record.get("sourcetime") or "")
    if created:
        header_parts.append(created)

    lines: List[str] = []
    if header_parts:
        lines.append(f"{prefix}{' '.join(header_parts)}")

    content = _forward_record_text(record)
    for line in content.splitlines() or [_placeholder("non_text")]:
        lines.append(f"{prefix}{line}")
    return lines


def _forward_record_text(record: Dict[str, Any]) -> str:
    datatype = str(record.get("datatype") or "")
    desc = _clean_plain_text(record.get("datadesc") or "")
    title = _clean_plain_text(record.get("datatitle") or "")
    url = record.get("url") or ""
    if url and (title or desc):
        return f"{_bracket_value('link', title or desc)}({url})"
    if desc:
        return desc
    if title:
        return title
    if datatype in {"2", "3"}:
        return _media_placeholder("3")
    if datatype == "34":
        return _media_placeholder("34")
    if datatype == "43":
        return _media_placeholder("43")
    if datatype == "47":
        return _media_placeholder("47")
    if datatype in {"8", "49"}:
        return _bracket_value("file", PLACEHOLDERS["file"])
    if datatype == "17":
        return _placeholder("forward_chat")
    return _placeholder("non_text")


def _iter_xml_elements(raw: str, tag: str) -> List[tuple[str, str]]:
    pattern = re.compile(rf"<{tag}\b([^>]*)>([\s\S]*?)</{tag}>", re.IGNORECASE)
    return [(match.group(1) or "", match.group(2) or "") for match in pattern.finditer(raw or "")]


def _extract_xml_text(raw: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}>", raw or "", re.IGNORECASE)
    if not match:
        return ""
    return _clean_plain_text(match.group(1) or "")


def _extract_attr(raw: str, name: str) -> str:
    match = re.search(rf"{name}\s*=\s*['\"]?([^'\"\s>]+)", raw or "", re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else ""


def _format_refer_time(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(int(value)).strftime("%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return ""


def _has_xml(value: Any) -> bool:
    text = html.unescape(str(value))
    return "<" in text and ">" in text


def _parse_xml_fragment(value: str) -> Optional[ET.Element]:
    if not value:
        return None
    unescaped = html.unescape(_remove_sender_prefix(str(value))).strip()
    if "<" not in unescaped or ">" not in unescaped:
        return None
    xml_text = unescaped[unescaped.find("<") :]
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        return None


def _parse_html_fragment(value: str) -> Optional[BeautifulSoup]:
    if not value:
        return None
    unescaped = html.unescape(_remove_sender_prefix(str(value))).strip()
    if "<" not in unescaped or ">" not in unescaped:
        return None
    return BeautifulSoup(unescaped[unescaped.find("<") :], "html.parser")


def _find_text(root: ET.Element, path: str) -> str:
    item = root.find(path)
    if item is None:
        return ""
    if item.text is None:
        child_xml = "".join(ET.tostring(child, encoding="unicode") for child in list(item))
        return html.unescape(child_xml).strip()
    return html.unescape(item.text).strip()


def _soup_text(root: Any, path: str) -> str:
    node = root
    for part in path.split("/"):
        if not part:
            continue
        node = node.find(part, recursive=False)
        if node is None:
            return ""
    return html.unescape(node.get_text(" ", strip=True)).strip()


def _soup_markup(root: Any, path: str) -> str:
    node = root
    for part in path.split("/"):
        if not part:
            continue
        node = node.find(part, recursive=False)
        if node is None:
            return ""
    return html.unescape(node.decode_contents()).strip()


def _remove_sender_prefix(value: str) -> str:
    return re.sub(r"^[^\n:]+:\s*\n(?=<)", "", value, count=1)


def _placeholder(key: str) -> str:
    return f"[{PLACEHOLDERS[key]}]"


def _bracket_value(kind: str, value: str) -> str:
    return f"[{PLACEHOLDERS[kind]}|{value}]"


def _clean_plain_text(value: str) -> str:
    text = html.unescape(value or "")
    text = _strip_xml(text).strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()


def _media_placeholder(value: str) -> str:
    mapping = {
        "3": "image",
        "34": "voice",
        "43": "video",
        "47": "emoji",
        "49": "link_file",
        "image": "image",
        "voice": "voice",
        "video": "video",
        "emoji": "emoji",
        "file": "file",
    }
    return _placeholder(mapping.get(value, "non_text"))


def _strip_xml(value: str) -> str:
    if not value:
        return ""
    unescaped = html.unescape(value)
    if "<" not in unescaped or ">" not in unescaped:
        return unescaped
    soup = BeautifulSoup(unescaped, "html.parser")
    text = soup.get_text(" ", strip=True)
    if text:
        return text
    return re.sub(r"<[^>]+>", " ", unescaped).strip()
