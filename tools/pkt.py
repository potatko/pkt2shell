#!/usr/bin/env python3
"""pkt.py — read and edit Cisco Packet Tracer .pka/.pkt files directly.

Edits are surgical byte-level replacements of single XML elements, so everything
else in the file stays byte-identical (PT stores raw control chars, CDATA, etc.).

Commands (FILE may be .pka/.pkt or an already-decrypted .xml):
  list      FILE                              networks + devices
  show      FILE DEVICE [--net N] [--startup] print IOS config
  ports     FILE DEVICE [--net N]             list ports with MAC / IP
  set-config FILE DEVICE CFG.txt -o OUT [--nets 0,1] [--startup]
                                              replace running-config (and startup with --startup)
  set-host  FILE DEVICE -o OUT [--ip A --mask M --gw G --dns D
            --ipv6 ADDR/PREFIX --ipv6-ll LL --ipv6-gw G6 --ipv6-dns D6 --port N] [--nets 0,1]
                                              static addressing for PCs / servers
  decrypt   FILE.pka OUT.xml
  encrypt   FILE.xml OUT.pka

Config text: one IOS line per line; write banner delimiters as ^C (stored as byte 0x03).
Activity files contain 3 networks: #0 saved, #1 initial (loaded for a fresh activity),
#2 answer network. Edits default to #0 and #1; #2 is never modified.
"""
import argparse, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKA2XML = os.path.join(HERE, "pka2xml")

# ---------------------------------------------------------------- crypto I/O

def _run_pka2xml(flag, src, dst):
    r = subprocess.run([PKA2XML, flag, src, dst], capture_output=True)
    if r.returncode != 0:
        sys.exit(f"pka2xml {flag} failed: {r.stderr.decode(errors='replace')}")

def load(path):
    if path.lower().endswith(".xml"):
        return open(path, "rb").read()
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "x.xml")
        _run_pka2xml("-d", path, out)
        return open(out, "rb").read()

def save(data, path):
    if path.lower().endswith(".xml"):
        open(path, "wb").write(data); return
    with tempfile.TemporaryDirectory() as td:
        x = os.path.join(td, "x.xml"); x2 = os.path.join(td, "y.xml"); p = os.path.join(td, "x.pka")
        open(x, "wb").write(data)
        _run_pka2xml("-e", x, p)
        _run_pka2xml("-d", p, x2)          # verify round trip before touching OUT
        if open(x2, "rb").read() != data:
            sys.exit("round-trip verification failed; output not written")
        open(path, "wb").write(open(p, "rb").read())

# ---------------------------------------------------------------- tiny XML span locator

TOKEN = re.compile(rb"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<(/?)([A-Za-z_][\w.\-]*)([^>]*?)(/?)>", re.S)

class El:
    """Element located in the byte buffer: outer [os, oe), inner [is_, ie)."""
    __slots__ = ("tag", "os", "oe", "is_", "ie", "attrs")
    def __init__(self, tag, os_, oe, is_, ie, attrs):
        self.tag, self.os, self.oe, self.is_, self.ie, self.attrs = tag, os_, oe, is_, ie, attrs

def children(buf, parent):
    """Direct child elements of `parent` (an El, or (start, end) range)."""
    start, end = (parent.is_, parent.ie) if isinstance(parent, El) else parent
    out, stack = [], []
    for m in TOKEN.finditer(buf, start, end):
        if m.group(2) is None:
            continue                        # comment / CDATA / PI
        closing, tag, attrs, selfclose = m.group(1), m.group(2), m.group(3), m.group(4)
        if closing:
            os_, tg, at, is_ = stack.pop()
            assert tg == tag, f"mismatched </{tag.decode()}> at {m.start()}"
            if not stack:
                out.append(El(tag.decode(), os_, m.end(), is_, m.start(), at))
        elif selfclose:
            if not stack:
                out.append(El(tag.decode(), m.start(), m.end(), m.end(), m.end(), attrs))
        else:
            stack.append((m.start(), tag, attrs, m.end()))
    return out

def child(buf, parent, tag):
    for c in children(buf, parent):
        if c.tag == tag:
            return c
    return None

def descendants(buf, parent, tag, stop=()):
    res = []
    for c in children(buf, parent):
        if c.tag == tag:
            res.append(c)
        elif c.tag not in stop:
            res.extend(descendants(buf, c, tag, stop))
    return res

ENT = {b"&amp;": b"&", b"&lt;": b"<", b"&gt;": b">", b"&quot;": b'"', b"&apos;": b"'"}
def unescape(b):
    b = re.sub(rb"&#(\d+);", lambda m: bytes([int(m.group(1))]), b)
    for k, v in ENT.items():
        b = b.replace(k, v)
    return b
def escape(b):
    return b.replace(b"&", b"&amp;").replace(b"<", b"&lt;").replace(b">", b"&gt;")

