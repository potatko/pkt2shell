#!/usr/bin/env python3
"""pkt.py — read and edit Cisco Packet Tracer .pka/.pkt files directly.

Edits are surgical byte-level replacements of single XML elements, so everything
else in the file stays byte-identical (PT stores raw control chars, CDATA, etc.).

Commands (FILE may be .pka/.pkt or an already-decrypted .xml):
  list      FILE                              networks + devices
  show      FILE DEVICE [--net N | --answer] [--startup]   print IOS config
  ports     FILE DEVICE [--net N | --answer]  list ports with MAC / IP
  links     FILE [--net N | --answer]         list cables (topology)
  instructions FILE [--html]                  activity instructions as Markdown
  checklist FILE [--dev NAME]                 graded items with expected values (answer key)
  copy-answer FILE [DEVICE ...] (-o OUT | --in-place) [--all] [--links] [--whole-network] [--nets 0,1]
                                              copy devices / cabling / whole network from the answer
                                              network (sample solution) into networks #0/#1
  set-config FILE DEVICE CFG.txt (-o OUT | --in-place) [--nets 0,1] [--startup]
                                              replace running-config (and startup + flash:config.text
                                              with --startup)
  set-host  FILE DEVICE (-o OUT | --in-place) [--ip A --mask M --gw G --dns D
            --ipv6 ADDR/PREFIX --ipv6-ll LL --ipv6-gw G6 --ipv6-dns D6 --port N] [--nets 0,1]
                                              static addressing for PCs / servers
  set-wan   FILE DEVICE (-o OUT | --in-place) [--ip A --mask M --gw G --dns D] [--nets 0,1]
                                              Internet (WAN) setup of a home wireless router (WRT300N)
  backup    FILE DEST [--force]               copy FILE to DEST unless DEST already exists
  decrypt   FILE.pka OUT.xml
  encrypt   FILE.xml OUT.pka [--base ORIG.pka]   (--base: allow changes only in networks #0/#1)

Config text: one IOS line per line; write banner delimiters as ^C (stored as byte 0x03).
Activity files contain 3 networks: #0 saved, #1 initial (loaded for a fresh activity),
#2 answer network (sample solution). Edits default to #0 and #1; #2 is only read (--answer,
checklist, copy-answer) and never modified, nor are COMPARISONS / scoring / activity settings.
"""
import argparse, importlib.util, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# load the sibling module explicitly (works under `python -I`, which drops the script dir from sys.path)
_spec = importlib.util.spec_from_file_location("ptcrypto", os.path.join(HERE, "ptcrypto.py"))
ptcrypto = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ptcrypto)

# ---------------------------------------------------------------- crypto I/O

def load(path):
    raw = open(path, "rb").read()
    if path.lower().endswith(".xml"):
        return raw
    try:
        return ptcrypto.decrypt_pka(raw)
    except Exception as e:
        sys.exit(f"cannot decrypt {path}: {e}")

def _atomic_write(path, data):
    tmp = path + ".pkt2shell-tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)                          # never leaves a half-written file behind

def save(data, path):
    if path.lower().endswith(".xml"):
        _atomic_write(path, data); return
    enc = ptcrypto.encrypt_pka(data)
    if ptcrypto.decrypt_pka(enc) != data:          # verify round trip before touching OUT
        sys.exit("round-trip verification failed; output not written")
    _atomic_write(path, enc)

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

def links(buf, net):
    """Cables in a network as (dev_a, port_a, dev_b, port_b, cable_type)."""
    refs = {text(buf, child(buf, e, "SAVE_REF_ID")): n for n, _t, _m, e in devices(buf, net)}
    n = child(buf, net, "NETWORK"); ls = child(buf, n, "LINKS") if n else None
    res = []
    for l in children(buf, ls) if ls else []:
        if l.tag != "LINK": continue
        c = child(buf, l, "CABLE")
        if c is None: continue
        kids = children(buf, c)
        ports = [text(buf, k) for k in kids if k.tag == "PORT"]
        fr = text(buf, child(buf, c, "FROM")); to = text(buf, child(buf, c, "TO"))
        res.append((refs.get(fr, fr), ports[0] if ports else "", refs.get(to, to),
                    ports[1] if len(ports) > 1 else "", text(buf, child(buf, l, "TYPE")) or ""))
    return res

