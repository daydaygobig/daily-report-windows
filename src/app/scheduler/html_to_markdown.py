"""HTML 模型输出 → 可读 Markdown 转换（模型输出备份 / IMA 知识库同步用）。

日报作业开启 GitHub 部署或 HTML 备份时，模型被要求返回完整 HTML 文档，
直接同步到知识库会看到满屏标签。这里按语义结构（标题/段落/列表/表格/
引用等）转换成 Markdown；装饰性内容（script/style/nav/按钮/图标）丢弃。
非 HTML 内容（普通 Markdown、卡片 JSON 等）原样返回，不影响卡片链路。
"""

from __future__ import annotations

import re
from typing import List

from bs4 import BeautifulSoup, NavigableString, Tag

from .parsing import _strip_markdown_fence

# 转换时整体丢弃的标签：脚本样式、页面导航、交互按钮（复制/翻页等 UI 噪音）
_DROP_TAGS = {
    "script",
    "style",
    "nav",
    "button",
    "svg",
    "noscript",
    "template",
    "iframe",
    "input",
    "select",
    "textarea",
    "meta",
    "link",
    "title",
    "head",
}

_HEADING_PREFIX = {
    "h1": "#",
    "h2": "##",
    "h3": "###",
    "h4": "####",
    "h5": "#####",
    "h6": "######",
}

_LIST_TAGS = {"ul", "ol"}

# 会被当成独立块处理的标签；其余未知标签按行内容器处理
_BLOCK_TAGS = (
    set(_HEADING_PREFIX)
    | _LIST_TAGS
    | {
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "main",
        "aside",
        "li",
        "table",
        "blockquote",
        "hr",
        "pre",
        "figure",
        "figcaption",
        "details",
        "summary",
        "form",
        "dl",
    }
)

# 容器标签：本身不产生格式，渲染方式取决于内部是否含块级子元素——
# 有则按块递归拆分，没有（如「文字 + <br> + <b>」行内混排）则整体当一段
_CONTAINER_TAGS = {
    "div",
    "span",
    "section",
    "article",
    "header",
    "footer",
    "main",
    "aside",
    "li",
    "figure",
    "figcaption",
    "details",
    "summary",
    "form",
    "dl",
}

_INLINE_MARK_TAGS = {
    "b": "**",
    "strong": "**",
    "i": "*",
    "em": "*",
}


def looks_like_html(content: str) -> bool:
    """判断内容是否为 HTML 文档（先剥掉 ```html 围栏再判断）。"""

    text = _strip_markdown_fence(content or "").lstrip("\ufeff").strip().lower()
    if not text:
        return False
    return (
        text.startswith("<!doctype html")
        or text.startswith("<html")
        or ("<html" in text and "</html>" in text)
    )


def html_to_markdown(content: str) -> str:
    """把 HTML 文档转成 Markdown；不是 HTML 或解析失败时原样返回。"""

    if not content or not looks_like_html(content):
        return content
    try:
        soup = BeautifulSoup(_strip_markdown_fence(content), "html5lib")
    except Exception:
        return content
    root = soup.body or soup
    blocks = [block for block in _render_blocks(root) if block and block.strip()]
    markdown = "\n\n".join(block.strip() for block in blocks if block.strip())
    return markdown or content


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "")


