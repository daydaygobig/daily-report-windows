"""关系图生图离线验证 CLI（一期探索，不动主链路）。

把 card_data.json 里的人物关系交给生图模型画成整幅关系图，产出对比产物供人工评审：
现行 SVG 渲染版整卡 vs 生图版关系图 + 嵌入生图后的整卡。

用法:
    # 列出数据库里可用的生图模型
    python scripts/gen_relation_image.py --list-models

    # 用指定模型（id 或名称子串）给一张/多张卡生成对比产物
    python scripts/gen_relation_image.py 04/card_data.json --model 兔子
    python scripts/gen_relation_image.py a.json b.json --model 2 --size 1536x1024

产物（每张卡一个目录，data/relation_image_trial/<时间戳>/<NN>/）:
    card.html / card.png      现行 SVG 渲染版整卡（对照基准）
    relation.png              生图模型画的关系图原图（核心评审对象：错别字/排版/风格）
    card.image.html/.png      生图关系图嵌入后的整卡（嵌入效果）
    prompt.txt                本次组装的生图提示词（确定性生成，非人工编写）
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image, ImageStat  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.model import Model  # noqa: E402
from app.services import html_case_card_service as svc  # noqa: E402
from app.integrations import image_generation  # noqa: E402

TRIAL_ROOT = Path(__file__).resolve().parents[1] / "data" / "relation_image_trial"


def _list_image_models() -> None:
    db = SessionLocal()
    try:
        rows = db.query(Model).filter(Model.model_type == "image").all()
        if not rows:
            print("数据库里没有 model_type=image 的模型")
            return
        for m in rows:
            print(f"id={m.id}  name={m.name}  provider={m.provider}  base_url={m.base_url}")
    finally:
        db.close()


def _pick_model(selector: str) -> Model:
    db = SessionLocal()
    try:
        rows = db.query(Model).filter(Model.model_type == "image").all()
        if not rows:
            raise SystemExit("数据库里没有可用的生图模型（model_type=image）")
        if selector.isdigit():
            for m in rows:
                if m.id == int(selector):
                    return m
            raise SystemExit(f"找不到 id={selector} 的生图模型")
        for m in rows:
            if selector in m.name:
                return m
        raise SystemExit(f"找不到名称包含「{selector}」的生图模型；可用："
                         + "、".join(f"{m.id}:{m.name}" for m in rows))
    finally:
        db.close()


def _validate_and_save_image(content: bytes, target: Path) -> tuple[int, int]:
    """校验生图结果（可解码、尺寸、非空白）并统一存成 PNG。"""
    im = Image.open(io.BytesIO(content))
    im.load()
    if im.width < 512 or im.height < 512:
        raise RuntimeError(f"生图尺寸异常: {im.width}x{im.height}")
    stat = ImageStat.Stat(im.convert("L"))
    if stat.stddev[0] < 5:
        raise RuntimeError("生图疑似空白图，已丢弃")
    im.convert("RGB").save(target, format="PNG")
    return im.width, im.height


def run_trial(data_path: Path, model: Model, size: str, index: int, run_dir: Path) -> Path:
    card_dir = run_dir / f"{index:02d}"
    card_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    card = svc.CaseCard.from_dict(payload)

    # 1) 现行 SVG 渲染版整卡（对照基准），同时落好头像/二维码素材
    svc.render_case_card(card, card_dir, card_index=int(payload.get("avatar_index", 1)))

    # 2) 组装提示词并生图
    prompt, mode = svc.compose_relation_prompt(card)
    (card_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    started = time.time()
    generated = asyncio.run(image_generation.generate_image(model, prompt=prompt, size=size))
    # 存进 assets/（HTML 引用 assets/relation.png），根目录留一份评审副本
    assets_dir = card_dir / "assets"
    width, height = _validate_and_save_image(generated.content, assets_dir / "relation.png")
    shutil.copyfile(assets_dir / "relation.png", card_dir / "relation.png")
    elapsed = time.time() - started

    # 3) 生图版关系图嵌入整卡（与 SVG 版共用 assets，便于直接对比）
    avatar = next(card_dir.joinpath("assets").glob("avatar.*"), None)
    css_h = round(svc.DIAGRAM_CANVAS_W * height / width)
    html = svc.build_card_html(
        card,
        avatar_file=f"assets/{avatar.name}" if avatar else "",
        qr_file="assets/qr.png",
        diagram_override={"image_file": "assets/relation.png", "canvas_h": css_h,
                          "nodes": {}, "edges": []},
    )
    image_html_path = card_dir / "card.image.html"
    image_html_path.write_text(html, encoding="utf-8")
    svc.render_html_to_png(image_html_path, card_dir / "card.image.png")

    white = svc._relation_image_passes_gate(card_dir / "relation.png")
    print(f"[{index:02d}] mode={mode}  生图 {width}x{height}  耗时 {elapsed:.0f}s  "
          f"背景{'白 ✓' if white else '不白 ✗（风格不达标，需重试）'}  → {card_dir}")
    return card_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="关系图生图离线验证（一期探索）")
    parser.add_argument("cards", nargs="*", help="card_data.json 路径（可多张）")
    parser.add_argument("--model", default="", help="生图模型 id 或名称子串")
    parser.add_argument("--size", default="1536x1024", help="生图尺寸（默认 1536x1024）")
    parser.add_argument("--list-models", action="store_true", help="列出可用生图模型后退出")
    args = parser.parse_args()

    if args.list_models:
        _list_image_models()
        return
    if not args.cards:
        raise SystemExit("请给出至少一个 card_data.json 路径（或 --list-models 查看模型）")
    if not args.model:
        _list_image_models()
        raise SystemExit("请用 --model 指定生图模型（id 或名称子串）")

    model = _pick_model(args.model)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = TRIAL_ROOT / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"模型: id={model.id} {model.name} ({model.provider})  尺寸: {args.size}")
    print(f"产物目录: {run_dir.resolve()}")
    for index, raw in enumerate(args.cards, start=1):
        data_path = Path(raw)
        if not data_path.is_file():
            print(f"[{index:02d}] 跳过：未找到 {data_path}")
            continue
        try:
            run_trial(data_path, model, args.size, index, run_dir)
        except Exception as exc:  # noqa: BLE001 单卡失败不影响其余卡
            print(f"[{index:02d}] 失败：{exc}")
    print(f"\n评审要点：relation.png 的错别字/压字/风格是否可接受；card.image.png 为嵌入效果；card.png 为现行 SVG 对照。")


if __name__ == "__main__":
    main()
