# pkt2shell

pkt2shell lets a coding agent, such as **Claude Code** or **OpenAI Codex**, read and configure
Cisco Packet Tracer activity files (`.pka`) and network files (`.pkt`) directly, without
operating the Packet Tracer user interface. Given an activity file, the agent reads the
instructions and topology, configures the routers, switches and end devices, and produces a new
file that can be opened and checked in Packet Tracer.

The project consists of:

- a dependency-free Python command-line tool (`tools/pkt.py`) that decrypts, inspects and edits
  Packet Tracer files;
- an agent skill (`skill/SKILL.md`) that defines a safe, repeatable workflow for completing an
  activity;
- an installer (`install.py`) that registers the skill with Claude Code and Codex.

Supported platforms are Windows, macOS and Linux. The tool has been validated with
Cisco Packet Tracer 9.0.1.

---

## Requirements

| Component | Notes |
|---|---|
| Python 3.8 or newer | Windows: install from [python.org](https://www.python.org/downloads/) and enable *Add python.exe to PATH*. |
| Claude Code and/or Codex | Either the desktop application or the command-line interface. |
| Cisco Packet Tracer | Required only to open and verify the resulting file. |
| Git | Optional. The repository can also be downloaded as a ZIP archive. |

No compiler or third-party Python packages are required.

## Installation

```bash
git clone https://github.com/potatko/pkt2shell.git
cd pkt2shell
python3 install.py
```

On Windows, use `py install.py`.

By default, the installer registers the skill for both agents:

| Agent | Skill location |
|---|---|
| Claude Code | `~/.claude/skills/packet-tracer/SKILL.md` |
| Codex | `~/.agents/skills/packet-tracer/SKILL.md` |

Use `--claude` or `--codex` to install for a single agent, and `--uninstall` to remove the skill.
The skill references the repository by its absolute path. If the repository is moved, run the
installer again.

### Output mode

The installer also sets where a completed activity is written:

| Option | Behaviour |
|---|---|
| `--output new` (default) | The result is written to a new file, `<original name> - completed.pka`. The original file is not modified. |
| `--output overwrite` | The original file is backed up to `labs/<activity>/original.pka` in the repository and then overwritten with the result. |

```bash
python3 install.py --output overwrite
```

If `--output` is omitted, the mode of the existing installation is retained. The default can be
overridden for a single request by stating it explicitly, for example *"overwrite the original"* or
*"write the result to a new file"*.

## Usage

1. Start a new Claude Code or Codex session. The working directory does not matter.
2. Ask the agent to complete the activity and give it the file path, for example:

   > Complete the Packet Tracer activity "C:\Users\student\Downloads\11.5.5 Subnet an IPv4 Network.pka"

3. The agent extracts the instructions and topology, presents an addressing and configuration plan,
   and writes the result according to the configured [output mode](#output-mode): either to
   `<original name> - completed.pka` next to the original, or into the original file after creating
   a backup. In overwrite mode, close the file in Packet Tracer before starting.
4. Open the resulting file in Packet Tracer (*File → Open*) and review the completion percentage and
   *Check Results*.
5. If the activity is not complete, paste the failing *Check Results* items into the session.
   The agent corrects the configuration and updates the result.

### Post-completion checks

- **SSH:** RSA key generation is an exec-time operation and may not be applied when the file is
  opened. Run `show ip ssh` on the router. If SSH is not enabled, enter the following once in the CLI:
  ```
  enable
  configure terminal
  crypto key generate rsa general-keys modulus 1024
  ```
- **Addressing schemes left to the student:** the agent uses a conventional assignment (router:
  first usable address; switch SVI: second; host: last). If the activity expects different values,
  the affected items appear in *Check Results*.
- **Not yet validated:** VLAN databases, server services (DNS, HTTP, DHCP), and wireless settings.
  For activities that require them, the agent also provides the equivalent CLI commands.

### Updating

```bash
cd pkt2shell
git pull
python3 install.py
```

---

## Command-line reference

The agent invokes `tools/pkt.py`. It can also be used directly:

| Command | Description |
|---|---|
| `list FILE` | Networks and devices; marks the network Packet Tracer loads on open. |
| `instructions FILE [--html]` | Activity instructions as Markdown (or raw HTML). |
| `links FILE [--net N]` | Cabling between devices (topology). |
| `show FILE DEVICE [--net N] [--startup]` | IOS running- or startup-configuration as text. |
| `ports FILE DEVICE [--net N]` | Interfaces with MAC and IP addresses. |
| `set-config FILE DEVICE CFG (-o OUT \| --in-place) [--startup] [--nets 0,1]` | Replaces the IOS configuration with the contents of `CFG`. |
| `set-host FILE DEVICE (-o OUT \| --in-place) [--ip --mask --gw --dns --ipv6 --ipv6-ll --ipv6-gw --ipv6-dns --port]` | Static addressing for PCs and servers. |
| `decrypt FILE.pka OUT.xml` / `encrypt FILE.xml OUT.pka` | Whole-file conversion. |

Example:

```bash
python3 tools/pkt.py show lab.pka R1 > r1.txt
# edit r1.txt: provide the complete configuration; use ^C as the banner delimiter
python3 tools/pkt.py set-config lab.pka R1 r1.txt --startup -o result.pka
python3 tools/pkt.py set-host result.pka PC1 --ip 192.168.0.10 --mask 255.255.255.0 \
    --gw 192.168.0.1 --ipv6 2001:db8::10/64 --ipv6-ll fe80::2 --ipv6-gw fe80::1 -o result.pka
```

## Technical overview

- **File format.** A Packet Tracer file is XML that is zlib-compressed, encrypted with Twofish in
  EAX mode, and obfuscated with position-dependent XOR passes. `tools/ptcrypto.py` implements this
  in pure Python. Its output is byte-identical to that of the reference implementation (pka2xml).
- **Activity structure.** An activity contains three networks: `#0` (saved progress), `#1`
  (initial state) and `#2` (answer network). A new activity is opened from `#1`, and a saved one from
  `#0`. Edits are applied to both.
- **Network devices.** The `RUNNINGCONFIG` element holds plain IOS commands that Packet Tracer
  replays when the file is opened, so configuration takes effect immediately. `STARTUPCONFIG` is
  applied on `reload`.
- **End devices.** PC and server addressing is stored in structured interface fields (`IP`,
  `SUBNET`, `PORT_GATEWAY`, `IPV6_*`) and device fields (`GATEWAY`, `DNS_CLIENT`).
- **Edit safety.** The XML contains raw control characters (for example `0x03` banner
  delimiters), so edits are applied as byte-level replacements of individual elements rather than
  through an XML library. All other content remains byte-identical, and every output file is
  verified by decrypting it again before it is written. Files are written atomically (temporary
  file, then rename), so an interrupted run cannot leave a partially written activity.

Notes for coding agents are maintained in [AGENTS.md](AGENTS.md). `CLAUDE.md` imports the same
file. An optional C++ converter derived from pka2xml is located in `cpp/` (`make`, requires
Crypto++). The tool does not use it.

## Responsible use

- The tool never displays or modifies an activity's answer network, scoring data, locking
  configuration or activity password. Activities are solved from their published instructions only.
- Comply with the academic integrity policy of your course. Do not use this tool where the use of
  AI assistance is not permitted.
- Packet Tracer files, extracted instructions and completed labs are excluded from version control
  (`.gitignore`) and must not be committed.

## Acknowledgements and license

The Packet Tracer file format was documented by Mirco De Zorzi in
[mircodz/pka2xml](https://github.com/mircodz/pka2xml), released under the BSD 2-Clause License
(see [LICENSE.pka2xml](LICENSE.pka2xml)). The files in `cpp/` are derived from that project.
