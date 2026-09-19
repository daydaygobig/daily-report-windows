"""HTML 案例卡可视化编辑器。

用法（在项目根目录）：
    poetry run python scripts/card_editor.py <卡片文件夹>   # 如 backups/html_cards/xxx/01

浏览器自动打开后：
- 拖动关系图节点/动词标签 → 连线端点实时跟随；
- 单击选中元素（虚线框/橙色高亮）：Delete 删除；关系图节点、面板可拖右下角手柄改尺寸；
- 单击连线选中 → Delete 删线；拖两端橙色圆点手动调整连线走向；
- 双击任意文字直接编辑；Ctrl+Z 撤销；
- 点「保存并出图」→ 自动备份 card.html、写回修改、重新截图 card.png。
"""
from __future__ import annotations

import shutil
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

EDITOR_JS = r"""
<script id="ce-script">
(function () {
  if (window.__cardEditor) return; window.__cardEditor = true;

  var SELECTABLE = ['.dg-node', '.dg-verb', '.dg-panel', '.facts', '.scenes', '.sol-panel',
    '.quote', '.fact', '.scene', '.item', '.chip', '.avatar-box', '.qr-box',
    '.question-band', '.rel-sum', '[data-hit]', 'svg [data-edge]'].join(',');
  var selected = null;
  var undoStack = [];
  var dragged = false;

  var bar = document.createElement('div');
  bar.id = 'ce-bar';
  bar.style.cssText = 'position:fixed;top:12px;right:12px;z-index:99999;background:#1A1A1A;color:#fff;'
    + 'padding:10px 14px;border-radius:12px;font:15px/1.4 sans-serif;display:flex;gap:10px;align-items:center;box-shadow:0 4px 16px rgba(0,0,0,.3)';
  var status = document.createElement('span');
  status.textContent = '拖动=移动 · 单击=选中(可删/改尺寸，连线可拖端点) · 双击=改字';
  status.style.cssText = 'max-width:430px';
  function mkBtn(text, bg, fs) {
    var b = document.createElement('button');
    b.textContent = text;
    b.style.cssText = 'background:' + bg + ';color:#fff;border:none;padding:8px 14px;border-radius:8px;font-size:' + (fs || 15) + 'px;cursor:pointer;font-weight:700';
    return b;
  }
  var undoBtn = mkBtn('撤销', '#4b5563');
  var hint = mkBtn('预览改动', '#4b5563', 13);
  var btn = mkBtn('保存并出图', '#E8590C');
  bar.appendChild(status); bar.appendChild(undoBtn); bar.appendChild(hint); bar.appendChild(btn);
  document.body.appendChild(bar);

  // ---------- 尺寸手柄（跟随选中元素右下角，仅非连线元素） ----------
  var handle = document.createElement('div');
  handle.id = 'ce-handle';
  handle.style.cssText = 'position:fixed;width:18px;height:18px;background:#E8590C;border:2px solid #fff;'
    + 'z-index:99998;cursor:nwse-resize;display:none;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.4)';
  handle.title = '拖动调整尺寸';
  document.body.appendChild(handle);

  // ---------- 连线端点圆点（选中连线时显示） ----------
  var dots = [];
  for (var di = 0; di < 2; di++) {
    var d = document.createElement('div');
    d.className = 'ce-dot';
    d.style.cssText = 'position:fixed;width:20px;height:20px;background:#E8590C;border:3px solid #fff;'
      + 'z-index:99998;cursor:move;display:none;border-radius:50%;box-shadow:0 1px 4px rgba(0,0,0,.4)';
    d.title = '拖动调整连线端点';
    document.body.appendChild(d);
    dots.push(d);
  }

  function activeSvg() {
    return document.querySelector('.dg-canvas svg');
  }
  function isEdge(el) {
    return !!(el && el.getAttribute && el.getAttribute('data-edge') !== null && el.tagName);
  }

  // ---------- 命中线：给每条连线加一条透明加粗镜像，便于点中 ----------
  document.querySelectorAll('svg [data-edge]').forEach(function (edge) {
    edge.style.pointerEvents = 'none';  // 仅编辑期：点击统一落到下方命中带
    var hit = edge.cloneNode(false);
    hit.setAttribute('data-hit', '1');
    hit.setAttribute('stroke', 'rgba(0,0,0,0)');
    hit.setAttribute('stroke-width', '28');
    hit.setAttribute('fill', 'none');
    hit.setAttribute('style', 'pointer-events:stroke;cursor:pointer');
    hit.removeAttribute('marker-end');
    hit.removeAttribute('stroke-dasharray');
    hit.removeAttribute('stroke-width');
    hit.setAttribute('stroke-width', '28');
    edge.parentNode.insertBefore(hit, edge);
  });
  function syncHit(edge) {
    var hit = edge.previousSibling;
    if (!hit || hit.getAttribute !== undefined && hit.getAttribute('data-hit') === null) return;
    ['x1', 'y1', 'x2', 'y2', 'd'].forEach(function (attr) {
      var v = edge.getAttribute(attr);
      if (v !== null) hit.setAttribute(attr, v);
    });
  }

  // ---------- 位置计算 ----------
  function placeHandle() {
    if (!selected || isEdge(selected)) { handle.style.display = 'none'; }
    else {
      var r = selected.getBoundingClientRect();
      handle.style.display = 'block';
      handle.style.left = (r.right - 9) + 'px';
      handle.style.top = (r.bottom - 9) + 'px';
    }
    placeDots();
  }
  function edgeEndpoints(edge) {
    if (edge.tagName.toLowerCase() === 'line') {
      return [{ x: parseFloat(edge.getAttribute('x1')), y: parseFloat(edge.getAttribute('y1')) },
              { x: parseFloat(edge.getAttribute('x2')), y: parseFloat(edge.getAttribute('y2')) }];
    }
    var m = (edge.getAttribute('d') || '').match(/M\s*([\d.\-]+),([\d.\-]+)\s+Q\s*([\d.\-]+),([\d.\-]+)\s+([\d.\-]+),([\d.\-]+)/);
    if (!m) return null;
    return [{ x: parseFloat(m[1]), y: parseFloat(m[2]) }, { x: parseFloat(m[5]), y: parseFloat(m[6]) }];
  }
  function svgToPage(pt) {
    var svg = activeSvg(); if (!svg) return pt;
    var r = svg.getBoundingClientRect();
    var vb = svg.viewBox.baseVal;
    return { x: r.left + pt.x / vb.width * r.width, y: r.top + pt.y / vb.height * r.height };
  }
  function pageToSvg(clientX, clientY) {
    var svg = activeSvg();
    var r = svg.getBoundingClientRect();
    var vb = svg.viewBox.baseVal;
    return { x: (clientX - r.left) / r.width * vb.width, y: (clientY - r.top) / r.height * vb.height };
  }
  function placeDots() {
    if (!selected || !isEdge(selected)) { dots.forEach(function (d) { d.style.display = 'none'; }); return; }
    var pts = edgeEndpoints(selected);
    if (!pts) { dots.forEach(function (d) { d.style.display = 'none'; }); return; }
    pts.forEach(function (pt, i) {
      var p = svgToPage(pt);
      dots[i].style.display = 'block';
      dots[i].style.left = (p.x - 10) + 'px';
      dots[i].style.top = (p.y - 10) + 'px';
    });
  }
  window.addEventListener('scroll', placeHandle, true);
  window.addEventListener('resize', placeHandle);

  // ---------- 选中 / 取消 ----------
  function select(el) {
    deselect();
    selected = el;
    if (isEdge(el)) {
      el.setAttribute('stroke', '#E8590C');
      status.textContent = '已选中连线：Delete 删除 · 拖两端圆点改走向（拖节点会重算该线）';
    } else {
      el.style.outline = '3px dashed #E8590C';
      el.style.outlineOffset = '3px';
      status.textContent = '已选中：Delete 删除 · 拖右下角手柄改尺寸 · 双击改字';
    }
    placeHandle();
  }
  function deselect() {
    if (!selected) return;
    if (isEdge(selected)) selected.setAttribute('stroke', '#1A1A1A');
    else { selected.style.outline = ''; selected.style.outlineOffset = ''; }
    selected = null;
    placeHandle();
  }

  document.addEventListener('click', function (e) {
    if (e.target.closest('#ce-bar') || e.target === handle || e.target.classList.contains('ce-dot')) return;
    if (dragged) { dragged = false; return; }
    var el = e.target.closest(SELECTABLE);
    if (el && el.getAttribute && el.getAttribute('data-hit') !== null && el !== selected) {
      el = el.nextSibling && el.nextSibling.getAttribute && el.nextSibling.getAttribute('data-edge') !== null
        ? el.nextSibling : el;
    }
    if (el) select(el); else deselect();
  });

  // ---------- 删除 + 撤销 ----------
  function isEditingText() {
    var a = document.activeElement;
    return !!(a && a.isContentEditable);
  }
  function deleteSelected() {
    if (!selected) return;
    var el = selected;
    if (isEdge(el)) {
      var hit = el.previousSibling;
      deselect();
      if (hit && hit.getAttribute && hit.getAttribute('data-hit') !== null) {
        undoStack.push({ node: hit, parent: hit.parentNode, next: hit.nextSibling });
        hit.parentNode.removeChild(hit);
      }
      undoStack.push({ node: el, parent: el.parentNode, next: el.nextSibling });
      el.parentNode.removeChild(el);
      status.textContent = '连线已删除（可点撤销）';
      return;
    }
    var record = { node: el, parent: el.parentNode, next: el.nextSibling };
    // 删除关系图节点时，连带删除与它相连的线（含命中线）
    if (el.classList.contains('dg-node')) {
      var name = el.dataset.node;
      document.querySelectorAll('svg [data-edge]').forEach(function (edge) {
        if (edge.dataset.from === name || edge.dataset.to === name) {
          var ehit = edge.previousSibling;
          if (ehit && ehit.parentNode && ehit.getAttribute && ehit.getAttribute('data-hit') !== null) {
            undoStack.push({ node: ehit, parent: ehit.parentNode, next: ehit.nextSibling });
            ehit.parentNode.removeChild(ehit);
          }
          undoStack.push({ node: edge, parent: edge.parentNode, next: edge.nextSibling });
          edge.parentNode.removeChild(edge);
        }
      });
    }
    undoStack.push(record);
    deselect();
    el.parentNode.removeChild(el);
    status.textContent = '已删除（可点撤销）';
  }
  function undo() {
    var rec = undoStack.pop();
    if (!rec) { status.textContent = '没有可撤销的操作'; return; }
    if (rec.next && rec.next.parentNode === rec.parent) rec.parent.insertBefore(rec.node, rec.next);
    else rec.parent.appendChild(rec.node);
    status.textContent = '已撤销';
  }
  document.addEventListener('keydown', function (e) {
    if (isEditingText()) return;
    if ((e.key === 'Delete' || e.key === 'Backspace') && selected) { e.preventDefault(); deleteSelected(); return; }
    if (e.key === 'Escape') { deselect(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(); }
  });
  undoBtn.onclick = undo;

  // ---------- 手柄拖拽：改尺寸（仅非连线） ----------
  handle.addEventListener('pointerdown', function (ev) {
    if (!selected || isEdge(selected)) return;
    ev.preventDefault();
    ev.stopPropagation();
    var el = selected;
    var sx = ev.clientX, sy = ev.clientY;
    var sw = el.offsetWidth, sh = el.offsetHeight;
    handle.setPointerCapture(ev.pointerId);
    function move(e) {
      var w = Math.max(120, Math.round(sw + e.clientX - sx));
      var h = Math.max(80, Math.round(sh + e.clientY - sy));
      el.style.width = w + 'px';
      if (el.classList.contains('dg-node')) el.style.minHeight = h + 'px';
      else el.style.height = h + 'px';
      placeHandle();
    }
    function up() {
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', up);
      if (el.classList.contains('dg-node')) redrawEdges();
    }
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', up);
  });

  // ---------- 端点圆点拖拽：手动改连线走向 ----------
  dots.forEach(function (dot, dotIndex) {
    dot.addEventListener('pointerdown', function (ev) {
      if (!selected || !isEdge(selected)) return;
      ev.preventDefault();
      ev.stopPropagation();
      var edge = selected;
      dot.setPointerCapture(ev.pointerId);
      function move(e) {
        var p = pageToSvg(e.clientX, e.clientY);
        setEdgeEndpoint(edge, dotIndex, p);
        syncHit(edge);
        placeDots();
      }
      function up() {
        dot.removeEventListener('pointermove', move);
        dot.removeEventListener('pointerup', up);
      }
      dot.addEventListener('pointermove', move);
      dot.addEventListener('pointerup', up);
    });
  });
  function setEdgeEndpoint(edge, index, p) {
    var x = Math.round(p.x), y = Math.round(p.y);
    if (edge.tagName.toLowerCase() === 'line') {
      edge.setAttribute(index === 0 ? 'x1' : 'x2', x);
      edge.setAttribute(index === 0 ? 'y1' : 'y2', y);
      return;
    }
    var m = (edge.getAttribute('d') || '').match(/M\s*([\d.\-]+),([\d.\-]+)\s+Q\s*([\d.\-]+),([\d.\-]+)\s+([\d.\-]+),([\d.\-]+)/);
    if (!m) return;
    var pts = [m[1], m[2], m[3], m[4], m[5], m[6]];
    if (index === 0) { pts[0] = x; pts[1] = y; } else { pts[4] = x; pts[5] = y; }
    edge.setAttribute('d', 'M ' + pts[0] + ',' + pts[1] + ' Q ' + pts[2] + ',' + pts[3] + ' ' + pts[4] + ',' + pts[5]);
  }

  // ---------- 连线自动跟随（与 Python 端一致的几何） ----------
  function nodeCenter(el) {
    return { x: el.offsetLeft + el.offsetWidth / 2, y: el.offsetTop + el.offsetHeight / 2 };
  }
  function clipPoint(el, toward) {
    var c = nodeCenter(el);
    var dx = toward.x - c.x, dy = toward.y - c.y;
    var dist = Math.hypot(dx, dy) || 1;
    if (el.dataset.kind === 'person') {
      var r = 172 + 12;
      return { x: c.x + dx / dist * r, y: c.y + dy / dist * r };
    }
    var tx = (el.offsetWidth / 2 + 10) / Math.abs(dx || 0.0001);
    var ty = (el.offsetHeight / 2 + 10) / Math.abs(dy || 0.0001);
    var t = Math.min(tx, ty);
    return { x: c.x + dx * t, y: c.y + dy * t };
  }
  function personCenter() {
    var p = document.querySelector('.dg-node[data-kind="person"]');
    return p ? nodeCenter(p) : { x: 492, y: 600 };
  }
  function redrawEdges() {
    document.querySelectorAll('svg [data-edge]').forEach(function (e) {
      var from = document.querySelector('.dg-node[data-node="' + CSS.escape(e.dataset.from) + '"]');
      var to = document.querySelector('.dg-node[data-node="' + CSS.escape(e.dataset.to) + '"]');
      if (!from || !to) return;
      var p1 = clipPoint(from, nodeCenter(to));
      var p2 = clipPoint(to, nodeCenter(from));
      if (e.tagName.toLowerCase() === 'line') {
        e.setAttribute('x1', p1.x); e.setAttribute('y1', p1.y);
        e.setAttribute('x2', p2.x); e.setAttribute('y2', p2.y);
      } else {
        var mid = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
        var len = Math.hypot(p2.x - p1.x, p2.y - p1.y) || 1;
        var off = Math.min(Math.max(len * 0.22, 24), 90);
        var nx = -(p2.y - p1.y) / len, ny = (p2.x - p1.x) / len;
        var pc = personCenter();
        var d1 = Math.hypot(mid.x + nx * off - pc.x, mid.y + ny * off - pc.y);
        var d2 = Math.hypot(mid.x - nx * off - pc.x, mid.y - ny * off - pc.y);
        var sign = d1 >= d2 ? 1 : -1;
        e.setAttribute('d', 'M ' + p1.x + ',' + p1.y + ' Q ' + (mid.x + nx * off * sign) + ',' + (mid.y + ny * off * sign) + ' ' + p2.x + ',' + p2.y);
      }
      syncHit(e);
    });
  }

  // ---------- 移动（拖动） ----------
  function makeDraggable(el) {
    el.style.cursor = 'move';
    el.addEventListener('pointerdown', function (ev) {
      if (ev.target.isContentEditable) return;
      ev.preventDefault();
      var sx = ev.clientX, sy = ev.clientY;
      var bl = parseFloat(el.style.left) || 0, bt = parseFloat(el.style.top) || 0;
      el.setPointerCapture(ev.pointerId);
      function move(e) {
        if (Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy) > 3) dragged = true;
        el.style.left = (bl + e.clientX - sx) + 'px';
        el.style.top = (bt + e.clientY - sy) + 'px';
        if (el.classList.contains('dg-node')) redrawEdges();
      }
      function up() {
        el.removeEventListener('pointermove', move);
        el.removeEventListener('pointerup', up);
      }
      el.addEventListener('pointermove', move);
      el.addEventListener('pointerup', up);
    });
  }
  document.querySelectorAll('.dg-node,.dg-verb').forEach(makeDraggable);

  // ---------- 双击改字 ----------
  var editableSelectors = ['.dg-name', '.dg-why', '.dg-pname', '.dg-psub', '.dg-verb',
    '.title', '.subtitle', '.chip', '.fact .k', '.fact .v', '.scene', '.question-band',
    '.item .tag', '.item .txt', '.quote .q', '.quote .sig', '.avatar-box .note',
    '.foot-left', '.cta', '.mod-head .zh'];
  document.querySelectorAll(editableSelectors.join(',')).forEach(function (el) {
    el.title = '双击编辑文字';
    el.addEventListener('dblclick', function () {
      el.contentEditable = 'true';
      el.focus();
      el.addEventListener('blur', function once() {
        el.removeAttribute('contenteditable');
        el.removeEventListener('blur', once);
      });
    });
  });

  // ---------- 保存 ----------
  function collectHtml() {
    document.querySelectorAll('[contenteditable]').forEach(function (e) { e.removeAttribute('contenteditable'); });
    deselect();
    var clone = document.documentElement.cloneNode(true);
    var b = clone.querySelector('#ce-bar'); if (b) b.remove();
    var h = clone.querySelector('#ce-handle'); if (h) h.remove();
    var s = clone.querySelector('#ce-script'); if (s) s.remove();
    clone.querySelectorAll('.ce-dot').forEach(function (d) { d.remove(); });
    clone.querySelectorAll('svg [data-edge]').forEach(function (e) { e.style.pointerEvents = ''; });
    clone.querySelectorAll('[data-hit]').forEach(function (x) { x.remove(); });
    return '<!DOCTYPE html>\n' + clone.outerHTML;
  }

  hint.onclick = function () { location.reload(); return false; };
  btn.onclick = function () {
    status.textContent = '正在保存并出图（约20秒）…';
    fetch('/save', { method: 'POST', body: collectHtml() })
      .then(function (r) { return r.text(); })
      .then(function (t) { status.textContent = t; })
      .catch(function (err) { status.textContent = '保存失败：' + err; });
  };
})();
</script>
"""