def text(buf, el):
    return unescape(buf[el.is_:el.ie]).decode("utf-8", "replace").strip() if el else None

def indent_of(buf, pos):
    ls = buf.rfind(b"\n", 0, pos) + 1
    return re.match(rb"[ \t]*", buf[ls:pos]).group()

# ---------------------------------------------------------------- document model

def root_el(buf):
    for m in TOKEN.finditer(buf):
        if m.group(2) is not None and not m.group(1):
            end = buf.rindex(b"</" + m.group(2) + b">")
            return El(m.group(2).decode(), m.start(), end + len(m.group(2)) + 3, m.end(), end, m.group(3))
    sys.exit("no root element")

def networks(buf):
    r = root_el(buf)
    if r.tag == "PACKETTRACER5":
        return [r], False
    return [c for c in children(buf, r) if c.tag == "PACKETTRACER5"], True

def devices(buf, net):
    n = child(buf, net, "NETWORK"); ds = child(buf, n, "DEVICES") if n else None
    res = []
    for d in children(buf, ds) if ds else []:
        if d.tag != "DEVICE": continue
        e = child(buf, d, "ENGINE")
        t = child(buf, e, "TYPE")
        model = re.search(rb'model="([^"]*)"', t.attrs) if t is not None else None
        res.append((text(buf, child(buf, e, "NAME")), text(buf, t), model.group(1).decode() if model else "", e))
    return res

def find_engine(buf, net_idx, name):
    nets, activity = networks(buf)
    if activity and len(nets) >= 3 and net_idx == len(nets) - 1:
        sys.exit(f"network #{net_idx} is the answer network; not shown or edited")
    for n, _t, _m, e in devices(buf, nets[net_idx]):
        if n == name:
            return e
    names = sorted(n for n, *_ in devices(buf, nets[net_idx]))
    sys.exit(f"device {name!r} not found in network #{net_idx}. Devices: {', '.join(names)}")

def editable_nets(buf, requested):
    nets, activity = networks(buf)
    if not activity:
        return [0]
    idx = [int(x) for x in requested.split(",")] if requested else [0, 1]
    if any(i >= len(nets) - 1 or i < 0 for i in idx) and len(nets) >= 3:
        sys.exit(f"refusing to edit network(s) {idx}: #{len(nets)-1} is the answer network")
    return idx

def loaded_net(buf):
    nets, activity = networks(buf)
    if not activity:
        return 0
    r = root_el(buf); c = child(buf, r, "CLEAN_ACTIVITY")
    return 1 if (c is not None and text(buf, c) == "true") else 0

def splice(buf, start, end, new):
    return buf[:start] + new + buf[end:]

# ---------------------------------------------------------------- config text

def cfg_lines(buf, cfg_el):
    return [unescape(buf[l.is_:l.ie]).decode("utf-8", "replace").replace("\x03", "^C")
            for l in children(buf, cfg_el) if l.tag == "LINE"]

def build_cfg(buf, el, lines):
    tag = el.tag.encode()
    lines_ = children(buf, el)
    if lines_:
        ind = indent_of(buf, lines_[0].os)
    else:
        ind = indent_of(buf, el.os) + b" "
    close_ind = ind[:-1]
    body = b"".join(b"\n" + ind + b"<LINE>" + escape(l.replace("^C", "\x03").encode()) + b"</LINE>" for l in lines)
    return b"<" + tag + b">" + body + b"\n" + close_ind + b"</" + tag + b">"

def set_config(buf, net_idx, name, lines, which):
    e = find_engine(buf, net_idx, name)
    el = child(buf, e, which)
    if el is None:
        sys.exit(f"{name} in network #{net_idx} has no {which} (not an IOS device?)")
    return splice(buf, el.os, el.oe, build_cfg(buf, el, lines))

# ---------------------------------------------------------------- host addressing

def set_leaf(buf, parent, tag, value):
    el = child(buf, parent, tag)
    if el is None:
        sys.exit(f"field {tag} not found")
    t = tag.encode()
    new = b"<" + t + b"/>" if value == "" else b"<" + t + b">" + escape(value.encode()) + b"</" + t + b">"
    return splice(buf, el.os, el.oe, new)

def host_ports(buf, e):
    return [p for p in descendants(buf, e, "PORT", stop=("PORT",))
            if (text(buf, child(buf, p, "TYPE")) or "").startswith(("eCopper", "eFiber"))]