def answer_idx(buf):
    """Index of the answer network (the sample solution PT grades against), or None."""
    nets, activity = networks(buf)
    return len(nets) - 1 if activity and len(nets) >= 3 else None

def find_engine(buf, net_idx, name, read_answer=False):
    if net_idx == answer_idx(buf) and not read_answer:
        sys.exit(f"network #{net_idx} is the answer network; read it with --answer, it is never edited")
    nets, _ = networks(buf)
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

def check_against_base(base, buf):
    """Hand-edited XML may differ from BASE only inside networks #0 and #1 (saved, initial).
    Everything else — answer network, ACTIVITY (comparisons, scoring, password) — must be byte-identical."""
    bn, bact = networks(base); nn, nact = networks(buf)
    if (bact, len(bn)) != (nact, len(nn)):
        sys.exit("refusing: network structure differs from --base")
    editable = range(len(nn) - 1) if nact and len(nn) >= 3 else range(len(nn))
    def outside(b, nets):
        parts, pos = [], 0
        for i in editable:
            parts.append(b[pos:nets[i].os]); pos = nets[i].oe
        parts.append(b[pos:])
        return parts
    if outside(base, bn) != outside(buf, nn):
        sys.exit("refusing: edits outside networks #0/#1 (answer network or activity settings changed); "
                 "output not written")
    changed = [i for i in editable if base[bn[i].os:bn[i].oe] != buf[nn[i].os:nn[i].oe]]
    names = []
    for i in changed:
        old = {n: base[e.os:e.oe] for n, _t, _m, e in devices(base, bn[i])}
        names += [n for n, _t, _m, e in devices(buf, nn[i]) if old.get(n) != buf[e.os:e.oe]]
    print(f"check ok: changed network(s) {changed or 'none'}; devices: {', '.join(sorted(set(names))) or 'none'}")

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

def flash_config(buf, e):
    """CONFIG element of flash:config.text (switch startup config kept in FILE_MANAGER), if any."""
    fm = child(buf, e, "FILE_MANAGER")
    stack = [fm] if fm is not None else []
    while stack:
        el = stack.pop()
        for c in children(buf, el):
            if c.tag == "FILE" and text(buf, child(buf, c, "NAME")) == "config.text":
                fc = child(buf, c, "FILE_CONTENT")
                cfg = child(buf, fc, "CONFIG") if fc is not None else None
                if cfg is not None:
                    return cfg
            stack.append(c)
    return None

def set_config(buf, net_idx, name, lines, which):
    e = find_engine(buf, net_idx, name)
    el = child(buf, e, which)
    if el is None:
        sys.exit(f"{name} in network #{net_idx} has no {which} (not an IOS device?)")
    buf = splice(buf, el.os, el.oe, build_cfg(buf, el, lines))
    if which == "STARTUPCONFIG":                 # keep flash:config.text in sync with startup-config
        fc = flash_config(buf, find_engine(buf, net_idx, name))
        if fc is not None:
            buf = splice(buf, fc.os, fc.oe, build_cfg(buf, fc, lines))
    return buf

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

# ---------------------------------------------------------------- home wireless router (Linksys) WAN

WAN_FIELDS = ("INTERNET_CONNECTION_TYPE", "INTERNET_IP_ADDRESS", "INTERNET_SUBNET_MASK", "DEFAULT_GATEWAY")

def wan_info(buf, e):
    """Internet (WAN) settings of a home wireless router, or None for other devices."""
    if child(buf, e, "INTERNET_IP_ADDRESS") is None:
        return None
    info = {f: text(buf, child(buf, e, f)) or "" for f in WAN_FIELDS}
    dc = child(buf, e, "DNS_CLIENT")
    info["DNS"] = text(buf, child(buf, dc, "SERVER_IP")) or "" if dc is not None else ""
    return info

