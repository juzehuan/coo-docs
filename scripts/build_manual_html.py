#!/usr/bin/env python3
"""把《用户操作手册》从 Markdown 生成为站点上的静态 HTML 页面。

    python3 scripts/build_manual_html.py

输入  docs/用户操作手册.md
输出  frontend/public/manual.html   （vite 会把 public/ 原样拷进 dist/，
                                      因此重新 build frontend 后即可通过
                                      https://站点/manual 访问）

**手册内容改了就要重跑本脚本并重新 build frontend**，否则站点上还是旧版本。

为什么自己写转换而不用 markdown 库:本仓库的运行环境没有 markdown/pandoc,
而给一份交付文档引入 pip/npm 依赖不划算——客户 IT 拿到仓库要能直接跑。
因此这里只实现本手册**实际用到的** Markdown 子集(标题、段落、分隔线、
有序/无序列表含缩进嵌套、GFM 表格、围栏代码块、引用块,以及行内的
粗体/代码/链接)。用到子集之外的语法时,请在这里补,而不要在手册里绕开。
"""
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "用户操作手册.md")
OUT = os.path.join(ROOT, "frontend", "public", "manual.html")


# ---------------------------------------------------------------- 行内元素

def inline(text: str) -> str:
    """行内标记 → HTML。先转义再替换,避免手册里的尖括号被当成标签。

    `代码` 用占位符抠出来后再放回:否则代码里的 ** 或 [] 会被后续规则误伤
    (手册里确实有 `**`、`[:64]` 这类内容)。
    """
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append(html.escape(m.group(1), quote=False))
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", text)
    return text


# ---------------------------------------------------------------- 标题锚点

def slug(title: str, seq: int) -> str:
    """尽量生成稳定可读的锚点:「6.3 COO 终审人」→ s-6-3、「附录 B · …」→ s-appendix-b。

    锚点会出现在用户收藏/互相转发的链接里,用序号而非中文哈希,改标题文字时不会失效。
    """
    m = re.match(r"^(\d+(?:\.\d+)*)", title)
    if m:
        return "s-" + m.group(1).replace(".", "-")
    m = re.match(r"^附录\s*([A-Z])", title)
    if m:
        return "s-appendix-" + m.group(1).lower()
    return f"s-{seq}"


# ---------------------------------------------------------------- 块级解析

