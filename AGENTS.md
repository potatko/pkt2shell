# pkt2shell — agent notes (Claude Code, Codex, other coding agents)

Editing Cisco Packet Tracer .pka/.pkt files directly. `CLAUDE.md` imports this file.

## Tooling
- `tools/ptcrypto.py` — pure-Python .pka/.pkt codec (Twofish + EAX + zlib), no dependencies.
  Byte-identical to mircodz/pka2xml. `tools/pkt.py` loads it via importlib (works under `python -I`).
- `cpp/` — optional C++ converter derived from pka2xml (`make`, needs Homebrew `cryptopp`). Not used by pkt.py.
- `skill/SKILL.md` — agent skill template (same format for Claude Code and Codex); `install.py` fills in paths
  and installs it to `~/.claude/skills/packet-tracer/` and `~/.agents/skills/packet-tracer/` (Codex).
  Re-run install.py after changing the template.
- Do NOT use upstream `patch.c` or `--forge` (bypass Cisco login / mark activities complete). Never edit the
  answer network, COMPARISONS, scoring or activity password.

## Main tool: `tools/pkt.py` (run with `python3 -I tools/pkt.py ...`)
- `list F.pka` — networks (saved/initial/answer, which one PT loads) and devices.
- `show F.pka DEV [--net N] [--startup]` — IOS config as text (defaults to the network PT loads).
- `ports F.pka DEV` — ports with MAC/IP.
- `links F.pka [--net N]` — cables / topology (device, port <-> device, port).
- `decrypt F.pka OUT.xml` / `encrypt F.xml OUT.pka` — whole-file conversion.
- `instructions F.pka [--html]` — activity instructions (ACTIVITY/INSTRUCTIONS/PAGE, CDATA HTML) as Markdown.
- `set-config F.pka DEV cfg.txt (-o OUT.pka | --in-place) [--nets 0,1] [--startup]` — replace running-config
  (+ startup-config). Same text goes to every listed network.
- `set-host F.pka DEV (-o OUT.pka | --in-place) --ip --mask --gw --dns --ipv6 A/P --ipv6-ll --ipv6-gw --ipv6-dns [--port N]`
  — PC/server static addressing.
- `set-wan F.pka DEV (-o OUT.pka | --in-place) --ip --mask --gw --dns` — Internet (WAN) setup of a home
  wireless router (Linksys WRT300N). `ports` prints the current WAN line for such devices.
- Workflow: `show` → edit full config text → `set-config`. Write a full, consistent config (it replaces,
  not appends). Banner delimiter: write `^C`. Output is verified by an encrypt→decrypt round trip.
- The tool refuses to show or edit the answer network (last of three). Write to the user's original file
  only in the skill's `overwrite` output mode (default chosen via `install.py --output`), and only after
  backing it up to `labs/<name>/original.pka` with `cp -n` (never overwrite an existing backup — a second run
  would otherwise replace the true original with an already-edited file). Writes are atomic (temp file + rename).

## XML facts (verified in PT 9.0.1 on "17.8.2 Skills Integration Challenge", file VERSION 8.0.0.0216)
- Root `PACKETTRACER5_ACTIVITY` holds three `PACKETTRACER5` networks:
  #0 = saved/user network, #1 = initial network, #2 = answer network (used for grading — leave alone).
- With `CLEAN_ACTIVITY=true`, PT loads **network #1** on open; edits to #0 are ignored.
  (Unverified: after the user saves progress, PT probably loads #0 — edit both #0 and #1 to be safe.)
- Routers/switches: `ENGINE/RUNNINGCONFIG/LINE` text **is replayed on open** → config active immediately
  (verified: hostname + interface IP + no shutdown). `ENGINE/STARTUPCONFIG/LINE` is applied on `reload`.
- Structured fields (`SYS_NAME`, port `IP`/`SUBNET`/`DESCRIPTION`) are overwritten from RUNNINGCONFIG on open —
  editing them alone has no effect for IOS devices.
- PCs/servers have no RUNNINGCONFIG; their settings live in structured PORT fields (IP, SUBNET, PORT_GATEWAY,
  PORT_DNS, IPV6_*) plus ENGINE GATEWAY/GATEWAYV6/DNS_CLIENT. Verified in PT 9.0.1: `set-host` edits are honoured.
- Home wireless routers (WRT300N): no IOS config; Internet setup lives in ENGINE `INTERNET_IP_ADDRESS`,
  `INTERNET_SUBNET_MASK`, `DEFAULT_GATEWAY`, `DNS_CLIENT/SERVER_IP` (+ the Internet port = first wired PORT).
  Verified in PT 9.0.1 ("Troubleshooting" activity): editing these is honoured and graded. `set-wan` does not
  touch `INTERNET_CONNECTION_TYPE` (value meaning unclear: static WAN seen with both 0 and 2).
- Unverified: exec-time state that is not in running-config text — RSA keys (`crypto key generate rsa`,
  needed for SSH) and VLANs (stored in ENGINE/VLANS on switches). These may need to be done in the PT CLI.
- Text contains raw control chars (e.g. `^C` = 0x03 in banners) → invalid XML 1.0. Parse only for reading
  (sanitize first); make edits as byte-level string replacements to preserve the file exactly.
- Device lookup: `<NAME translate="true">R1</NAME>` inside `<DEVICE><ENGINE>`; ports identified by `MACADDRESS`.