def set_wan(buf, net_idx, name, a):
    eng = lambda: find_engine(buf, net_idx, name)
    if wan_info(buf, eng()) is None:
        sys.exit(f"{name} has no Internet (WAN) settings (not a home wireless router such as WRT300N?)")
    def wan_port():                              # the Internet port is the first wired port
        ps = host_ports(buf, eng())
        return ps[0] if ps else None
    if a.ip is not None:
        buf = set_leaf(buf, eng(), "INTERNET_IP_ADDRESS", a.ip)
        if wan_port() is not None: buf = set_leaf(buf, wan_port(), "IP", a.ip)
    if a.mask is not None:
        buf = set_leaf(buf, eng(), "INTERNET_SUBNET_MASK", a.mask)
        if wan_port() is not None: buf = set_leaf(buf, wan_port(), "SUBNET", a.mask)
    if a.gw is not None:
        buf = set_leaf(buf, eng(), "DEFAULT_GATEWAY", a.gw)
    if a.dns is not None:
        dc = child(buf, eng(), "DNS_CLIENT")
        if dc is None or child(buf, dc, "SERVER_IP") is None:
            sys.exit(f"{name}: no DNS_CLIENT/SERVER_IP field")
        buf = set_leaf(buf, dc, "SERVER_IP", a.dns)
    return buf

# ---------------------------------------------------------------- answer key (read-only) and copying from it

def checklist(buf):
    """Graded items: checked leaves (checkType="2") of the activity's COMPARISONS tree,
    as (path, expected value, points, component). Paths start below the root "Network" node."""
    cmp_ = child(buf, root_el(buf), "COMPARISONS")
    out = []
    def walk(el, path):
        for n in children(buf, el):
            if n.tag != "NODE": continue
            nm = child(buf, n, "NAME")
            if nm is None: continue
            p = path + [text(buf, nm)]
            if any(c.tag == "NODE" for c in children(buf, n)):
                walk(n, p); continue
            ct = re.search(rb'checkType="(\d+)"', nm.attrs)
            if ct and ct.group(1) == b"2":
                v = re.search(rb'nodeValue="([^"]*)"', nm.attrs)
                out.append((p[1:] if p[0] == "Network" else p,
                            unescape(v.group(1)).decode("utf-8", "replace") if v else "",
                            text(buf, child(buf, n, "POINTS")) or "", text(buf, child(buf, n, "COMPONENTS")) or ""))
    if cmp_ is not None:
        walk(cmp_, [])
    return out

def _norm(s):
    return re.sub(r"[\s_\-]+", "", (s or "").lower())

def match_devices(buf, src, dst):
    """Pair devices of network `src` (answer) with `dst`: exact name, then name ignoring case/spaces,
    then the only unpaired device of the same type+model on both sides. Returns {src_name: dst_name}."""
    s, d = devices(buf, src), devices(buf, dst)
    pairs, used = {}, set()
    for key in (lambda x: x, _norm):
        for n, *_ in s:
            if n in pairs: continue
            c = [x for x, *_ in d if x not in used and key(x) == key(n)]
            if len(c) == 1:
                pairs[n] = c[0]; used.add(c[0])
    for n, t, m, _e in s:
        if n in pairs: continue
        cs = [x for x, t2, m2, _ in s if x not in pairs and (t2, m2) == (t, m)]
        cd = [x for x, t2, m2, _ in d if x not in used and (t2, m2) == (t, m)]
        if len(cs) == 1 and len(cd) == 1:
            pairs[n] = cd[0]; used.add(cd[0])
    return pairs

REF = re.compile(rb"save-ref-id:[0-9]+")

def _refs(buf, net):
    return {n: text(buf, child(buf, e, "SAVE_REF_ID")) for n, _t, _m, e in devices(buf, net)}

def translate_refs(blob, rmap):
    """Rewrite answer-network device references to the target network's; return (blob, unmapped refs)."""
    missing = set()
    def sub(m):
        r = m.group().decode()
        if r in rmap: return rmap[r].encode()
        missing.add(r); return m.group()
    return REF.sub(sub, blob), missing

