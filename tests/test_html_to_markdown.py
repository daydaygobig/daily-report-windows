"""html_to_markdown：HTML 模型输出转 Markdown 的单元测试。"""

from app.scheduler.html_to_markdown import (
    html_to_markdown,
    looks_like_html,
)


def _doc(body: str) -> str:
    return f"<!DOCTYPE html>\n<html><head><title>标题</title></head><body>\n{body}\n</body></html>"


def test_非HTML内容原样返回():
    md = "# 已是 Markdown\n\n正文内容"
    assert html_to_markdown(md) == md
    json_output = '```json\n{"cards": []}\n```'
    assert html_to_markdown(json_output) == json_output


def test_识别HTML文档():
    assert looks_like_html(_doc("<p>hi</p>"))
    assert looks_like_html("```html\n" + _doc("<p>hi</p>") + "\n```")
    assert not looks_like_html("# 标题\n正文")
    assert not looks_like_html('{"cards": []}')


def test_围栏包裹的HTML会被剥掉围栏():
    fenced = "```html\n" + _doc("<h1>标题</h1>") + "\n```"
    assert "```" not in html_to_markdown(fenced)
    assert html_to_markdown(fenced).startswith("# 标题")


def test_标题与行内样式():
    html = _doc(
        "<h1>一级</h1><h4>四级</h4>"
        "<p>包含<b>加粗</b>、<i>斜体</i>、<strong>加粗2</strong>和"
        '<a href="https://example.com">链接</a>文字</p>'
    )
    markdown = html_to_markdown(html)
    assert "# 一级" in markdown
    assert "#### 四级" in markdown
    assert "**加粗**" in markdown
    assert "**加粗2**" in markdown
    assert "*斜体*" in markdown
    assert "[链接](https://example.com)" in markdown


def test_无href链接只保留文字():
    html = _doc('<p>前<a name="anchor">锚点</a>后</p>')
    assert "锚点" in html_to_markdown(html)
    assert "](" not in html_to_markdown(html)


def test_嵌套列表():
    html = _doc(
        "<ul><li>第一项</li><li>第二项<ol><li>嵌套一</li><li>嵌套二</li></ol></li><li>第三项</li></ul>"
    )
    markdown = html_to_markdown(html)
    assert "- 第一项" in markdown
    assert "- 第二项" in markdown
    assert "  1. 嵌套一" in markdown
    assert "  2. 嵌套二" in markdown
    assert "- 第三项" in markdown


def test_表格转Markdown表格():
    html = _doc(
        "<table><tr><th>项目</th><th>数值</th></tr>"
        "<tr><td>消息数</td><td>100</td></tr>"
        "<tr><td>参与人</td><td>3</td></tr></table>"
    )
    markdown = html_to_markdown(html)
    assert "| 项目 | 数值 |" in markdown
    assert "| --- | --- |" in markdown
    assert "| 消息数 | 100 |" in markdown


def test_交互与脚本噪音被丢弃():
    html = _doc(
        "<nav><a>前一天</a><a>后一天</a></nav>"
        "<p>正文段落</p>"
        '<button class="copy-btn" title="复制金句">复制</button>'
        "<script>var x = '不应出现';</script>"
        "<style>.a { color: red; }</style>"
    )
    markdown = html_to_markdown(html)
    assert "正文段落" in markdown
    assert "复制" not in markdown
    assert "不应出现" not in markdown
    assert "前一天" not in markdown
    assert "color: red" not in markdown


def test_换行标签保留分行():
    html = _doc("<p>第一行<br>第二行</p>")
    markdown = html_to_markdown(html)
    assert "第一行" in markdown
    assert "第二行" in markdown
    assert markdown.count("\n") >= 1


def test_引用块():
    html = _doc("<blockquote><p>引用内容</p></blockquote>")
    assert "> 引用内容" in html_to_markdown(html)


def test_图标空元素不产生空行():
    html = _doc('<p><i class="fas fa-clock"></i>20:16 - 22:50</p>')
    markdown = html_to_markdown(html)
    assert "20:16 - 22:50" in markdown
    assert "**" not in markdown


def test_未闭合标签宽容处理():
    # html5lib 会自动修复未闭合标签，转换仍应产出正文而不是报错/丢内容
    broken = "<html><body><p>未闭合段落"
    markdown = html_to_markdown(broken)
    assert "未闭合段落" in markdown


def test_行内混排容器不因隐藏按钮被拆碎():
    # 日报正文的真实结构：一个 div 里「文字 + <br> + <b>」行内混排，
    # 还夹着隐藏的展开按钮；应整体渲染为一段，<br> 变换行，序号不孤立
    html = _doc(
        '<div class="content">'
        "<b>一、背景</b><br>这里是背景说明。<br><br>"
        "1. <b>张三</b>提出了观点。<br>2. <b>李四</b>表示同意。"
        '<button class="expand-btn" style="display: none;">展开全文</button>'
        "</div>"
    )
    markdown = html_to_markdown(html)
    assert "**一、背景**  \n这里是背景说明。" in markdown
    assert "1. **张三**提出了观点。" in markdown
    assert "2. **李四**表示同意。" in markdown
    assert "展开全文" not in markdown