def set_host(buf, net_idx, name, a):
    # every edit re-resolves spans, since earlier splices shift offsets
    def port():
        ps = host_ports(buf, find_engine(buf, net_idx, name))
        if a.port >= len(ps): sys.exit(f"{name}: no port #{a.port} (has {len(ps)} wired ports)")
        return ps[a.port]
    eng = lambda: find_engine(buf, net_idx, name)
    if a.ip is not None:
        buf = set_leaf(buf, port(), "IP", a.ip)
        buf = set_leaf(buf, port(), "PORT_DHCP_ENABLE", "false")
    if a.mask is not None:
        buf = set_leaf(buf, port(), "SUBNET", a.mask)
    if a.gw is not None:
        buf = set_leaf(buf, port(), "PORT_GATEWAY", a.gw)
        buf = set_leaf(buf, eng(), "GATEWAY", a.gw)
    if a.dns is not None:
        buf = set_leaf(buf, port(), "PORT_DNS", a.dns)
        dc = child(buf, eng(), "DNS_CLIENT")
        if dc is not None and child(buf, dc, "SERVER_IP") is not None:
            buf = set_leaf(buf, dc, "SERVER_IP", a.dns)
    if a.ipv6 is not None or a.ipv6_ll is not None or a.ipv6_gw is not None:
        buf = set_leaf(buf, port(), "IPV6_ENABLED", "true")
    if a.ipv6 is not None:
        p = port(); el = child(buf, p, "IPV6_ADDRESSES")
        ind = indent_of(buf, el.os)
        if a.ipv6 == "":
            new = b"<IPV6_ADDRESSES/>"
        else:
            addr, _, pfx = a.ipv6.partition("/")
            i1, i2 = ind + b" ", ind + b"  "
            new = (b"<IPV6_ADDRESSES>\n" + i1 + b"<IPV6_ADDRESS>\n" +
                   i2 + b"<ADDRESS>" + addr.upper().encode() + b"</ADDRESS>\n" +
                   i2 + b"<PREFIX>" + (pfx or "64").encode() + b"</PREFIX>\n" +
                   i2 + b"<TYPE>0</TYPE>\n" + i1 + b"</IPV6_ADDRESS>\n" + ind + b"</IPV6_ADDRESSES>")
        buf = splice(buf, el.os, el.oe, new)
    if a.ipv6_ll is not None:
        buf = set_leaf(buf, port(), "IPV6_LINK_LOCAL", a.ipv6_ll.upper())
    if a.ipv6_gw is not None:
        buf = set_leaf(buf, port(), "IPV6_PORT_GATEWAY", a.ipv6_gw.upper())
        buf = set_leaf(buf, eng(), "GATEWAYV6", a.ipv6_gw.upper())
    if a.ipv6_dns is not None:
        buf = set_leaf(buf, port(), "IPV6_PORT_DNS", a.ipv6_dns.upper())
        dc = child(buf, eng(), "DNS_CLIENT")
        if dc is not None and child(buf, dc, "SERVER_IPV6") is not None:
            buf = set_leaf(buf, dc, "SERVER_IPV6", a.ipv6_dns.upper())
    return buf

# ---------------------------------------------------------------- activity instructions

def instructions_html(buf):
    r = root_el(buf)
    act = child(buf, r, "ACTIVITY")
    ins = child(buf, act, "INSTRUCTIONS") if act else None
    def content(p):
        b = buf[p.is_:p.ie].strip()
        if b.startswith(b"<![CDATA[") and b.endswith(b"]]>"):
            b = b[9:-3]
        else:
            b = unescape(b)
        return b.decode("utf-8", "replace")
    return [content(p) for p in children(buf, ins) if p.tag == "PAGE"] if ins else []

