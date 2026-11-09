# pkt2shell

Read and edit Cisco Packet Tracer `.pka` / `.pkt` files from the command line, so that a script
(or an AI assistant such as Claude) can configure a lab directly in the file, without driving the
Packet Tracer GUI.

working on Cisco Packet Tracer 9.0.1

## What it can do

- Decrypt a `.pka`/`.pkt` to XML and encrypt it back (byte-identical round trip).
- List the networks and devices in a file.
- Print a router/switch IOS configuration as plain text.
- Replace a router/switch running-config (and optionally startup-config) with your own text.
  Packet Tracer replays it when the file is opened, so the configuration is live immediately.
- Set static IPv4/IPv6 addressing, gateway and DNS on PCs and servers.
- Extract the activity instructions as Markdown.

Edits are surgical: only the touched XML elements change and the rest of the file stays
byte-for-byte identical. Every written file is verified with an encrypt → decrypt round trip.

The answer network of an activity (the one used for grading) is never shown or modified.

## Build

```bash
brew install cryptopp        # Debian/Ubuntu: sudo apt install libcrypto++-dev zlib1g-dev
make
```

Python 3.8+ with no extra packages is needed for `tools/pkt.py`.

## Usage

```bash
python3 tools/pkt.py list lab.pka
python3 tools/pkt.py instructions lab.pka > instructions.md
python3 tools/pkt.py show lab.pka R1 > r1.txt
# edit r1.txt (full config, it replaces the existing one; write banner delimiters as ^C)
python3 tools/pkt.py set-config lab.pka R1 r1.txt --startup -o lab-done.pka
python3 tools/pkt.py set-host lab-done.pka PC1 --ip 192.168.0.10 --mask 255.255.255.0 \
    --gw 192.168.0.1 --ipv6 2001:db8::10/64 --ipv6-ll fe80::2 --ipv6-gw fe80::1 -o lab-done.pka
python3 tools/pkt.py ports lab-done.pka PC1
```

Low-level conversion:

```bash
tools/pka2xml -d lab.pka lab.xml
tools/pka2xml -e lab.xml lab.pka
```

## How Packet Tracer stores things (findings)

- An activity (`.pka`) contains three networks: `#0` saved progress, `#1` the initial network,
  `#2` the answer network. A fresh activity (`CLEAN_ACTIVITY=true`) opens from `#1`, a saved one
  from `#0`. `pkt.py` writes to both `#0` and `#1`.
- Routers and switches: `ENGINE/RUNNINGCONFIG` is plain IOS text and is replayed when the file is
  opened. `ENGINE/STARTUPCONFIG` is used on `reload`. Structured fields such as `SYS_NAME` or port
  `IP` are overwritten from the running-config, so editing them alone does nothing.
- PCs and servers have no IOS config. Their addressing lives in structured `PORT` fields and in
  `ENGINE/GATEWAY`, `GATEWAYV6` and `DNS_CLIENT`.
- The XML contains raw control characters (e.g. `0x03` banner delimiters), which makes it invalid
  XML 1.0. That is why edits are done at byte level instead of with an XML library.
- Not verified yet: state that is not part of the running-config text, such as RSA keys for SSH
  and switch VLAN databases. These may still need a command in the Packet Tracer CLI.

See [CLAUDE.md](CLAUDE.md) for notes aimed at an AI assistant using this tool.

## Credits and license

`tools/pka2xml.hpp` and `tools/main.cpp` are derived from
[mircodz/pka2xml](https://github.com/mircodz/pka2xml) by Mirco De Zorzi, BSD 2-Clause License
(see [LICENSE.pka2xml](LICENSE.pka2xml)). They were trimmed to file conversion only.

Cisco and Packet Tracer are trademarks of Cisco Systems, Inc. This project is not affiliated with
Cisco. Use it on your own lab files and follow your course's rules.