def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def render(md: str):
    lines = md.split("\n")
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []   # (level, text, anchor)
    i, seq = 0, 0
    # 列表状态栈:(缩进宽度, 标签)。手册用 2 空格缩进表示嵌套。
    stack: list[tuple[int, str]] = []

    def close_lists(to_indent: int = -1) -> None:
        while stack and stack[-1][0] > to_indent:
            out.append(f"</{stack.pop()[1]}>")

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        # 围栏代码块
        if stripped.startswith("```"):
            close_lists()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf), quote=False) + "</code></pre>")
            continue

        # 空行:结束段落,但不结束列表(列表项之间允许空行)
        if not stripped:
            i += 1
            continue

        # 分隔线
        if re.fullmatch(r"-{3,}", stripped):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            close_lists()
            level, title = len(m.group(1)), m.group(2).strip()
            seq += 1
            anchor = slug(title, seq)
            if level in (2, 3):
                toc.append((level, title, anchor))
            out.append(f'<h{level} id="{anchor}">{inline(title)}'
                       f'<a class="anchor" href="#{anchor}" aria-label="链接到本节">#</a></h{level}>')
            i += 1
            continue

        indent = len(line) - len(line.lstrip())

        # 表格(GFM):当前行含 | 且下一行是分隔行。手册里有缩进在列表项内的表格。
        if "|" in stripped and i + 1 < len(lines) and \
                re.fullmatch(r"\|?[\s:|-]*-[\s:|-]*\|?", lines[i + 1].strip()) and "|" in lines[i + 1]:
            header = split_row(stripped)
            aligns = []
            for cell in split_row(lines[i + 1]):
                if cell.startswith(":") and cell.endswith(":"):
                    aligns.append("center")
                elif cell.endswith(":"):
                    aligns.append("right")
                else:
                    aligns.append("")
            i += 2
            body = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                body.append(split_row(lines[i]))
                i += 1

            def cells(row, tag):
                res = []
                for n, c in enumerate(row):
                    a = aligns[n] if n < len(aligns) else ""
                    style = f' style="text-align:{a}"' if a else ""
                    res.append(f"<{tag}{style}>{inline(c)}</{tag}>")
                return "".join(res)

            tbl = ['<div class="table-wrap"><table><thead><tr>' + cells(header, "th") + "</tr></thead><tbody>"]
            for row in body:
                tbl.append("<tr>" + cells(row, "td") + "</tr>")
            tbl.append("</tbody></table></div>")
            html_tbl = "".join(tbl)
            if indent == 0 or not stack:
                close_lists()
                out.append(html_tbl)
            else:
                # 缩进的表格属于上一个列表项。直接 append 会让 <div> 成为 <ul> 的
                # 直接子元素(非法 HTML,浏览器可能把它挪到列表外),因此把它并进
                # 上一个 <li>:重开该 li 再闭合。
                if out and out[-1].endswith("</li>"):
                    out[-1] = out[-1][: -len("</li>")] + html_tbl + "</li>"
                else:
                    out.append(f"<li>{html_tbl}</li>")
            continue

        # 引用块(可含多行,行内可再有列表符号,按普通文本处理)
        if stripped.startswith(">"):
            close_lists()
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            # 引用块内部按段落切分,空行分段
            paras, cur = [], []
            for b in buf:
                if b.strip():
                    cur.append(b.strip())
                elif cur:
                    paras.append(cur)
                    cur = []
            if cur:
                paras.append(cur)
            inner = "".join(f"<p>{inline(' '.join(p))}</p>" for p in paras)
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # 列表项
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            ind = len(m.group(1))
            tag = "ul" if m.group(2) in "-*" else "ol"
            while stack and stack[-1][0] > ind:
                out.append(f"</{stack.pop()[1]}>")
            if not stack or stack[-1][0] < ind:
                stack.append((ind, tag))
                out.append(f"<{tag}>")
            elif stack[-1][1] != tag:            # 同级但类型变了
                out.append(f"</{stack.pop()[1]}>")
                stack.append((ind, tag))
                out.append(f"<{tag}>")
            text = m.group(3)
            # 续行:比本项缩进更深、且不是新列表项/表格/围栏的行
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip() or "|" in nxt or nxt.strip().startswith("```"):
                    break
                nind = len(nxt) - len(nxt.lstrip())
                if nind <= ind or re.match(r"^\s*([-*]|\d+\.)\s+", nxt):
                    break
                text += " " + nxt.strip()
                i += 1
            out.append(f"<li>{inline(text)}</li>")
            continue

        # 普通段落(允许软换行续行)
        close_lists()
        buf = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^\s*(#{1,6}\s|[-*]\s|\d+\.\s|>|```|-{3,}$)", lines[i]) and "|" not in lines[i]:
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")

    close_lists()
    return "\n".join(out), toc


# ---------------------------------------------------------------- 页面模板

CSS = """
:root{
  --ink:#16263f; --ink-deep:#101d31; --ink-2:#2a3d5c;
  --gold:#a8833c; --gold-2:#c9b06a; --gold-soft:#f4efe4;
  --paper:#f5f2ea; --card:#fffdf7;
  --text:#232a33; --text-sub:#75705f; --text-faint:#a49e8c;
  --line:#dcd4c3; --line-soft:#e8e1d3;
  --green:#3f7d5c; --amber:#b97a1e; --red:#b04a3a;
  --serif:'Noto Serif SC','Source Han Serif SC','Songti SC','STSong','SimSun',serif;
  --sans:'Noto Sans SC','PingFang SC','Hiragino Sans GB','Microsoft YaHei','Helvetica Neue',Arial,sans-serif;
  --sidebar:280px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{
  margin:0;font-family:var(--sans);color:var(--text);background-color:var(--paper);
  background-image:radial-gradient(circle at 20% 10%,rgba(168,131,60,.035) 0,transparent 42%),
                   radial-gradient(circle at 85% 88%,rgba(22,38,63,.03) 0,transparent 40%);
  background-attachment:fixed;-webkit-font-smoothing:antialiased;line-height:1.75;font-size:15px;
}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:rgba(168,131,60,.35);border-radius:8px;border:2px solid transparent;background-clip:content-box}
::-webkit-scrollbar-track{background:transparent}

/* ---- 顶栏 ---- */
.topbar{
  position:sticky;top:0;z-index:30;height:56px;display:flex;align-items:center;gap:14px;
  padding:0 20px;background:var(--ink);color:#f5f1e4;box-shadow:0 2px 10px rgba(22,38,63,.18);
}
.topbar .brand{font-family:var(--serif);font-size:17px;font-weight:600;letter-spacing:.5px;color:#f7e9c9;white-space:nowrap}
.topbar .sub{font-size:12.5px;color:rgba(244,240,228,.6);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.topbar .spacer{flex:1}
.topbar a.btn,.topbar button.btn{
  font:inherit;font-size:13px;line-height:1;cursor:pointer;text-decoration:none;white-space:nowrap;
  color:#f5f1e4;background:rgba(255,255,255,.08);border:1px solid rgba(247,233,201,.28);
  padding:7px 13px;border-radius:6px;transition:background .15s,border-color .15s;
}
.topbar a.btn:hover,.topbar button.btn:hover{background:rgba(255,255,255,.16);border-color:var(--gold-2)}
#menuBtn{display:none}

/* ---- 布局 ---- */
.wrap{display:flex;align-items:flex-start;max-width:1400px;margin:0 auto}
.sidebar{
  position:sticky;top:56px;flex:0 0 var(--sidebar);width:var(--sidebar);
  height:calc(100vh - 56px);overflow-y:auto;padding:18px 10px 40px 20px;
}
.tocfilter{
  width:100%;font:inherit;font-size:13px;padding:7px 10px;margin-bottom:12px;
  border:1px solid var(--line);border-radius:6px;background:#fffef8;color:var(--text);
}
.tocfilter:focus{outline:none;border-color:var(--gold);box-shadow:0 0 0 3px rgba(168,131,60,.14)}
.toc{list-style:none;margin:0;padding:0;font-size:13.5px}
.toc li{margin:0}
.toc a{
  display:block;padding:5px 10px;border-radius:5px;color:var(--text-sub);
  text-decoration:none;border-left:2px solid transparent;transition:background .12s,color .12s;
}
.toc a:hover{background:var(--gold-soft);color:var(--ink)}
.toc a.lv3{padding-left:24px;font-size:12.8px;color:var(--text-faint)}
.toc a.active{background:var(--gold-soft);color:var(--ink);border-left-color:var(--gold);font-weight:600}
.toc a.hidden{display:none}

.content{
  flex:1;min-width:0;background:var(--card);border:1px solid var(--line-soft);
  border-radius:10px;box-shadow:0 1px 2px rgba(34,42,51,.05),0 4px 14px rgba(34,42,51,.05);
  margin:18px 20px 60px;padding:34px 44px 60px;
}

/* ---- 排版 ---- */
.content h1{
  font-family:var(--serif);font-size:29px;line-height:1.4;color:var(--ink);
  margin:0 0 18px;padding-bottom:16px;border-bottom:2px solid var(--gold);
}
.content h2{
  font-family:var(--serif);font-size:22px;color:var(--ink);margin:44px 0 14px;
  padding-bottom:8px;border-bottom:1px solid var(--line);scroll-margin-top:72px;
}
.content h3{font-family:var(--serif);font-size:17.5px;color:var(--ink-2);margin:30px 0 10px;scroll-margin-top:72px}
.content h4{font-size:15.5px;color:var(--ink-2);margin:22px 0 8px}
.content p{margin:11px 0}
.content hr{border:0;border-top:1px solid var(--line);margin:34px 0}
.content a{color:#8a6d2f;text-decoration:none;border-bottom:1px solid rgba(168,131,60,.4)}
.content a:hover{color:var(--gold);border-bottom-color:var(--gold)}
.anchor{
  margin-left:8px;font-size:.62em;color:var(--text-faint);border:0!important;
  opacity:0;transition:opacity .15s;font-family:var(--sans);font-weight:400;
}
h2:hover .anchor,h3:hover .anchor{opacity:1}
.content ul,.content ol{margin:10px 0;padding-left:24px}
.content li{margin:5px 0}
.content li>ul,.content li>ol{margin:5px 0}
.content strong{color:var(--ink);font-weight:600}
.content code{
  font-family:'SFMono-Regular',Menlo,Consolas,'Courier New',monospace;font-size:.875em;
  background:var(--gold-soft);color:#6b5626;padding:1.5px 5px;border-radius:4px;
  border:1px solid rgba(168,131,60,.16);word-break:break-word;
}
.content pre{
  background:var(--ink-deep);color:#e8e2d3;padding:16px 18px;border-radius:8px;
  overflow-x:auto;line-height:1.6;font-size:13px;margin:14px 0;
}
.content pre code{background:none;border:0;color:inherit;padding:0;font-size:inherit;white-space:pre}
.content blockquote{
  margin:16px 0;padding:12px 18px;background:#fbf7ee;
  border-left:3px solid var(--gold);border-radius:0 6px 6px 0;color:#5d5647;
}
.content blockquote p{margin:6px 0}
.content blockquote strong{color:#7a5c1d}

/* ---- 表格 ---- */
.table-wrap{overflow-x:auto;margin:16px 0;border:1px solid var(--line-soft);border-radius:8px}
.content table{border-collapse:collapse;width:100%;font-size:13.5px;background:#fffef9}
.content th,.content td{padding:9px 13px;border-bottom:1px solid var(--line-soft);text-align:left;vertical-align:top}
.content th{background:#f4efe4;color:#6f685a;font-weight:600;white-space:nowrap}
.content tbody tr:last-child td{border-bottom:0}
.content tbody tr:hover{background:#faf6ec}
.content td code{white-space:nowrap}

/* ---- 回到顶部 ---- */
#top{
  position:fixed;right:22px;bottom:26px;width:40px;height:40px;border-radius:50%;
  border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;
  box-shadow:0 2px 6px rgba(34,42,51,.1),0 8px 22px rgba(34,42,51,.1);
  font-size:16px;line-height:1;display:none;z-index:20;
}
#top:hover{border-color:var(--gold);color:var(--gold)}
#backdrop{display:none}

/* ---- 响应式 ---- */
@media (max-width:1000px){
  body{font-size:14.5px}
  #menuBtn{display:inline-block}
  .sidebar{
    position:fixed;top:56px;left:0;z-index:25;background:var(--card);
    border-right:1px solid var(--line);box-shadow:6px 0 22px rgba(34,42,51,.14);
    transform:translateX(-102%);transition:transform .22s ease;
  }
  .sidebar.open{transform:translateX(0)}
  #backdrop.open{display:block;position:fixed;inset:56px 0 0 0;background:rgba(22,38,63,.34);z-index:24}
  .content{margin:12px;padding:22px 18px 44px}
  .content h1{font-size:23px}
  .content h2{font-size:19px}
  .topbar{padding:0 10px;gap:8px}
  .topbar .sub{display:none}
  /* 390px 屏上「☰ 目录 + 品牌 + 打印 + 返回系统」四件套一行放不下,实测右溢出 82px。
     手机上极少从浏览器打印,先去掉打印按钮;品牌允许压缩并省略,保证「返回系统」不被挤出屏幕。 */
  .topbar .print{display:none}
  .topbar .brand{font-size:15px;min-width:0;overflow:hidden;text-overflow:ellipsis}
  .topbar a.btn,.topbar button.btn{padding:6px 10px}
}

/* ---- 打印 ---- */
@media print{
  .topbar,.sidebar,#top,#backdrop,.anchor{display:none!important}
  body{background:#fff;font-size:11pt}
  .content{margin:0;padding:0;border:0;box-shadow:none;background:#fff}
  .content h2{page-break-after:avoid}
  .table-wrap,pre,blockquote{page-break-inside:avoid}
  .content pre{background:#f4f2ec;color:#232a33;border:1px solid #ddd}
}
"""

JS = """
(function(){
  var links=[].slice.call(document.querySelectorAll('.toc a'));
  var heads=links.map(function(a){return document.getElementById(a.getAttribute('href').slice(1));});
  var side=document.getElementById('sidebar'),back=document.getElementById('backdrop');

  function setOpen(v){side.classList.toggle('open',v);back.classList.toggle('open',v);}
  document.getElementById('menuBtn').onclick=function(){setOpen(!side.classList.contains('open'));};
  back.onclick=function(){setOpen(false);};
  // 窄屏点完目录就收起，否则浮层一直盖着正文
  links.forEach(function(a){a.onclick=function(){if(window.innerWidth<=1000)setOpen(false);};});

  // 目录高亮：取最后一个已滚过顶部的标题
  var top=document.getElementById('top'),cur=-1,ticking=false;
  function sync(){
    ticking=false;
    var y=window.scrollY+80,idx=0;
    for(var i=0;i<heads.length;i++){if(heads[i]&&heads[i].offsetTop<=y)idx=i;}
    if(idx!==cur){
      if(links[cur])links[cur].classList.remove('active');
      links[idx].classList.add('active');cur=idx;
      // 目录很长，跟随滚动把当前项带进可视区（仅在它已经跑出视野时）。
      // 这里必须直接改 side.scrollTop，不能用 scrollIntoView：后者会把**所有**
      // 祖先滚动容器（含文档本身）一起滚，于是点目录触发的平滑滚动刚走到一半
      // 就被它拽回来——实测点「6.3」后 scrollY 从 0 冲到 384 又退回 211 停住，
      // 页面看起来像是根本没跳转。
      var r=links[idx].getBoundingClientRect(),s=side.getBoundingClientRect();
      if(r.top<s.top+8||r.bottom>s.bottom-8){
        side.scrollTop+=(r.top-s.top)-(side.clientHeight/2-r.height/2);
      }
    }
    top.style.display=window.scrollY>400?'block':'none';
  }
  window.addEventListener('scroll',function(){if(!ticking){ticking=true;requestAnimationFrame(sync);}},{passive:true});
  sync();
  top.onclick=function(){window.scrollTo({top:0,behavior:'smooth'});};

  // 目录过滤：676 行的手册靠肉眼找章节太慢
  var f=document.getElementById('tocfilter');
  f.oninput=function(){
    var q=f.value.trim().toLowerCase();
    links.forEach(function(a){
      a.classList.toggle('hidden',!!q&&a.textContent.toLowerCase().indexOf(q)<0);
    });
  };
  f.onkeydown=function(e){if(e.key==='Escape'){f.value='';f.oninput();f.blur();}};
})();
"""

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>用户操作手册 · COO 资料收集平台</title>
<style>{css}</style>
</head>
<body>
<div class="topbar">
  <button id="menuBtn" class="btn" type="button">☰ 目录</button>
  <span class="brand">COO 资料收集平台</span>
  <span class="sub">用户操作手册</span>
  <span class="spacer"></span>
  <button class="btn print" type="button" onclick="window.print()">打印 / 存为 PDF</button>
  <a class="btn" href="/">返回系统</a>
</div>
<div id="backdrop"></div>
<div class="wrap">
  <nav class="sidebar" id="sidebar">
    <input class="tocfilter" id="tocfilter" type="search" placeholder="筛选章节…" autocomplete="off">
    <ul class="toc">
{toc}
    </ul>
  </nav>
  <main class="content">
{body}
  </main>
</div>
<button id="top" type="button" title="回到顶部">↑</button>
<script>{js}</script>
</body>
</html>
"""


def main() -> int:
    with open(SRC, encoding="utf-8") as f:
        md = f.read()
    body, toc = render(md)
    toc_html = "\n".join(
        f'      <li><a class="lv{lv}" href="#{a}">{html.escape(t, quote=False)}</a></li>'
        for lv, t, a in toc)
    page = PAGE.format(css=CSS, js=JS, toc=toc_html, body=body)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    # 按字节而非字符计:中文在 UTF-8 下是 3 字节,按 len(str) 报出来的数字会小三成
    kb = os.path.getsize(OUT) / 1024
    print(f"[OK] {SRC}\n  -> {OUT}  ({kb:.1f} KB，目录 {len(toc)} 项)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
