"""weflow 消息解析特征锁定：appmsg 内容解析合并为单一 soup 路径后的既有输出。

历史上 _app_message_content 是 ET 解析优先、soup 兜底的双轨实现；12 组语料对比确认
两版输出一致后合并为单一路径。本文件锁定合并后的输出，防止未来回归。
_embedded_app_summary 保留 ET 优先双轨（soup 会把自闭合标签/内嵌 HTML 当文本，见函数内注释）。
"""

from __future__ import annotations

import pytest

from app.integrations import weflow

MEMBERS = {"wxid_001": "张三", "wxid_002": "李四"}

SHARE_LINK = '<msg><appmsg appid="" sdkver="0"><title>深度好文：如何做好日报</title><des>一文讲透日报自动化</des><type>33</type><url>https://example.com/a?x=1</url><lowurl>https://example.com/a</lowurl><appattach><filename></filename></appattach></appmsg></msg>'
FILE_MSG = '<msg><appmsg><title>季度报表.xlsx</title><des></des><type>6</type><url></url><appattach><filename>季度报表.xlsx</filename></appattach></appmsg></msg>'
QUOTE_TEXT = '<msg><appmsg><title>张三：今天的数据我补一下</title><type>57</type><refermsg><type>1</type><svrid>10001</svrid><chatusr>wxid_002</chatusr><displayname>李四</displayname><createtime>1757400000</createtime><content>今天的日报数据有误</content></refermsg></appmsg></msg>'
FINDER = '<msg><appmsg><title>视频号动态</title><des></des><type>51</type><url>https://channels.weixin.qq.com/x</url></appmsg></msg>'
MONEY = '<msg><appmsg><title>微信红包</title><des>请查收</des><type>2000</type><url>https://example.com</url></appmsg></msg>'
MEDIA_VIDEO = '<msg><appmsg><title></title><des></des><type>43</type><url></url></appmsg></msg>'
MALFORMED = '<msg><appmsg><title>坏数据 <b>粗体</title><type>33</type><url>https://e.com/y</url></appmsg></msg>'
NO_APPMSG = '<msg><voipmsg><flag>3</flag></voipmsg></msg>'
FORWARD_RECORD = '<msg><appmsg><title>张三和李四的聊天记录</title><type>19</type><recorditem><recordinfo><title>张三和李四的聊天记录</title><desc>张三: 你好 2023-01-01&#xA;李四: 早上好</desc><dataitem datatype="1" dataid="1"><datadesc>张三: 你好&#xA;李四: 早上好</datadesc></dataitem></recordinfo></recorditem></appmsg></msg>'
ENTITIES = '<msg><appmsg><title>利润 &amp; 成本核算</title><des></des><type>5</type><url>https://e.com/z?a=1&amp;b=2</url></appmsg></msg>'


@pytest.mark.parametrize(
    "raw,expected",
    [
        (SHARE_LINK, "[链接|深度好文：如何做好日报](https://example.com/a?x=1)"),
        (FILE_MSG, "[文件|季度报表.xlsx]"),
        (FINDER, "[视频号]"),
        (MONEY, "[红包/转账]"),
        (MEDIA_VIDEO, "[非文本消息]"),
        (MALFORMED, "[链接|坏数据 粗体](https://e.com/y)"),
        (NO_APPMSG, None),
        (
            FORWARD_RECORD,
            "[转发聊天记录|张三和李四的聊天记录]\n> 张三: 你好\n> 李四: 早上好",
        ),
        (ENTITIES, "[链接|利润 & 成本核算](https://e.com/z?a=1&b=2)"),
    ],
)
def test_app_message_content_locked_outputs(raw, expected):
    assert weflow._app_message_content(raw, member_names=MEMBERS) == expected


def test_quote_reply_content():
    content = weflow._app_message_content(QUOTE_TEXT, member_names=MEMBERS)
    created = weflow._format_refer_time("1757400000")
    expected = f"> 李四(wxid_002) {created}\n> 今天的日报数据有误\n张三：今天的数据我补一下"
    assert content == expected


def test_embedded_app_summary_prefers_xml_parser():
    """ET 分支对内嵌 HTML 的处理：标签被解码为文本而非原样保留。"""
    raw = MALFORMED
    summary = weflow._embedded_app_summary(raw)
    assert summary is not None
    assert "<b>" not in summary


def test_malformed_fragment_matches_et_and_soup_paths():
    """合并后主路径在畸形输入上仍与原 ET 优先版输出一致。"""
    assert (
        weflow._app_message_content(MALFORMED, member_names=MEMBERS)
        == weflow._app_message_content_soup(MALFORMED, member_names=MEMBERS)
    )