def _render_blocks(node: Tag) -> List[str]:
    """按块渲染节点的直接子节点，返回 Markdown 块列表。"""

    blocks: List[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            text = _collapse_ws(str(child))
            if text.strip():
                blocks.append(text)
        elif isinstance(child, Tag):
            blocks.extend(_render_tag(child))
    return blocks


def _render_tag(tag: Tag) -> List[str]:
    """渲染一个块级标签，返回 Markdown 块列表（列表/表格等多行内容算一块）。"""

    name = tag.name
    if name in _DROP_TAGS:
        return []
    if name in _HEADING_PREFIX:
        inline = _render_inline(tag).strip()
        return [f"{_HEADING_PREFIX[name]} {inline}"] if inline else []
    if name == "p":
        inline = _render_inline(tag).strip()
        return [inline] if inline else []
    if name == "hr":
        return ["---"]
    if name == "pre":
        code = tag.get_text().strip("\n")
        return [f"```\n{code}\n```"] if code.strip() else []
    if name == "blockquote":
        inner = _render_blocks(tag)
        if not inner:
            return []
        quoted = "\n\n".join(inner).splitlines()
        return ["> " + "\n> ".join(line.rstrip() for line in quoted)]
    if name in _LIST_TAGS:
        return _render_list(tag, ordered=name == "ol", level=0)
    if name == "table":
        return _render_table(tag)
    if name == "img":
        src = (tag.get("src") or "").strip()
        alt = _collapse_ws(tag.get("alt") or "").strip() or "图片"
        return [f"![{alt}]({src})"] if src else []
    if name in _CONTAINER_TAGS:
        if _has_block_child(tag):
            return _render_blocks(tag)
        inline = _render_inline(tag).strip()
        return [inline] if inline else []
    if name in _BLOCK_TAGS or _has_block_child(tag):
        return _render_blocks(tag)
    inline = _render_inline(tag).strip()
    return [inline] if inline else []


def _has_block_child(tag: Tag) -> bool:
    """容器内是否含块级后代（决定递归按块拆还是整体当一段）。

    只看块级标签；丢弃类标签（script/button 等）不算——否则一个纯行内
    混排（文字 + <br> + <b>）的容器会因隐藏按钮被误拆成碎段落，
    <br> 承载的行结构也会丢失。
    """

    for child in tag.descendants:
        if isinstance(child, Tag) and child.name in _BLOCK_TAGS:
            return True
    return False


def _render_list(tag: Tag, *, ordered: bool, level: int) -> List[str]:
    lines: List[str] = []
    index = 0
    for item in tag.children:
        if not isinstance(item, Tag) or item.name != "li":
            continue
        index += 1
        marker = f"{index}." if ordered else "-"
        indent = "  " * level
        inline_parts: List[str] = []
        nested_blocks: List[str] = []
        for sub in item.children:
            if isinstance(sub, Tag) and sub.name in _LIST_TAGS:
                nested_blocks.extend(_render_list(sub, ordered=sub.name == "ol", level=level + 1))
            else:
                inline_parts.append(_render_inline_fragment(sub))
        text = "".join(inline_parts).strip()
        if text:
            lines.append(f"{indent}{marker} {text}")
        lines.extend(block for block in nested_blocks if block.strip())
    return ["\n".join(lines)] if lines else []


def _render_table(tag: Tag) -> List[str]:
    rows = []
    for tr in tag.find_all("tr"):
        if not isinstance(tr, Tag):
            continue
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        rows.append([_render_inline(cell).strip() or " " for cell in cells])
    if not rows:
        return []
    width = max(len(row) for row in rows)
    rows = [row + [" "] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return ["\n".join(lines)]


def _render_inline(node: Tag) -> str:
    return "".join(_render_inline_fragment(child) for child in node.children)


def _render_inline_fragment(node) -> str:
    if isinstance(node, NavigableString):
        return _collapse_ws(str(node))
    if not isinstance(node, Tag):
        return ""
    name = node.name
    if name in _DROP_TAGS:
        return ""
    if name == "br":
        return "  \n"
    if name == "img":
        src = (node.get("src") or "").strip()
        alt = _collapse_ws(node.get("alt") or "").strip() or "图片"
        return f"![{alt}]({src})" if src else ""
    if name == "a":
        inner = _render_inline(node).strip()
        href = (node.get("href") or "").strip()
        if inner and href and not href.startswith(("javascript:", "#")):
            return f"[{inner}]({href})"
        return inner
    if name == "code":
        inner = node.get_text().strip()
        return f"`{inner}`" if inner else ""
    if name in _INLINE_MARK_TAGS:
        inner = _render_inline(node).strip()
        return f"{_INLINE_MARK_TAGS[name]}{inner}{_INLINE_MARK_TAGS[name]}" if inner else ""
    if name in _BLOCK_TAGS:
        # 不规范 HTML：块级标签混在行内上下文里，降级为块拼接
        return "\n".join(block for block in _render_tag(node) if block.strip())
    return _render_inline(node)
