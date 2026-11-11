---
name: packet-tracer
description: Use when the user gives a Cisco Packet Tracer file (.pka activity or .pkt) and wants it configured, completed, inspected or its instructions read — e.g. "sprav tento lab", "urob aktivitu", "nakonfiguruj routre v tomto .pka", "čo je zadanie v tomto pka", "do this Packet Tracer activity", "solve this .pka". Configures routers, switches, PCs and servers by editing the file directly with the pkt2shell tool, without the Packet Tracer GUI.
---

# Packet Tracer labs via pkt2shell

Tool repo (local clone): `{{REPO}}`
Read `{{REPO}}/AGENTS.md` before the first edit in a session — it holds the verified facts about the file format.

Below, `$PKT` stands for this exact command — write it out in full in every shell call
(variables are not word-split in zsh and shell state does not persist between calls):

```
{{PKT}}
```

Quote file paths (lab names contain spaces). Commands take ~2–5 s, on large activities up to ~1 min
(pure-Python crypto) — use a shell timeout of at least 5 minutes.
Run one `$PKT` command per shell call (no loops, pipes, `&&` or redirections) and use `$PKT backup`
instead of `cp` — unattended runs only allow plain `$PKT …` calls.

## Output mode

Default output mode on this computer: **`{{OUTPUT_MODE}}`**

- `new` — write the result next to the original as `<original name> - completed.pka`; the original is untouched.
- `overwrite` — first back up the original to `{{REPO}}/labs/<name>/original.pka`, then write the result
  into the original file itself (use `--in-place`). Tell the user the backup path.

The user's request overrides the default for that request: "overwrite the original", "prepíš originál",
"do pôvodného súboru" → `overwrite`; "into a new file", "do nového súboru", "nechaj originál" → `new`.
If the request is ambiguous, use the default. In `overwrite` mode remind the user to close the file in
Packet Tracer first (Packet Tracer would otherwise save its own copy over the result).

## Rules

- Never modify the original file except in `overwrite` mode, and never without the backup above.
- Keep work files (instructions, checklist) in `{{REPO}}/labs/<short-lab-name>/` (git-ignored).
  Never commit `.pka`/`.xml`/instructions or lab solutions to the repo.
