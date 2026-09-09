# card_renderer — 案例卡 B 路径渲染器（AI 素材 + 真字体排版）

文字由 HTML/CSS 用真实字体排版（永不乱码），AI 只负责离线生成免抠素材。
输入 prompt 3 输出的内容块文本，输出 1080×6480 拼接长图。

## 首次准备（一次性）

1. `pip install playwright qrcode pillow`，然后 `python -m playwright install chromium`
2. 按 `fonts/README.txt` 下载字体放入 `fonts/`（不放也能渲染，自动回退系统字体）
3. 按 `assets_prompts.md` 用 GPT Image 生成素材 PNG 放入 `assets/`
   （白底素材用 `python render_card.py --whiten assets` 去底；素材不齐也不阻塞，缺的画虚线占位框）

## 日常使用

```bash
# 渲染一批内容块（可含多组 上/下 块），字体主题 A
python render_card.py input.txt --font A --qr https://md.xinjianhub.cn/

# 严格模式：校验不合格的卡直接跳过
python render_card.py input.txt --strict
```

- 输出：`out/card_1.png, card_2.png ...`（1080×6480，右下角已叠二维码）
- 中间产物：`out/half/`（上卡、下卡单图，各 1080×3240）
- 字体主题：`--font A`（黄油体+MiSans+沐瑶手写，首选）｜`B`（优设标题黑+普惠体，稳重）｜`C`（快乐体+江城圆+悠哉，活泼）

## 自动化接入

把 `render_card.py` 接在 prompt 3 输出之后即可：

```
聊天记录 → [prompt1+LLM] 日报/话题 → [prompt3+LLM] 内容块 → render_card.py → 长图 → 飞书
```

脚本内置校验器（事实3行/场景3行/问句收尾/分析3-4条/方案3-4条/金句2-3条/条目≤70字），
不合格会在控制台列出问题；配合 `--strict` 可在上游 LLM 重写循环中使用。

内容块第一行的「IP角色：男/女」标记决定用哪套 IP 素材（无标记默认男）。

## 已知边界

- 内容超载时整卡等比缩小（下限 0.6），缩到下限会在控制台告警——说明文字源超版式预算，应回炉文案而不是调模板
- 关系图布局为确定性算法：当事人居中最大，外圈节点按数量等分环绕；外圈之间的连线走底部弧线；
  含「制度/话术工具」类无形角色时给该边加 dashed（prompt 3 文本中该边写为虚线描述即可，解析器暂以 `←——` 反向线或后续扩展识别）
- 换风格只改 `card_template.html` 的 CSS 变量与色板
