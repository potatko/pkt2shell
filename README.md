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

3. The agent reads the instructions, lists what differs from the activity's sample solution, and writes
   the result according to the configured [output mode](#output-mode): either to
   `<original name> - completed.pka` next to the original, or into the original file after creating
   a backup. In overwrite mode, close the file in Packet Tracer (without saving) before starting.
4. For activities, the networks Packet Tracer loads are replaced by exact copies of the sample
   solution and checked offline with `verify`; the report starts with "✅ 100 %". Packet Tracer is
   not opened. Open the result yourself (*File → Open*); if *Check Results* first says incomplete,
   press *Fast Forward Time* and check again.
5. Plain `.pkt` files have no sample solution; the agent configures them from the instructions.
6. To learn from the result, open *View Command Log* in Packet Tracer: it lists, per device, the
   commands that turn the original activity into the completed one (`cmdlog`). The same commands are
   saved as `labs/<activity>/prikazy.txt` in the repository.

Every activity stores its sample solution (the answer network Packet Tracer grades against) and a
list of graded items (`checklist`). The agent copies the sample solution into the networks Packet
Tracer loads (`copy-answer --whole-network`) and confirms with `verify` that they are identical, so
the activity is complete without opening Packet Tracer.

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
- **Not yet validated:** VLAN databases, server services (DNS, HTTP, DHCP), and wireless SSID/security
  settings (the Internet/WAN setup of WRT300N routers is supported via `set-wan`).
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
| `links FILE [--net N \| --answer]` | Cabling between devices (topology). |
| `show FILE DEVICE [--net N \| --answer] [--startup]` | IOS running- or startup-configuration as text. `--answer` reads the sample solution. |
| `ports FILE DEVICE [--net N \| --answer]` | Interfaces with MAC and IP addresses. |
| `checklist FILE [--dev NAME]` | Graded items of the activity with expected values and points (answer key), plus the messages Packet Tracer shows when the activity is complete or incomplete. |
| `verify FILE` | Offline check of every graded item against the value Packet Tracer grades (exit code 0 = 100 %, 1 = wrong items listed, 2 = only items that Packet Tracer decides at runtime). |
| `copy-answer FILE [DEVICE ...] (-o OUT \| --in-place) [--all] [--links] [--whole-network]` | Copies devices, cabling or the whole network from the sample solution into networks #0/#1. |
| `set-config FILE DEVICE CFG (-o OUT \| --in-place) [--startup] [--nets 0,1]` | Replaces the IOS configuration with the contents of `CFG`. |
| `set-host FILE DEVICE (-o OUT \| --in-place) [--ip --mask --gw --dns --ipv6 --ipv6-ll --ipv6-gw --ipv6-dns --port]` | Static addressing for PCs and servers. |
| `set-wan FILE DEVICE (-o OUT \| --in-place) [--ip --mask --gw --dns]` | Internet (WAN) setup of a home wireless router (Linksys WRT300N). |
| `cmdlog FILE --from ORIG (-o OUT \| --in-place \| --dry-run) [--txt CMDS.txt]` | Writes the CLI commands that turn `ORIG` (the unsolved file) into `FILE` into Packet Tracer's command log (*View Command Log*), for learning: `enable`, `configure terminal`, the configuration changes, `end`, `copy running-config startup-config`; `ipconfig` / `ipv6config` on PCs. Settings without a CLI (PC DNS, wireless, WAN) are listed as GUI notes. Passwords are shown in plain text (type 7 decoded, type 5 matched against the activity instructions). Devices and grading are not changed. |
| `decrypt FILE.pka OUT.xml` / `encrypt FILE.xml OUT.pka [--base ORIG.pka]` | Whole-file conversion. With `--base`, only changes inside networks #0/#1 are accepted (used by the agent when it edits settings that no command covers directly in the XML). |

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
  (initial state) and `#2` (answer network, the sample solution). A new activity is opened from `#1`,
  and a saved one from `#0`. Edits are applied to both. The graded items are listed in the
  `COMPARISONS` tree (expected value and points per item).
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

- The tool never modifies an activity's answer network, scoring data, locking configuration or
  activity password; `encrypt --base` refuses any such change. It reads the answer network and the
  graded checklist to verify and complete a solution.
- Comply with the academic integrity policy of your course. Do not use this tool where the use of
  AI assistance is not permitted.
- Packet Tracer files, extracted instructions and completed labs are excluded from version control
  (`.gitignore`) and must not be committed.

## Acknowledgements and license

The Packet Tracer file format was documented by Mirco De Zorzi in
[mircodz/pka2xml](https://github.com/mircodz/pka2xml), released under the BSD 2-Clause License
(see [LICENSE.pka2xml](LICENSE.pka2xml)). The files in `cpp/` are derived from that project.
