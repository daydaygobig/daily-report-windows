#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
案例卡渲染器（B 路径：AI 素材 + 真字体 HTML 排版）
用法:
    python render_card.py sample_input.txt --font A --outdir out
    python render_card.py cards.json --input-json --qr https://md.xinjianhub.cn/
输入: 文本模式为内容块文本（可含多组 上/下 块，自行拆块配对，供手动调试）；
      --input-json 为服务端已配对的 {"cards": [{"top": 上卡块原文, "bottom": 下卡块原文}]}，
      配对真源在服务端 pair_card_blocks，此处只做块内结构化，块首拼卡标记可省略。
输出: 每组一张 1080x6480 拼接长图（card_1.png, card_2.png ...），中间产物 half PNG 在 out/half/
依赖: playwright(chromium)、Pillow；可选 qrcode(--qr 时需要)
"""
import argparse, json, os, re, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
TEMPLATE = (HERE / "card_template.html").read_text(encoding="utf-8")

# ---------------- 解析 ----------------
# 与服务端 image_card_service.CARD_TOP_MARKER / CARD_BOTTOM_MARKER 保持同一匹配规则
CARD_TOP_MARKER = "【拼卡·上】"
CARD_BOTTOM_MARKER = "【拼卡·下】"

EDGE_FWD = re.compile(r"^(.+?)\s*——\((.+?)\)→\s*(.+?)：(.*)$")
EDGE_FWD1 = re.compile(r"^(.+?)\s*—\((.+?)\)→\s*(.+?)：(.*)$")
EDGE_REV = re.compile(r"^(.+?)\s*←——\((.+?)\)——\s*(.+?)：(.*)$")
ITEM = re.compile(r"^\d+、([『「])(.+?)[』」]：(.*)$")
BY = re.compile(r"^——\s*@(.+)$")

def _split_blocks(text):
    blocks, cur = [], None
    for line in text.splitlines():
        s = line.strip()
        if s == "<!-- CONTENT_BLOCK_START -->":
            cur = []
        elif s == "<!-- CONTENT_BLOCK_END -->":
            if cur is not None:
                blocks.append(cur)
            cur = None
        elif cur is not None:
            cur.append(line)
    return blocks

def _section(lines, start_key, end_keys):
    """返回 start_key 之后、end_keys 之前的行（去空行尾部）"""
    out, on = [], False
    for ln in lines:
        s = ln.strip()
        if s.startswith(start_key):
            on = True
            rest = s[len(start_key):].strip().strip("：:").strip()
            if rest:
                out.append(rest)
            continue
        if on and any(s.startswith(k) for k in end_keys):
            break
        if on:
            out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    return out

def _groups(lines):
    gs, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            gs.append(cur); cur = []
    if cur:
        gs.append(cur)
    return gs

def parse_top(lines):
    d = {}
    body = lines[:]
    d["gender"] = "male"
    if body and re.match(r"^IP角色：", body[0]):
        d["gender"] = "female" if "女" in body[0] else "male"
        body = body[1:]
    d["title"] = body[0].strip()
    d["subtitle"] = body[1].strip().lstrip("🔍").strip()
    kw_line = next(l for l in body if l.strip().startswith("关键词"))
    d["keywords"] = [k.strip() for k in kw_line.split("：", 1)[1].replace("，", "、").split("、") if k.strip()]

    bg = _section(body, "背景概述", ["人物关系"])
    gs = _groups(bg)
    d["facts"] = []
    for ln in gs[0]:
        tag, _, txt = ln.partition("｜")
        d["facts"].append({"tag": tag.strip(), "text": txt.strip()})
    d["scenes"] = gs[1] if len(gs) > 1 else []
    d["question"] = (gs[2][0] if len(gs) > 2 else (gs[-1][0] if gs else ""))

    rel = _section(body, "人物关系", ["__none__"])
    edges = []
    for ln in rel:
        s = ln.strip()
        if s.startswith("整体结构"):
            d["structure"] = s.split("：", 1)[1].strip()
            continue
        m = EDGE_REV.match(s) or EDGE_FWD.match(s) or EDGE_FWD1.match(s)
        if m:
            a, verb, b, note = m.groups()
            edges.append({"from": a.strip(), "to": b.strip(), "verb": verb.strip(),
                          "note": note.strip(), "dashed": False})
    d["relations"] = {"edges": edges, "structure": d.get("structure", "")}
    return d

def parse_bottom(lines):
    d = {}
    def items_of(key, next_keys):
        out = []
        for ln in _section(lines, key, next_keys):
            m = ITEM.match(ln.strip())
            if m:
                out.append({"tag": m.group(2).strip(), "text": m.group(3).strip(),
                            "qo": m.group(1), "qc": "』" if m.group(1)=="『" else "」"})
        return out
    d["analysis"] = items_of("分析过程", ["解决方案", "金句"])
    d["solution"] = items_of("解决方案", ["金句"])
    quotes, cur = [], []
    for ln in _section(lines, "金句", ["__none__"]):
        s = ln.strip()
        m = BY.match(s)
        if m:
            if cur:
                quotes.append({"text": " ".join(cur), "by": m.group(1).strip().lstrip("@")})
                cur = []
        elif s:
            cur.append(s)
    if cur:
        quotes.append({"text": " ".join(cur), "by": "?"})
    d["quotes"] = quotes
    return d

def _take_marker(lines, marker):
    """定位第一个非空行；行首匹配 marker 时把行内余文（如「【拼卡·上】：标题」）
    并入正文首行。返回 (是否匹配, 标记行之后的正文行)。"""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith(marker):
            return False, []
        rest = stripped[len(marker):].strip().strip("：:").strip()
        body = lines[index + 1:]
        return True, ([rest] if rest else []) + body
    return False, []


def parse_input(text):
    blocks = _split_blocks(text)
    parsed = []
    for block_index, b in enumerate(blocks, 1):
        matched, body = _take_marker(b, CARD_TOP_MARKER)
        if matched:
            parsed.append(("top", parse_top(body)))
            continue
        matched, body = _take_marker(b, CARD_BOTTOM_MARKER)
        if matched:
            parsed.append(("bottom", parse_bottom(body)))
            continue
        first = next((ln.strip() for ln in b if ln.strip()), "")
        # 拼卡渲染要求每个内容块第一行带标记；静默跳过会导致
        # 后续按序配对时把两个话题拼进同一张卡
        raise ValueError(
            f"第 {block_index} 个内容块第一行必须是【拼卡·上】或【拼卡·下】，实际是：{first[:30] or '（空）'}"
        )
    cards, i = [], 0
    while i < len(parsed):
        kind, data = parsed[i]
        if kind == "top" and i + 1 < len(parsed) and parsed[i + 1][0] == "bottom":
            cards.append({"top": parsed[i][1], "bottom": parsed[i + 1][1],
                          "gender": parsed[i][1].get("gender", "male")})
            i += 2
        elif kind == "top":
            raise ValueError(f"第 {i + 1} 个内容块是【拼卡·上】，但没有紧跟配对的【拼卡·下】（内容块总数须为偶数）")
        else:
            raise ValueError(f"第 {i + 1} 个内容块是【拼卡·下】，但前面没有待配对的【拼卡·上】")
    return cards


def _strip_optional_marker(lines, marker, other_marker):
    """剥离块首的可选拼卡标记行；无标记时从首个非空行开始。

    JSON 输入已完成配对，标记行只是冗余标注；但标记与所在半卡不符
    （上卡带【拼卡·下】标记）说明上游配对出错，必须当场报错，
    否则标记行会被当成正文渲染进卡片。
    """
    matched, body = _take_marker(lines, marker)
    if matched:
        return body
    first = next((ln.strip() for ln in lines if ln.strip()), "")
    if first.startswith(other_marker):
        raise ValueError(f"内容块标记与所在半卡不符：{first[:30]}")
    for index, line in enumerate(lines):
        if line.strip():
            return lines[index:]
    return []


def parse_cards_json(text):
    """解析服务端已配对的 JSON 输入：{"cards": [{"top": 上卡块原文, "bottom": 下卡块原文}]}。

    配对真源在服务端 image_card_service.pair_card_blocks，此处不做拆块与配对，
    只负责块内结构化（parse_top / parse_bottom）。
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 输入解析失败：{exc}")
    items = payload.get("cards") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("JSON 输入缺少非空 cards 数组")
    cards = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 组卡片不是对象")
        top_raw, bottom_raw = item.get("top"), item.get("bottom")
        if not isinstance(top_raw, str) or not isinstance(bottom_raw, str):
            raise ValueError(f"第 {index} 组卡片缺少 top/bottom 文本字段")
        top_lines = _strip_optional_marker(top_raw.splitlines(), CARD_TOP_MARKER, CARD_BOTTOM_MARKER)
        bottom_lines = _strip_optional_marker(bottom_raw.splitlines(), CARD_BOTTOM_MARKER, CARD_TOP_MARKER)
        top_data = parse_top(top_lines)
        cards.append({
            "top": top_data,
            "bottom": parse_bottom(bottom_lines),
            "gender": top_data.get("gender", "male"),
        })
    return cards

