"""HTML 案例卡渲染 CLI。

常用法：
    # 生成链路自动出卡后，手动改过 card.html（如调整人物关系图的节点/连线），重新出图：
    python scripts/render_html_card.py render data/html_cards/<run>/<NN>

    # 也可直接指定 card.html 文件：
    python scripts/render_html_card.py render data/html_cards/<run>/<NN>/card.html

    # 手改过 card_data.json 后重建 HTML 并出图（会覆盖 card.html）：
    python scripts/render_html_card.py build data/html_cards/<run>/<NN>/card_data.json

render 只截图、绝不改动 card.html；build 会按数据重新生成 card.html。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.config import get_settings  # noqa: E402
from app.services import html_case_card_service as svc  # noqa: E402


def _resolve_card_dir(target: Path) -> Path:
    target = Path(target)
    if target.is_file():
        return target.parent
    if target.is_dir():
        return target
    raise SystemExit(f"路径不存在：{target}" )


def cmd_render(target: str, scale: int) -> None:
    settings = get_settings()
    card_dir = _resolve_card_dir(Path(target))
    html_path = card_dir / "card.html"
    if not html_path.exists():
        raise SystemExit(f"未找到 {html_path}")
    png_path = card_dir / "card.png"
    width, height = svc.render_html_to_png(
        html_path, png_path,
        scale=scale or int(settings.html_card_render_scale),
        edge_path=settings.html_card_edge_path,
    )
    print(f"[OK] 已重渲染（card.html 未改动）\n  HTML: {html_path}\n  PNG : {png_path} ({width}x{height})")


def cmd_build(data_path: str, scale: int) -> None:
    settings = get_settings()
    data_file = Path(data_path)
    if not data_file.is_file():
        raise SystemExit(f"未找到 {data_file}")
    import json

    payload = json.loads(data_file.read_text(encoding="utf-8"))
    card = svc.CaseCard.from_dict(payload)
    rendered = svc.render_case_card(
        card, data_file.parent,
        join_url=settings.html_card_join_url,
        avatar_dir=Path(settings.html_card_avatar_dir),
        edge_path=settings.html_card_edge_path,
        scale=scale or int(settings.html_card_render_scale),
        card_index=int(payload.get("avatar_index", 1)),
    )
    print(f"[OK] 已按 card_data.json 重建\n  HTML: {rendered.html_path}\n  PNG : {rendered.png_path} ({rendered.width}x{rendered.height})")


def main() -> None:
    parser = argparse.ArgumentParser(description="HTML 案例卡渲染工具（手动修正工作流）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render", help="对已有 card.html 重新截图（不改动 HTML）")
    p_render.add_argument("target", help="card.html 路径或其所在目录")
    p_render.add_argument("--scale", type=int, default=0, help="输出倍率（默认取配置）")

    p_build = sub.add_parser("build", help="按 card_data.json 重建 HTML 并出图")
    p_build.add_argument("data", help="card_data.json 路径")
    p_build.add_argument("--scale", type=int, default=0, help="输出倍率（默认取配置）")

    args = parser.parse_args()
    settings = get_settings()
    if args.command == "render":
        cmd_render(args.target, args.scale)
    elif args.command == "build":
        cmd_build(args.data, args.scale)


if __name__ == "__main__":
    main()