- **Activities (`.pka` with an answer network) always end at 100 %:** the networks Packet Tracer loads
  are made copies of the sample solution (answer network #2), every graded item is then set to the value
  Packet Tracer grades against, and `$PKT verify` checks all graded items offline.
  Never open Packet Tracer or other GUI apps to check the result — `verify` is the check.
- The answer network and the graded checklist are **read-only references**; never edit them, nor
  COMPARISONS, scoring, locking or the activity password (the tool and `encrypt --base` refuse it).

## Workflow for an activity (.pka with an answer network — `list` shows `network #2 answer`)

1. **Inspect**
   - `$PKT list "FILE"` — devices, and which network PT loads.
   - `$PKT instructions "FILE"`, save to `{{REPO}}/labs/<name>/zadanie.md` (Write tool), read it.
   - `$PKT checklist "FILE"`, save to `{{REPO}}/labs/<name>/checklist.txt` — graded items with the value
     Packet Tracer grades against, points, and the message PT shows when complete. Lines marked
     `<- graded value … the answer network has …` are graded against a different value than the sample
     solution contains (the author's override) — the sample solution alone will NOT score them.
   - `$PKT verify "FILE"` — every graded item that is wrong now (current vs. graded value): this is the list
     of faults for the hand-over.
2. **Output file**
   - `new` mode: `$PKT backup "FILE" "OUT" --force` with OUT = `<original name> - completed.pka`.
   - `overwrite` mode: `$PKT backup "FILE" "{{REPO}}/labs/<name>/original.pka"` (never replaces an existing
     backup — it holds the true original); OUT is FILE.
3. **Copy the sample solution:** `$PKT copy-answer "OUT" --whole-network --in-place`
   — networks #0 (saved) and #1 (initial) become exact copies of the answer network: configs,
   startup-configs, structured state (IPv6 lists, VLANs, RSA keys, server services, wireless), cabling,
   renamed or replaced devices. It also switches off the activity's initial setup (`LOAD_INIT_TREE`), which
   would otherwise make Packet Tracer write the planted faults back over the solution on open. Nothing
   else outside the networks changes.
4. **Verify offline:** `$PKT verify "OUT"`. It reads every graded item from OUT the way Packet Tracer will
   see it (IOS: running-config text; PCs/servers: structured fields) and compares it with the graded value.
   - `WRONG … expected 'X' (graded value; the answer network has 'Y')` — set X yourself:
     IOS device → `$PKT show "OUT" <dev>` into `{{REPO}}/labs/<name>/cfg/<dev>.txt`, edit the line
     (e.g. `hostname X`, `ip address …`, `ip route …`), `$PKT set-config "OUT" <dev> <cfg> --in-place`;
     PC/server → `$PKT set-host "OUT" <dev> --ip/--mask/--gw/--dns … --in-place`;
     home wireless router WAN → `set-wan`; anything else → XML fallback.
   - Other `WRONG` lines or `initial setup: LOAD_INIT_TREE=true` → run step 3 again.
   - Repeat until `verify` ends with `OK: every graded item has its graded value -> 100 % expected` (exit 0).
     Exit 2 = all checkable items OK, the `UNSURE` lines (live tests, variables `[[…]]`) are decided by
     Packet Tracer — hand over with those listed. Never hand over a file with `WRONG` lines.
5. **Command log (always — the user learns from it):**
   `$PKT cmdlog "OUT" --from "ORIG" --txt "{{REPO}}/labs/<name>/prikazy.txt" --in-place`
   with ORIG = the untouched original (`new` mode: FILE; `overwrite` mode: the backup
   `{{REPO}}/labs/<name>/original.pka`). It writes the CLI commands a student would type to get from the
   original to the finished file (enable → configure terminal → changes → end → copy running-config
   startup-config; PCs: `ipconfig` / `ipv6config`) into Packet Tracer's Command Log (*View Command Log*),
   and lists settings that have no CLI (DNS on a PC, wireless, WAN) as `(GUI)` notes. Passwords appear in
   plain text (type 7 decoded, type 5 matched against the instruction words). It does not touch any device,
   so grading is unchanged — run `$PKT verify "OUT"` once more as the final check.
6. **Hand over** — first line: **"✅ 100 % — every graded item has its graded value (`verify` OK)"**
   (or **"⚠️ 100 % of checkable items — Packet Tracer decides: …"** with the UNSURE items, exit 2).
   Then: output path (and backup path in `overwrite` mode); what was wrong and is now fixed, per device
   (from step 1); the message Packet Tracer will show (`checklist.txt`, e.g. "Congratulations on
   completing this activity!"); that the commands are in Packet Tracer's *View Command Log* and in
   `{{REPO}}/labs/<name>/prikazy.txt` (how many commands, on which devices, and the `(GUI)` notes).
   Remind the user: close the file in Packet Tracer **without saving**
   before the run / reopen it after; if Check Results first says incomplete, press *Fast Forward Time*
   and check again (live items such as pings need the simulation to converge).

## Workflow for a plain .pkt (no answer network)

Nothing to copy from — configure it from the instructions/request:

1. Inspect with `list`, `links`, `show <dev>`, `ports <host>`; check **every** value for each host —
   IP, mask, gateway **and DNS**.
2. Plan addressing (VLSM largest-first; when the choice is open: router = first usable, switch SVI =
   second, PC = last) and show it as a short table.
3. For each IOS device write a FULL config to `{{REPO}}/labs/<name>/cfg/<dev>.txt` starting from `show`
   (set-config replaces, it does not append). Lines are replayed in order: `service password-encryption`
   and `security passwords min-length N` before passwords; `hostname` and `ip domain-name` before
   `crypto key generate rsa general-keys modulus <bits>`. Interfaces that must be up: omit `shutdown`.
   Banner delimiter `^C`. Local VTY login = `login local` + `username …`; SSH only = `transport input ssh`.
4. Apply on OUT (backup / output mode as above):
   ```
   $PKT set-config "OUT" R1 "{{REPO}}/labs/<name>/cfg/R1.txt" --startup --in-place
   $PKT set-host "OUT" PC1 --ip … --mask … --gw … [--dns …] [--ipv6 A/64 --ipv6-ll … --ipv6-gw …] --in-place
   $PKT set-wan "OUT" "Office AP" --ip … --mask … --gw … [--dns …] --in-place   # WRT300N Internet setup
   ```
   Re-check with `show` / `ports`. For settings no command covers, use the XML fallback below.
5. Finish with the command log as in step 5 of the activity workflow
   (`$PKT cmdlog "OUT" --from "ORIG" --txt "{{REPO}}/labs/<name>/prikazy.txt" --in-place`).
   Note: `set-config` rewrites config text only; stale structured state (e.g. an old IPv6 address with a
   different prefix) can survive Packet Tracer's replay — check `ports` and the XML for such leftovers.

## XML fallback (when no command covers a setting)

When a task needs a device setting that `set-config` / `set-host` / `set-wan` do not cover (e.g. wireless
SSID/WPA key, DHCP pool, server DNS/HTTP records, structured fields of non-IOS devices), edit the
decrypted XML directly instead of giving the user a manual GUI step:

1. Apply all tool commands first, then: `$PKT decrypt "OUT" "{{REPO}}/labs/<name>/work.xml"`
   (in `overwrite` mode OUT is FILE).
2. Find the device: Grep for `<NAME translate="true">DEV</NAME>` — it occurs once per network; the
   occurrences are network #0, #1 and #2 (answer) in this order. The third one shows the expected value
   and format — read it, but edit **only the first two**
   (Grep `-n` for `<PACKETTRACER5>` to see where networks start). Read a few hundred lines around the
   device to find the field, and compare with similar devices/fields in the same network for the format.
3. Change the value with the Edit tool — one exact `old_string` per occurrence, never `replace_all`
   (it would also hit the answer network). Change values only; do not add, remove or reorder elements
   unless the format is clear from another device in the same network. Never touch the answer
   network, `ACTIVITY`, `COMPARISONS`, scoring, locking or passwords.
4. `$PKT encrypt "{{REPO}}/labs/<name>/work.xml" "OUT" --base "OUT"` — refuses (and writes nothing) if
   anything outside networks #0/#1 changed; prints which devices changed. Check that list matches
   your intent, then re-check with `ports` / `show`.
5. In the hand-over, list which settings were made by hand-editing XML (unverified field → the user
   should check that device in Packet Tracer). Only when a setting truly cannot be found in the XML,
   give the user the exact GUI/CLI steps.

## Known limits (see AGENTS.md)

- Verified: IOS running-config replay on open; PC/server addressing via set-host; home wireless router
  (WRT300N) Internet/WAN setup via set-wan — do it with the tool, do not hand it to the user as a GUI step.
- Unverified for plain .pkt files: RSA keys and VLAN databases (exec-time / `ENGINE/VLANS` state), server
  services, wireless SSID/security — use the XML fallback; for RSA keys also give the user the CLI command
  (`crypto key generate rsa`). For activities these come with the whole-network copy.
- `copy-answer --whole-network` + `verify` guarantee that the loaded networks are byte-identical to the
  answer network (the reference Packet Tracer grades against), with the answer network and activity data
  untouched.