# ---------------- 校验 ----------------
def validate(card):
    probs = []
    t, b = card["top"], card["bottom"]
    if len(t["facts"]) != 3: probs.append(f"事实字段应为3行，实际{len(t['facts'])}")
    if len(t["scenes"]) != 3: probs.append(f"场景叙述应为3行，实际{len(t['scenes'])}")
    if not t["question"].endswith(("？", "?")): probs.append(f"背景末行不是问句：{t['question'][:20]}")
    for s in t["scenes"]:
        if len(s) > 30: probs.append(f"场景行超30字({len(s)})：{s[:18]}…")
    if not (3 <= len(b["analysis"]) <= 4): probs.append(f"分析应3~4条，实际{len(b['analysis'])}")
    if not (3 <= len(b["solution"]) <= 4): probs.append(f"方案应3~4条，实际{len(b['solution'])}")
    if not (2 <= len(b["quotes"]) <= 3): probs.append(f"金句应2~3条，实际{len(b['quotes'])}")
    for it in b["analysis"] + b["solution"]:
        if len(it["text"]) > 70: probs.append(f"条目超70字：『{it['tag']}』{len(it['text'])}字")
    if not t.get("structure"): probs.append("缺少整体结构行")
    if len(t["relations"]["edges"]) < 2: probs.append(f"关系线仅{len(t['relations']['edges'])}条")
    return probs