def html_to_md(h):
    from html.parser import HTMLParser
    class P(HTMLParser):
        BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "li", "br", "table"}
        def __init__(s):
            super().__init__(); s.out = []; s.skip = 0; s.row = None; s.cell = None; s.rows = None
        def w(s, t):
            if s.cell is not None: s.cell.append(t)
            else: s.out.append(t)
        def handle_starttag(s, t, a):
            if t in ("style", "script", "head"): s.skip += 1
            elif t == "table": s.rows = []
            elif t == "tr": s.row = []
            elif t in ("td", "th"): s.cell = []
            elif t in ("h1", "h2", "h3", "h4"): s.w("\n\n" + "#" * int(t[1]) + " ")
            elif t == "li": s.w("\n- ")
            elif t in s.BLOCK: s.w("\n" if s.cell is not None else "\n\n")
        def handle_endtag(s, t):
            if t in ("style", "script", "head"): s.skip -= 1
            elif t in ("td", "th") and s.cell is not None:
                s.row.append(re.sub(r"\s+", " ", "".join(s.cell)).strip()); s.cell = None
            elif t == "tr" and s.row is not None:
                if any(s.row): s.rows.append(s.row)
                s.row = None
            elif t == "table" and s.rows is not None:
                rows, s.rows = s.rows, None
                if rows:
                    n = max(len(x) for x in rows)
                    rows = [x + [""] * (n - len(x)) for x in rows]
                    s.out.append("\n\n" + "\n".join("| " + " | ".join(x) + " |" for x in rows[:1]))
                    s.out.append("\n|" + "---|" * n + "\n")
                    s.out.append("\n".join("| " + " | ".join(x) + " |" for x in rows[1:]) + "\n\n")
        def handle_data(s, d):
            if not s.skip: s.w(d.replace("\xa0", " ").replace("\r", " ").replace("\n", " "))
    p = P(); p.feed(h)
    s = "".join(p.out)
    s = re.sub(r"[ \t]+", " ", s); s = re.sub(r" *\n *", "\n", s)
    # Word list glyphs (Wingdings) come through as "=" / "§" / "o" prefixes
    s = re.sub(r"(?m)^[=§·•] ", "- ", s); s = re.sub(r"(?m)^o ", "  - ", s)
    s = re.sub(r"\n\n(?=(- |  - ))", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() + "\n"

# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("list"); p.add_argument("file")
    p = sp.add_parser("show"); p.add_argument("file"); p.add_argument("device")
    p.add_argument("--net", type=int); p.add_argument("--startup", action="store_true")
    p = sp.add_parser("ports"); p.add_argument("file"); p.add_argument("device"); p.add_argument("--net", type=int)
    p = sp.add_parser("set-config"); p.add_argument("file"); p.add_argument("device"); p.add_argument("cfg")
    p.add_argument("-o", "--out", required=True); p.add_argument("--nets"); p.add_argument("--startup", action="store_true")
    p = sp.add_parser("set-host"); p.add_argument("file"); p.add_argument("device")
    p.add_argument("-o", "--out", required=True); p.add_argument("--nets"); p.add_argument("--port", type=int, default=0)
    for f in ("ip", "mask", "gw", "dns", "ipv6", "ipv6-ll", "ipv6-gw", "ipv6-dns"):
        p.add_argument("--" + f)
    p = sp.add_parser("instructions"); p.add_argument("file"); p.add_argument("--html", action="store_true")
    p = sp.add_parser("decrypt"); p.add_argument("file"); p.add_argument("out")
    p = sp.add_parser("encrypt"); p.add_argument("file"); p.add_argument("out")
    a = ap.parse_args()

    if a.cmd == "decrypt":
        _run_pka2xml("-d", a.file, a.out); return
    if a.cmd == "encrypt":
        _run_pka2xml("-e", a.file, a.out); return

    buf = load(a.file)

    if a.cmd == "instructions":
        pages = instructions_html(buf)
        if not pages: sys.exit("no activity instructions in this file")
        print("\n\n---\n\n".join(pages if a.html else [html_to_md(h) for h in pages])); return

    if a.cmd == "list":
        nets, activity = networks(buf)
        ln = loaded_net(buf)
        for i, n in enumerate(nets):
            role = ("saved", "initial", "answer")[i] if activity and len(nets) == 3 else ""
            mark = "  <- loaded on open" if i == ln else ""
            print(f"network #{i} {role}{mark}")
            for name, t, model, e in devices(buf, n):
                ios = "IOS" if child(buf, e, "RUNNINGCONFIG") is not None else ""
                print(f"   {name:28} {t:12} {model:18} {ios}")
        return

    if a.cmd == "show":
        net = loaded_net(buf) if a.net is None else a.net
        e = find_engine(buf, net, a.device)
        el = child(buf, e, "STARTUPCONFIG" if a.startup else "RUNNINGCONFIG")
        if el is None: sys.exit(f"{a.device} has no IOS config")
        print("\n".join(cfg_lines(buf, el))); return

    if a.cmd == "ports":
        net = loaded_net(buf) if a.net is None else a.net
        e = find_engine(buf, net, a.device)
        for i, p in enumerate(descendants(buf, e, "PORT", stop=("PORT",))):
            g = lambda t: text(buf, child(buf, p, t)) or ""
            print(f"  [{i}] {g('TYPE'):26} mac={g('MACADDRESS'):15} ip={g('IP')}/{g('SUBNET')} gw={g('PORT_GATEWAY')} up={g('POWER')}")
        return

    if a.cmd == "set-config":
        lines = open(a.cfg, encoding="utf-8").read().splitlines()
        for n in editable_nets(buf, a.nets):
            buf = set_config(buf, n, a.device, lines, "RUNNINGCONFIG")
            if a.startup:
                buf = set_config(buf, n, a.device, lines, "STARTUPCONFIG")
        save(buf, a.out); print(f"{a.device}: config written ({len(lines)} lines) -> {a.out}"); return

    if a.cmd == "set-host":
        for n in editable_nets(buf, a.nets):
            buf = set_host(buf, n, a.device, a)
        save(buf, a.out); print(f"{a.device}: addressing written -> {a.out}"); return

if __name__ == "__main__":
    main()
