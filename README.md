# pkt2shell

Nástroj, s ktorým **Claude Code** vypracuje aktivitu z Cisco Packet Tracera (`.pka`) priamo v súbore.
Pošleš mu `.pka`, on si prečíta zadanie, nakonfiguruje routre, switche a PC a vráti ti hotový súbor,
ktorý otvoríš v Packet Traceri.

Funguje na **Windows, macOS aj Linuxe**. Okrem Pythonu netreba nič inštalovať ani kompilovať.
Otestované s Packet Tracer 9.0.1.

---

## Návod

### 1. Čo potrebuješ

- **Claude Code**, buď ako desktopová aplikácia Claude (záložka Code), alebo ako príkaz `claude` v termináli
- **Python 3.8 alebo novší**
  - Windows: nainštaluj z [python.org](https://www.python.org/downloads/) a zaškrtni „Add python.exe to PATH“
  - macOS: Python je väčšinou už nainštalovaný, otestuješ to príkazom `python3 --version`
- **Packet Tracer**, aby si si mohol výsledok otvoriť a skontrolovať percentá
- **git**, alebo si repozitár stiahni ako ZIP (zelené tlačidlo *Code* → *Download ZIP*)

> Repozitár je súkromný. Aby si ho mohol stiahnuť, musí ťa vlastník pridať
> (Settings → Collaborators).

### 2. Inštalácia (iba raz)

```bash
git clone https://github.com/potatko/pkt2shell.git
cd pkt2shell
python3 install.py
```

Na Windowse namiesto `python3` použi `py`:

```bash
py install.py
```

Ak všetko prebehlo v poriadku, uvidíš `OK  skill installed: ...`.
Inštalátor pridá do Claude Code **skill** `packet-tracer`, čo je návod, podľa ktorého Claude vie,
ako s `.pka` súbormi pracovať. Priečinok `pkt2shell` potom nepresúvaj. Ak ho presunieš,
spusti `install.py` znova.

### 3. Vypracovanie aktivity

1. Stiahni si aktivitu `.pka`, napríklad do priečinka Downloads.
2. Otvor **novú** session v Claude Code. Môže byť v ľubovoľnom priečinku.
3. Napíš napríklad:

   > sprav aktivitu "C:\Users\ja\Downloads\11.5.5 Packet Tracer - Subnet an IPv4 Network.pka"

   Na Macu: `sprav aktivitu ~/Downloads/lab.pka`. Súbor môžeš do okna aj pretiahnuť.
4. Claude si prečíta zadanie a topológiu, ukáže ti plán (adresy, čo nastaví na ktorom zariadení)
   a vytvorí nový súbor vedľa pôvodného:

   `… - VYPRACOVANE.pka`

   Pôvodný súbor zostane nezmenený.
5. Otvor `VYPRACOVANE.pka` v Packet Traceri (File → Open) a pozri si percento
   (*Check Results*).
6. Ak to nie je 100 %, skopíruj Claudovi nesplnené položky z *Check Results*. Opraví ich
   a vytvorí nový súbor.

### 4. Čo si skontrolovať

- **SSH na routroch:** RSA kľúč sa pri otvorení súboru nemusí vytvoriť. Na routri zadaj
  `show ip ssh`. Ak SSH nie je zapnuté, zadaj raz v CLI:
  ```
  enable
  conf t
  crypto key generate rsa general-keys modulus 1024
  ```
- **Vlastné adresovanie:** keď si zadanie nechá adresy na teba, Claude použije bežný spôsob
  (router = prvá použiteľná adresa, switch = druhá, PC = posledná). Ak by hodnotenie čakalo iné adresy,
  uvidíš to v *Check Results*.
- **VLANy, DHCP/DNS servery, wireless** zatiaľ nie sú overené. Claude ti v takom prípade dá aj príkazy
  na zadanie v CLI.

### 5. Aktualizácia

```bash
cd pkt2shell
git pull
python3 install.py
```

---

## Pravidlá

- Nástroj **nikdy nepozerá ani nemení vzorové riešenie** (answer network) ani hodnotenie aktivity.
  Claude rieši lab iba podľa zadania.
- Dodržiavaj pravidlá svojho predmetu. Ak nemáš dovolené pri aktivitách používať AI, nepoužívaj ho.
- Do repozitára sa necommitujú `.pka` súbory, zadania ani vypracované laby (sú v `.gitignore`).

---

## Pre pokročilých: príkazy nástroja

Claude volá nástroj `tools/pkt.py`. Môžeš ho používať aj sám:

```bash
python3 tools/pkt.py list lab.pka                  # siete a zariadenia
python3 tools/pkt.py instructions lab.pka          # zadanie ako Markdown
python3 tools/pkt.py links lab.pka                 # topológia (kto je kam zapojený)
python3 tools/pkt.py show lab.pka R1 > r1.txt      # IOS konfigurácia ako text
python3 tools/pkt.py ports lab.pka PC1             # porty, MAC, IP
# uprav r1.txt (celá konfigurácia, nahradí pôvodnú; banner oddeľuj ^C)
python3 tools/pkt.py set-config lab.pka R1 r1.txt --startup -o hotovo.pka
python3 tools/pkt.py set-host hotovo.pka PC1 --ip 192.168.0.10 --mask 255.255.255.0 \
    --gw 192.168.0.1 --ipv6 2001:db8::10/64 --ipv6-ll fe80::2 --ipv6-gw fe80::1 -o hotovo.pka
python3 tools/pkt.py decrypt lab.pka lab.xml       # celý súbor ako XML
python3 tools/pkt.py encrypt lab.xml lab.pka
```

### Ako to funguje

- `.pka`/`.pkt` je XML, ktoré je skomprimované (zlib), zašifrované (Twofish/EAX) a jednoducho
  zamaskované. `tools/ptcrypto.py` to robí v čistom Pythone. Výsledok je bajt po bajte rovnaký
  ako z pôvodného nástroja pka2xml.
- Aktivita obsahuje tri siete: `#0` uložený postup, `#1` počiatočný stav a `#2` vzorové riešenie.
  Čerstvá aktivita sa otvára zo siete `#1`, uložená zo siete `#0`. Nástroj zapisuje do oboch.
- Routre a switche: text v `RUNNINGCONFIG` Packet Tracer pri otvorení súboru vykoná ako príkazy,
  takže konfigurácia platí hneď. `STARTUPCONFIG` sa použije pri `reload`.
- PC a servery majú adresy v samostatných poliach portu (`IP`, `SUBNET`, `PORT_GATEWAY`, `IPV6_*`).
- Úpravy sa robia priamo v bajtoch, nie cez XML knižnicu, pretože XML obsahuje riadiace znaky
  (napríklad `0x03` v banneroch). Zvyšok súboru tak zostane bajt po bajte rovnaký. Každý výstup
  sa pred zápisom overí opätovným dešifrovaním.

Podrobnosti pre Clauda sú v [CLAUDE.md](CLAUDE.md). V priečinku `cpp/` je voliteľná C++ verzia
konvertora (`make`, potrebuje `cryptopp`), ktorú nástroj nepotrebuje.

## Licencia a poďakovanie

Formát súboru zistil Mirco De Zorzi v projekte [mircodz/pka2xml](https://github.com/mircodz/pka2xml)
(BSD 2-Clause, pozri [LICENSE.pka2xml](LICENSE.pka2xml)). Súbory v `cpp/` sú odvodené z jeho kódu.

Cisco a Packet Tracer sú ochranné známky spoločnosti Cisco Systems, Inc. Tento projekt nemá s Ciscom nič spoločné.