# ---------------- 渲染 ----------------
def render_half(browser, card, half, theme, out_png):
    data = {
        "gender": card.get("gender", "male"),
        "pose": card.get("pose", "think"),
        "top": card["top"], "bottom": card["bottom"],
        "qr": card.get("qr", ""),
    }
    html = (TEMPLATE
            .replace("__THEME__", theme)
            .replace("__HALF__", half)
            .replace("/*__CARD_DATA__*/null", json.dumps(data, ensure_ascii=False)))
    fd, tmp_name = tempfile.mkstemp(suffix=".html", dir=str(HERE))
    os.close(fd)  # 未关闭的句柄会让 Windows 上的 unlink 失败，临时文件就此堆积
    tmp = Path(tmp_name)
    tmp.write_text(html, encoding="utf-8")
    try:
        page = browser.new_page(viewport={"width": 1180, "height": 3340}, device_scale_factor=1)
        try:
            page.goto(tmp.as_uri())
            page.wait_for_function("window.__RESOLVED__===true", timeout=10000)
            page.evaluate("document.fonts.ready.then(()=>1)")
            page.wait_for_timeout(250)
            overflow = page.evaluate("window.__OVERFLOW__ || []")
            page.locator("#canvas").screenshot(path=str(out_png))
        finally:
            page.close()
        return overflow
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass  # Windows 下浏览器进程可能短暂占用，留给下次覆盖


def render_cards(cards, theme, halfdir, *, skip=frozenset()):
    """渲染全部半卡，返回 {(卡序号, 半卡): 溢出模块列表}。

    整批共用一个浏览器实例（Chromium 冷启动是大头开销）；每半卡独立 page，
    单次渲染失败时重启浏览器重试一次，避免坏状态波及后续卡片。
    """
    from playwright.sync_api import sync_playwright
    overflows = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for idx, card in enumerate(cards, 1):
                if idx in skip:
                    continue
                for half, out_png in (
                    ("top", halfdir / f"card{idx}_top.png"),
                    ("bottom", halfdir / f"card{idx}_bottom.png"),
                ):
                    try:
                        overflows[(idx, half)] = render_half(browser, card, half, theme, out_png)
                    except Exception:
                        browser.close()
                        browser = p.chromium.launch()
                        overflows[(idx, half)] = render_half(browser, card, half, theme, out_png)
        finally:
            try:
                browser.close()
            except Exception:
                pass
    return overflows

