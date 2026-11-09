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

Quote file paths (lab names contain spaces). Each command takes ~2–5 s (pure-Python crypto).
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
- Keep work files (instructions, configs) in `{{REPO}}/labs/<short-lab-name>/` (git-ignored).
  Never commit `.pka`/`.xml`/instructions or lab solutions to the repo.
- The answer network (#2, the sample solution) and the graded checklist are **read-only references**:
  read them with `$PKT checklist`, `--answer` and `copy-answer`, never edit them. Never touch
  COMPARISONS, scoring, locking or the activity password (the tool and `encrypt --base` refuse it).
- Solve the lab from the instructions first; use the answer key to check the result and to fill in
  whatever you could not do (see "Reach 100 % with the answer key").
- Don't claim a percentage — only Packet Tracer shows it. Ask the user to report it.

## Workflow

1. **Inspect**
   - `$PKT list "FILE"` — devices, and which network PT loads (`<- loaded on open`).
   - `$PKT instructions "FILE"`, save the output to `{{REPO}}/labs/<name>/zadanie.md` (Write tool),
     then read it fully.
   - `$PKT checklist "FILE"` — every graded item with its expected value and points (the answer key),
     save it to `{{REPO}}/labs/<name>/checklist.txt`. This is the target: every line must match.
   - `$PKT links "FILE"` — topology (which device/port connects where).
   - `$PKT show "FILE" <dev>` for every IOS device; `$PKT ports "FILE" <host>` for PCs/servers and
     home wireless routers (the `WAN (Internet setup)` line shows their Internet IP/mask/gateway/DNS).
     Check **every** value the instructions give for each host — IP, mask, gateway **and DNS** — not
     only the ones that look wrong; a missing DNS server is a typical planted fault.
2. **Plan** — addressing (VLSM largest-first when you design it; when the lab leaves the choice open,
   use router = first usable, switch SVI = second usable, PC = last usable) and per-device tasks.
   Show the plan to the user briefly as a table.
3. **Write configs** — for each IOS device save a FULL config to `{{REPO}}/labs/<name>/cfg/<dev>.txt`,
   starting from `show` output and editing it (set-config replaces, it does not append).
   - Order matters (lines are replayed): `service password-encryption` and
     `security passwords min-length N` before any passwords; `hostname` and `ip domain-name`
     before `crypto key generate rsa general-keys modulus <bits>`.
   - Interfaces that must be up: omit `shutdown`. Banner delimiter: `^C`.
   - Local login on VTY = `login local` + `username …`; SSH only = `transport input ssh`.
4. **Apply**, chaining every edit on the output file:
   - `new` mode: `$PKT backup "FILE" "OUT" --force` (copy) with OUT = `<original name> - completed.pka`,
     then edit OUT:
     ```
     $PKT set-config "OUT" R1 "{{REPO}}/labs/<name>/cfg/R1.txt" --startup --in-place
     $PKT set-host "OUT" PC1 --ip … --mask … --gw … [--dns …] [--ipv6 A/64 --ipv6-ll … --ipv6-gw …] --in-place
     $PKT set-wan "OUT" "Office AP" --ip … --mask … --gw … [--dns …] --in-place   # WRT300N Internet setup
     ```
   - `overwrite` mode: `$PKT backup "FILE" "{{REPO}}/labs/<name>/original.pka"` (never replaces an
     existing backup — it holds the true original), then run the same commands
     on "FILE" with `--in-place`. The file may already contain edits from an earlier run: still check every
     device against the instructions.
   Then re-check with `$PKT show "OUT" <dev>` / `$PKT ports "OUT" <host>`.
   For anything these commands cannot set, use the answer key / XML fallback below — do not hand it to the user.
5. **Check against the answer key** — go through `checklist.txt` line by line and compare each expected
   value with `show` / `ports` / `links` of OUT. Fix every mismatch (next section) before handing over.
6. **Hand over** — tell the user the output path (and the backup path in `overwrite` mode) and what to check in Packet Tracer
   (open it with File → Open): the completion percentage and Check Results; for SSH labs
   `show ip ssh` on the router (if SSH is not enabled, they run `crypto key generate rsa` once in the
   CLI). Ask them to paste failing Check Results items, then fix and re-apply.

## Reach 100 % with the answer key

When a graded item still does not match, or you have no command for it, or you are not sure how to
do it, take it from the sample solution instead of guessing or handing it to the user:

1. Look at the expected state: `$PKT show "FILE" <dev> --answer`, `$PKT ports "FILE" <dev> --answer`,
   `$PKT links "FILE" --answer`. For IOS devices copy the needed lines (or the whole answer config)
   into your cfg file and re-apply with `set-config` — this keeps your own work and still matches.
   Hashed secrets in the answer (`enable secret 5 $1$…`, `username … secret 5 …`) can be copied as is.
2. Copy whole devices from the answer when the setting is outside running-config (VLAN database, RSA keys,
   server services DNS/HTTP/DHCP/e-mail, wireless SSID/WPA, device display name, anything you could not find):
   ```
   $PKT copy-answer "OUT" "Server0" "Wireless Router" --in-place
   ```
   This replaces the device's ENGINE in networks #0/#1 with the answer's (it keeps the device's
   position and identity; cable references are translated). It renames devices the activity renames.
3. Missing or wrong cables: `$PKT copy-answer "OUT" --links --in-place`.
4. Everything at once: `$PKT copy-answer "OUT" --all --links --in-place`. If it reports
   `SKIPPED … the activity replaces the device` (a device of a different model in the answer) or the
   activity adds devices, use the last resort `$PKT copy-answer "OUT" --whole-network --in-place`
   (replaces networks #0/#1 entirely with the answer network).
5. Re-run step 5 of the workflow (checklist vs. `show`/`ports`). In the hand-over list which devices
   were copied from the answer key.

Note: some graded items are evaluated live in Packet Tracer (connectivity tests, ping results, DHCP
leases) — copying the configuration makes them pass once the simulation converges; tell the user to
wait a few seconds or press *Fast Forward Time* before *Check Results*.

## XML fallback (when no command covers a setting)

When a task needs a device setting that `set-config` / `set-host` / `set-wan` do not cover (e.g. wireless
SSID/WPA key, DHCP pool, server DNS/HTTP records, structured fields of non-IOS devices), edit the
decrypted XML directly instead of giving the user a manual GUI step:

1. Apply all tool commands first, then: `$PKT decrypt "OUT" "{{REPO}}/labs/<name>/work.xml"`
   (in `overwrite` mode OUT is FILE).
   Prefer `copy-answer` (above) for whole devices; use this fallback for a single field, or when the
   answer key does not cover the setting.
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
- Unverified: RSA keys and VLAN databases (exec-time / `ENGINE/VLANS` state), server services
  (DNS/HTTP/DHCP records), wireless SSID/security. When a lab needs these, copy the device with
  `copy-answer` (or use the XML fallback); for RSA keys also give the user the CLI command
  (`crypto key generate rsa`) in case the replay misses it.
- `copy-answer` is verified to write a valid file that keeps the answer network and activity data
  byte-identical; whether Packet Tracer scores every copied setting is confirmed per activity by the user.