def _sync_startup(buf, n, ref):
    """Make an IOS device's startup-config (and flash:config.text) equal to its running-config.
    The answer network's startup-config can be an unrelated leftover (seen: an OSPF template), which
    would break the device on `reload`; grading uses the running state."""
    def eng():
        nets, _ = networks(buf)
        return next(e for _x, _t, _m, e in devices(buf, nets[n]) if text(buf, child(buf, e, "SAVE_REF_ID")) == ref)
    run, st = child(buf, eng(), "RUNNINGCONFIG"), child(buf, eng(), "STARTUPCONFIG")
    if run is None or st is None:
        return buf
    lines = cfg_lines(buf, run)
    if cfg_lines(buf, st) != lines:
        buf = splice(buf, st.os, st.oe, build_cfg(buf, st, lines))
    fc = flash_config(buf, eng())
    if fc is not None and cfg_lines(buf, fc) != lines:
        buf = splice(buf, fc.os, fc.oe, build_cfg(buf, fc, lines))
    return buf

def copy_answer(buf, n, want, do_links):
    """Copy device ENGINEs (and optionally the cabling) of the answer network into network #n.
    Each device keeps its own SAVE_REF_ID and WORKSPACE (position); references between devices are
    translated. The answer network itself is only read."""
    ai = answer_idx(buf)
    nets, _ = networks(buf)
    pairs = match_devices(buf, nets[ai], nets[n])
    sref, dref = _refs(buf, nets[ai]), _refs(buf, nets[n])
    rmap = {sref[a]: dref[b] for a, b in pairs.items() if sref.get(a) and dref.get(b)}
    inv = {b: a for a, b in pairs.items()}
    for a, b in pairs.items():
        if a != b: print(f"  #{n}: {b!r} <- answer {a!r} (renamed)")
    names = sorted(inv) if want == "all" else want
    for name in names:
        src_name = inv.get(name) or (name if name in pairs else None)
        if src_name is None:
            sys.exit(f"{name!r}: no counterpart in the answer network (network #{n} devices: "
                     f"{', '.join(sorted(dref))}; answer: {', '.join(sorted(sref))}). "
                     f"Use --whole-network if the activity adds or replaces devices.")
        dst_name = pairs[src_name]
        nets, _ = networks(buf)
        se = next(e for x, _t, _m, e in devices(buf, nets[ai]) if x == src_name)
        dd = next((x, t, m, e) for x, t, m, e in devices(buf, nets[n]) if text(buf, child(buf, e, "SAVE_REF_ID")) == dref[dst_name])
        st = next((t, m) for x, t, m, _e in devices(buf, nets[ai]) if x == src_name)
        if st != (dd[1], dd[2]):
            msg = (f"{dst_name!r} is {dd[1]} {dd[2]} but the answer has {st[0]} {st[1]} — the activity replaces "
                   f"the device; use --whole-network or swap it in Packet Tracer")
            if want != "all": sys.exit(msg)
            print(f"  #{n}: SKIPPED {msg}"); continue
        de = dd[3]
        blob, miss = translate_refs(buf[se.os:se.oe], rmap)
        if miss:
            print(f"  warning: {dst_name}: references to answer-only objects kept as is: {', '.join(sorted(miss))}")
        new = _sync_startup(splice(buf, de.os, de.oe, blob), n, dref[dst_name])
        if new == buf:
            print(f"  #{n}: {dst_name}: already identical"); continue
        buf = new
        print(f"  #{n}: {dst_name}: copied from answer {src_name!r}")
    if do_links:
        nets, _ = networks(buf)
        sl = child(buf, child(buf, nets[ai], "NETWORK"), "LINKS")
        dl = child(buf, child(buf, nets[n], "NETWORK"), "LINKS")
        if sl is None or dl is None:
            sys.exit("no LINKS element in one of the networks")
        blob, miss = translate_refs(buf[sl.os:sl.oe], rmap)
        if miss:
            sys.exit(f"answer cabling connects devices with no counterpart in network #{n}; use --whole-network")
        if blob == buf[dl.os:dl.oe]:
            print(f"  #{n}: links already identical")
        else:
            buf = splice(buf, dl.os, dl.oe, blob)
            print(f"  #{n}: links copied ({len(links(buf, networks(buf)[0][n]))} cables)")
    return buf