def stitch(top_png, bottom_png, out_png, qr=None):
    from PIL import Image
    a, b = Image.open(top_png), Image.open(bottom_png)
    W = max(a.width, b.width)
    canvas = Image.new("RGB", (W, a.height + b.height), (248, 243, 227))
    canvas.paste(a, (0, 0)); canvas.paste(b, (0, a.height))
    if qr:
        try:
            import qrcode
            img = qrcode.make(qr).resize((216, 216))
            canvas.paste(img, (1080 - 36 - 216, a.height + (b.height - 100 - 216)))
        except ImportError:
            print("[warn] 未安装 qrcode，跳过二维码（pip install qrcode）")
    canvas.save(out_png)

# ---------------- 素材去底（--whiten DIR：把白底素材转为透明底） ----------------
def whiten(directory):
    from PIL import Image
    for f in Path(directory).glob("*.png"):
        img = Image.open(f).convert("RGBA")
        px = img.load()
        w, h = img.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if r > 243 and g > 243 and b > 243:
                    px[x, y] = (r, g, b, 0)
        img.save(f)
        print(f"去底完成: {f.name}")

# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="内容块文本文件；--input-json 模式下为已配对 JSON 文件")
    ap.add_argument("--input-json", action="store_true",
                    help="输入为服务端已配对的 JSON（{\"cards\":[{\"top\":…,\"bottom\":…}]}），跳过本地拆块配对")
    ap.add_argument("--font", default="A", choices=["A", "B", "C"], help="字体主题")
    ap.add_argument("--outdir", default=str(HERE / "out"))
    ap.add_argument("--qr", default=None, help="二维码链接（叠在右下角预留区）")
    ap.add_argument("--strict", action="store_true", help="校验不合格即跳过该卡")
    ap.add_argument("--whiten", default=None, help="把目录内白底 PNG 转透明底（素材处理）")
    args = ap.parse_args()

    if args.whiten:
        whiten(args.whiten); return

    text = Path(args.input).read_text(encoding="utf-8")
    try:
        cards = parse_cards_json(text) if args.input_json else parse_input(text)
    except ValueError as exc:
        stage = "JSON 解析失败" if args.input_json else "内容块配对校验失败"
        print(f"{stage}：{exc}")
        sys.exit(1)
    if not cards:
        print("未解析到完整卡片（需要一对 上/下 内容块）"); sys.exit(1)

    outdir = Path(args.outdir); halfdir = outdir / "half"
    halfdir.mkdir(parents=True, exist_ok=True)

    qr_uri = ""
    if args.qr:
        try:
            import qrcode
            qr_png = halfdir / "qr.png"
            qrcode.make(args.qr).resize((216, 216)).save(qr_png)
            qr_uri = qr_png.resolve().as_uri()
        except ImportError:
            print("[warn] 未安装 qrcode，跳过二维码（pip install qrcode）")

    strict_skip = set()
    for idx, card in enumerate(cards, 1):
        card["qr"] = qr_uri
        probs = validate(card)
        if probs:
            for p in probs: print(f"[card {idx}] 校验: {p}")
            if args.strict:
                strict_skip.add(idx)
    overflows = render_cards(cards, args.font, halfdir, skip=strict_skip)
    for idx in range(1, len(cards) + 1):
        if idx in strict_skip:
            continue
        for name, half in (("上卡", "top"), ("下卡", "bottom")):
            ov = overflows.get((idx, half))
            if ov: print(f"[card {idx}] {name}内容溢出模块: {', '.join(ov)}")
        out_png = outdir / f"card_{idx}.png"
        top_png = halfdir / f"card{idx}_top.png"
        bot_png = halfdir / f"card{idx}_bottom.png"
        stitch(top_png, bot_png, out_png, qr=None)  # 二维码在下卡模板内渲染
        print(f"[card {idx}] 完成 -> {out_png}")
    sys.exit(1 if strict_skip else 0)

if __name__ == "__main__":
    main()
