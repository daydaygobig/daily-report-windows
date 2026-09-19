"""历史模型输出备份批量转 Markdown（一次性迁移脚本）。

背景：开启 GitHub 部署/HTML 备份的作业，历史模型输出文件（.md/.txt）里
存的是 HTML 网页源码，阅读不便。本脚本用 html_to_markdown 把它们转成
可读 Markdown，做三件事：

1. 原件备份：HTML 原文复制到 backups/model_outputs_html_raw/（保持相对路径）；
2. 原地转换：backups/model_outputs/ 下的 HTML 内容文件覆盖为 Markdown 版；
3. IMA 新目录：转换结果另存到 backups/model_outputs_md/，文件名加「_文字版」
   后缀——IMA 按文件名去重，沿用原名会被当成重复跳过。

非 HTML 内容（卡片 JSON、原生 Markdown）不动。脚本可重复执行：
已转换的文件不再是 HTML，第二次运行会自动跳过。

用法：在项目根目录执行
    PYTHONPATH=src python scripts/convert_legacy_model_outputs.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from app.scheduler.html_to_markdown import html_to_markdown, looks_like_html

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "backups" / "model_outputs"
HTML_RAW_BACKUP_DIR = PROJECT_ROOT / "backups" / "model_outputs_html_raw"
IMA_MD_DIR = PROJECT_ROOT / "backups" / "model_outputs_md"
IMA_SUFFIX = "_文字版"


def main() -> int:
    if not SOURCE_DIR.is_dir():
        print(f"找不到目录：{SOURCE_DIR}")
        return 1
    converted = skipped = 0
    for path in sorted(SOURCE_DIR.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        if not looks_like_html(content):
            skipped += 1
            continue
        markdown = html_to_markdown(content).strip()
        if not markdown or markdown == content.strip():
            print(f"[跳过] 转换无变化：{path.relative_to(PROJECT_ROOT)}")
            skipped += 1
            continue
        relative = path.relative_to(SOURCE_DIR)
        # 1. 备份 HTML 原文
        raw_backup = HTML_RAW_BACKUP_DIR / relative
        if not raw_backup.exists():
            raw_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, raw_backup)
        # 2. 原地覆盖为 Markdown
        path.write_text(markdown + "\n", encoding="utf-8")
        # 3. IMA 新目录（加后缀防同名去重跳过）
        ima_path = IMA_MD_DIR / relative
        ima_path = ima_path.with_name(ima_path.stem + IMA_SUFFIX + ima_path.suffix)
        ima_path.parent.mkdir(parents=True, exist_ok=True)
        ima_path.write_text(markdown + "\n", encoding="utf-8")
        converted += 1
        print(f"[转换] {relative}  →  {ima_path.relative_to(PROJECT_ROOT)}")
    print(f"\n完成：转换 {converted} 个，跳过 {skipped} 个（非 HTML）")
    print(f"HTML 原件备份：{HTML_RAW_BACKUP_DIR.relative_to(PROJECT_ROOT)}")
    print(f"IMA 同步用新目录：{IMA_MD_DIR.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