def copy_whole_network(buf, n):
    ai = answer_idx(buf)
    nets, _ = networks(buf)
    return splice(buf, nets[n].os, nets[n].oe, buf[nets[ai].os:nets[ai].oe])

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

def _out_args(p):
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("-o", "--out", help="write the result to OUT (may equal FILE)")
    g.add_argument("--in-place", action="store_true", help="overwrite FILE")

def _net_args(p):
    g = p.add_mutually_exclusive_group()
    g.add_argument("--net", type=int)
    g.add_argument("--answer", action="store_true", help="read the answer network (sample solution)")

def pick_net(buf, a):
    if getattr(a, "answer", False):
        ai = answer_idx(buf)
        if ai is None: sys.exit("no answer network (not an activity file)")
        return ai
    return loaded_net(buf) if a.net is None else a.net

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("list"); p.add_argument("file")
    p = sp.add_parser("show"); p.add_argument("file"); p.add_argument("device")
    _net_args(p); p.add_argument("--startup", action="store_true")
    p = sp.add_parser("ports"); p.add_argument("file"); p.add_argument("device"); _net_args(p)
    p = sp.add_parser("set-config"); p.add_argument("file"); p.add_argument("device"); p.add_argument("cfg")
    _out_args(p); p.add_argument("--nets"); p.add_argument("--startup", action="store_true")
    p = sp.add_parser("set-host"); p.add_argument("file"); p.add_argument("device")
    _out_args(p); p.add_argument("--nets"); p.add_argument("--port", type=int, default=0)
    for f in ("ip", "mask", "gw", "dns", "ipv6", "ipv6-ll", "ipv6-gw", "ipv6-dns"):
        p.add_argument("--" + f)
    p = sp.add_parser("set-wan"); p.add_argument("file"); p.add_argument("device")
    _out_args(p); p.add_argument("--nets")
    for f in ("ip", "mask", "gw", "dns"):
        p.add_argument("--" + f)
    p = sp.add_parser("instructions"); p.add_argument("file"); p.add_argument("--html", action="store_true")
    p = sp.add_parser("links"); p.add_argument("file"); _net_args(p)
    p = sp.add_parser("checklist"); p.add_argument("file"); p.add_argument("--dev", help="only this device")
    p = sp.add_parser("copy-answer"); p.add_argument("file"); p.add_argument("devices", nargs="*")
    _out_args(p); p.add_argument("--nets")
    p.add_argument("--all", action="store_true", help="every device that has a counterpart in the answer")
    p.add_argument("--links", action="store_true", help="also copy the cabling")
    p.add_argument("--whole-network", action="store_true",
                   help="replace networks #0/#1 entirely with the answer network (last resort)")
    p = sp.add_parser("decrypt"); p.add_argument("file"); p.add_argument("out")
    p = sp.add_parser("encrypt"); p.add_argument("file"); p.add_argument("out")
    p.add_argument("--base", help="original .pka/.xml; refuse unless only networks #0/#1 differ from it")
    p = sp.add_parser("backup"); p.add_argument("file"); p.add_argument("dest")
    p.add_argument("--force", action="store_true", help="replace DEST if it exists")
    a = ap.parse_args()

    if a.cmd == "backup":                          # never replaces an existing backup
        if os.path.exists(a.dest) and not a.force:
            print(f"backup exists, kept: {a.dest}"); return
        os.makedirs(os.path.dirname(os.path.abspath(a.dest)), exist_ok=True)
        _atomic_write(a.dest, open(a.file, "rb").read()); print(f"backup written: {a.dest}"); return
    if a.cmd == "decrypt":
        open(a.out, "wb").write(load(a.file)); return
    if a.cmd == "encrypt":
        buf = open(a.file, "rb").read()
        if a.base:
            check_against_base(load(a.base), buf)
        save(buf, a.out); print(f"encrypted -> {a.out}"); return

    if getattr(a, "in_place", False):
        a.out = a.file
    buf = load(a.file)

    if a.cmd == "instructions":
        pages = instructions_html(buf)
        if not pages: sys.exit("no activity instructions in this file")
        print("\n\n---\n\n".join(pages if a.html else [html_to_md(h) for h in pages])); return

    if a.cmd == "links":
        net = pick_net(buf, a)
        nets, _ = networks(buf)
        if net == answer_idx(buf) and not a.answer:
            sys.exit(f"network #{net} is the answer network; read it with --answer")
        for fa, pa, fb, pb, t in links(buf, nets[net]):
            print(f"{fa:24} {pa:24} <-> {fb:24} {pb:24} {t}")
        return

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
        e = find_engine(buf, pick_net(buf, a), a.device, read_answer=a.answer)
        el = child(buf, e, "STARTUPCONFIG" if a.startup else "RUNNINGCONFIG")
        if el is None: sys.exit(f"{a.device} has no IOS config")
        print("\n".join(cfg_lines(buf, el))); return

    if a.cmd == "ports":
        e = find_engine(buf, pick_net(buf, a), a.device, read_answer=a.answer)
        for i, p in enumerate(descendants(buf, e, "PORT", stop=("PORT",))):
            g = lambda t: text(buf, child(buf, p, t)) or ""
            dns = f" dns={g('PORT_DNS')}" if child(buf, p, "PORT_DNS") is not None else ""
            print(f"  [{i}] {g('TYPE'):26} mac={g('MACADDRESS'):15} ip={g('IP')}/{g('SUBNET')} gw={g('PORT_GATEWAY')}{dns} up={g('POWER')}")
        dc = child(buf, e, "DNS_CLIENT")
        if dc is not None and wan_info(buf, e) is None and child(buf, dc, "SERVER_IP") is not None:
            print(f"  DNS client: server={text(buf, child(buf, dc, 'SERVER_IP')) or '(none)'}")
        w = wan_info(buf, e)
        if w is not None:
            print(f"  WAN (Internet setup): ip={w['INTERNET_IP_ADDRESS']}/{w['INTERNET_SUBNET_MASK']} "
                  f"gw={w['DEFAULT_GATEWAY']} dns={w['DNS']} conn_type={w['INTERNET_CONNECTION_TYPE']}"
                  f"  (edit with set-wan)")
        return

    if a.cmd == "checklist":
        items = checklist(buf)
        if not items: sys.exit("no graded items (not an activity file, or nothing is checked)")
        groups = {}
        for path, val, pts, comp in items:
            groups.setdefault(path[0], []).append((path[1:], val, pts, comp))
        total = 0
        for g, rows in groups.items():
            if a.dev and g != a.dev: continue
            pts = sum(int(p) for _p, _v, p, _c in rows if p.isdigit()); total += pts
            print(f"{g}  ({len(rows)} items, {pts} pts)")
            for path, val, p, comp in rows:
                print(f"  {' > '.join(path) or '(self)'} = {val!r}   [{p} pt, {comp}]")
        if not a.dev: print(f"total: {len(items)} items, {total} pts")
        return

    if a.cmd == "copy-answer":
        if answer_idx(buf) is None: sys.exit("no answer network (not an activity file)")
        if not (a.devices or a.all or a.links or a.whole_network):
            sys.exit("nothing to copy: name devices, or use --all / --links / --whole-network")
        for n in editable_nets(buf, a.nets):
            if a.whole_network:
                buf = copy_whole_network(buf, n); print(f"  #{n}: replaced with the answer network")
            else:
                buf = copy_answer(buf, n, "all" if a.all else a.devices, a.links)
        save(buf, a.out); print(f"answer copied -> {a.out}"); return

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

    if a.cmd == "set-wan":
        for n in editable_nets(buf, a.nets):
            buf = set_wan(buf, n, a.device, a)
        save(buf, a.out); print(f"{a.device}: WAN settings written -> {a.out}"); return

if __name__ == "__main__":
    main()
