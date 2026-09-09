#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
案例卡免抠素材批量生成（调用中转站 gpt-image-2）
用法:
    python gen_assets.py                # 生成全部缺失素材
    python gen_assets.py --only ip_male_think.png   # 只生成指定素材
    python gen_assets.py --list         # 列出全部素材与状态
    python gen_assets.py --force        # 已存在的也重新生成
凭证: image_api.json (base/endpoint/model/key)
"""
import argparse, base64, json, sys, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "assets"

COMMON = ("手绘水彩×彩铅插画风格，扁平无透视、2D 插画感，线条用深蓝 #2B4A9B 细线，"
          "配色只允许深蓝 #2B4A9B、荧光黄 #FFE28A、暖橙 #E8935A、浅蓝 #D6E6F7、米白 #F8F3E3，"
          "画面干净有留白，背景必须完全透明（输出带 alpha 通道的 PNG），绝对不要绘制棋盘格、灰白格子、透明格纹图案来表示透明，画面中绝对不要出现任何文字、字母、数字，"
          "不要立体阴影、渐变高光、摄影写实质感。")

IP_M = "年轻中国职场男青年半身插画，黑色短发，穿浅蓝色衬衫（袖口卷起），胸前挂深蓝色工牌挂绳，腰身以上半身特写，正面微侧"
IP_F = "年轻中国职场女青年半身插画，深棕色齐肩发，穿浅蓝色衬衫（袖口卷起），胸前挂深蓝色工牌挂绳，腰身以上半身特写，正面微侧"

ASSETS = [
    ("ip_male_think.png",     f"{IP_M}，单手托下巴、眉头微抬做思考状"),
    ("ip_male_surprise.png",  f"{IP_M}，双眼睁大、嘴微张、双手微抬做惊讶状"),
    ("ip_male_facepalm.png",  f"{IP_M}，一手捂住半张脸，露出无奈表情"),
    ("ip_male_raise.png",     f"{IP_M}，一手举高做出课堂提问姿势，表情积极"),
    ("ip_female_think.png",   f"{IP_F}，单手托下巴做思考状"),
    ("ip_female_surprise.png",f"{IP_F}，双眼睁大、嘴微张、双手微抬做惊讶状"),
    ("ip_female_facepalm.png",f"{IP_F}，一手捂住半张脸，露出无奈表情"),
    ("ip_female_raise.png",   f"{IP_F}，一手举高做出课堂提问姿势，表情积极"),
    ("mascot_cup.png",        "一只有可爱笑脸的咖啡杯彩铅小涂鸦，杯子白色，热气温馨"),
    ("mascot_folder.png",     "一只带笑脸的办公文件夹彩铅小涂鸦，淡蓝色"),
    ("mascot_badge.png",      "一只带笑脸的员工工牌彩铅小涂鸦，挂绳深蓝色"),
    ("deco_leaf.png",         "一小枝绿色叶子彩铅涂鸦，叶子三到五片，枝条纤细"),
    ("deco_daisy.png",        "一朵橙色花心白色花瓣的小雏菊彩铅涂鸦"),
    ("deco_heart.png",        "一颗暖橙色手绘爱心涂鸦，笔触随意"),
    ("deco_star.png",         "一颗荧光黄四角闪光星星涂鸦"),
    ("deco_bulb.png",         "一只深蓝细线手绘小灯泡涂鸦，灯丝清晰"),
    ("tape_blue.png",         "一条蓝白格纹和纸胶带，水平放置，半透明纸质，两端有撕纸毛边，微微翘起"),
    ("tape_yellow.png",       "一条黄白格纹和纸胶带，水平放置，半透明纸质，两端有撕纸毛边，微微翘起"),
    ("swash_blue.png",        "一块横向长方形的浅蓝色 #D6E6F7 水彩笔刷涂抹色块，边缘有水彩晕染的不规则毛边，中间均匀"),
]

def api_generate(prompt, cfg, timeout=300, retries=5):
    import time
    def body(with_bg):
        payload = {"model": cfg["model"], "prompt": f"{prompt}。{COMMON}",
                   "n": 1, "size": "1024x1024", "output_format": "png"}
        if with_bg: payload["background"] = "transparent"
        return json.dumps(payload).encode("utf-8")
    last = None
    for attempt in range(retries):
        with_bg = (attempt < retries - 1)   # 最后一次退回白底，规避不支持 transparent 的上游
        req = urllib.request.Request(
            cfg["endpoint"], data=body(with_bg), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {cfg['key']}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            item = data["data"][0]
            if item.get("b64_json"):
                return base64.b64decode(item["b64_json"]), None
            if item.get("url"):
                with urllib.request.urlopen(item["url"], timeout=timeout) as r2:
                    return r2.read(), item["url"]
            raise RuntimeError(f"响应中既无 b64_json 也无 url: {json.dumps(data)[:200]}")
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", "replace")
            if e.code == 400 and with_bg:
                last = e; with_bg_note = "transparent 不被支持，改用白底"; 
                print(f"      400 -> 回退白底重试", flush=True); continue
            if e.code in (429, 500, 502, 503) or 'overloaded' in body_txt:
                wait = 10 + attempt * 15
                print(f"      {e.code} 繁忙，{wait}s 后重试({attempt+1}/{retries})", flush=True)
                time.sleep(wait); last = e; continue
            raise
    raise last if last else RuntimeError("重试耗尽")
    item = data["data"][0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"]), None
    if item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=timeout) as r2:
            return r2.read(), item["url"]
    raise RuntimeError(f"响应中既无 b64_json 也无 url: {json.dumps(data)[:200]}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只生成指定文件名（如 ip_male_think.png）")
    ap.add_argument("--force", action="store_true", help="已存在也重新生成")
    ap.add_argument("--list", action="store_true", help="列出素材状态")
    args = ap.parse_args()

    cfg = json.loads((HERE / "image_api.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)

    if args.list:
        for name, _ in ASSETS:
            mark = "OK " if (OUT / name).exists() else "缺 "
            print(mark, name)
        return

    todo = [(n, p) for n, p in ASSETS
            if (args.only in (None, n)) and (args.force or not (OUT / n).exists())]
    if args.only and not todo:
        print(f"{args.only} 已存在（--force 可强制重生成）"); return

    ok = fail = 0
    for name, prompt in todo:
        print(f"[gen] {name} ...", flush=True)
        try:
            img, via = api_generate(prompt, cfg)
            (OUT / name).write_bytes(img)
            has_alpha = False
            try:
                from PIL import Image
                im = Image.open(OUT / name)
                has_alpha = im.mode in ("RGBA", "LA") and im.getextrema()[-1][0] < 255
            except Exception:
                pass
            note = "" if has_alpha else "（无透明通道，可后续 --whiten）"
            print(f"      完成 {len(img)//1024}KB via={via or 'b64'} {note}", flush=True)
            ok += 1
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            print(f"      HTTP {e.code}: {body}", flush=True); fail += 1
        except Exception as e:
            print(f"      失败: {e}", flush=True); fail += 1
    print(f"\n完成 {ok} 张，失败 {fail} 张；输出目录: {OUT}")
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    main()