def make_handler(card_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 安静模式
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            html_path = card_dir / "card.html"
            if self.path.startswith("/assets/"):
                asset = card_dir / self.path.lstrip("/")
                if asset.is_file():
                    ctype = "image/png" if asset.suffix == ".png" else "image/jpeg"
                    self._send(200, asset.read_bytes(), ctype)
                    return
                self._send(404, b"not found", "text/plain")
                return
            if not html_path.is_file():
                self._send(404, "未找到 card.html".encode("utf-8"), "text/plain; charset=utf-8")
                return
            html = html_path.read_text(encoding="utf-8")
            if "</body>" in html:
                html = html.replace("</body>", EDITOR_JS + "</body>", 1)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self):
            if self.path != "/save":
                self._send(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8")
            html_path = card_dir / "card.html"
            png_path = card_dir / "card.png"
            try:
                backup = card_dir / "card.html.bak"
                if html_path.is_file():
                    shutil.copyfile(html_path, backup)
                html_path.write_text(body, encoding="utf-8")
                from app.config import get_settings
                from app.services.html_case_card_service import render_html_to_png
                settings = get_settings()
                width, height = render_html_to_png(
                    html_path, png_path,
                    scale=int(settings.html_card_render_scale),
                    edge_path=settings.html_card_edge_path,
                )
                message = f"已保存并出图：{width}x{height}（原文件备份为 card.html.bak）"
                self._send(200, message.encode("utf-8"), "text/plain; charset=utf-8")
            except Exception as exc:  # noqa: BLE001
                self._send(500, f"出图失败：{exc}".encode("utf-8"), "text/plain; charset=utf-8")

    return Handler


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    card_dir = Path(sys.argv[1]).resolve()
    if not (card_dir / "card.html").is_file():
        raise SystemExit(f"目录里没有 card.html：{card_dir}")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(card_dir))
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(f"visual editor: {url}  ({card_dir})")
    print("浏览器不自动弹出时手动访问上面的地址；改完点「保存并出图」，Ctrl+C 退出。")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
