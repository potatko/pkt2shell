#!/usr/bin/env python3
"""
Forge Packet Tracer authentication file ("nets") to bypass login screen.
Based on pka2xml encrypt_nets (key=0xBA*16, iv=0xBE*16).
"""

import sys
import os

# Pridaj tools/ do path, aby sme mohli použiť existujúci crypto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from ptcrypto import Twofish, EAX, _xor

# Kľúč a IV pre nets (iný ako pre .pka/.pkt)
_NETS_KEY = bytes([186]) * 16
_NETS_IV  = bytes([190]) * 16

def encrypt_nets(plaintext: str) -> bytes:
    """encrypt2: len Twofish-EAX + finálna obfuscácia (bez zlib)."""
    cipher = Twofish(_NETS_KEY)
    eax = EAX(cipher)

    # Stage 3 – encrypt
    encrypted = eax.encrypt(_NETS_IV, plaintext.encode("utf-8"))

    # Stage 4 – obfuscácia (rovnaká ako v pka2xml)
    n = len(encrypted)
    out = bytearray(n)
    for i in range(n):
        out[n - 1 - i] = encrypted[i] ^ ((n - i * n) & 0xFF)
    return bytes(out)


def main():
    # Rovnaký payload ako v originálnom pka2xml --forge
    payload = "foobar~foobar~foobar~foobar~1700000000"

    out_path = sys.argv[1] if len(sys.argv) > 1 else "nets"

    data = encrypt_nets(payload)
    with open(out_path, "wb") as f:
        f.write(data)

    print(f"[+] Forged nets file written to: {out_path}")
    print(f"    Payload: {payload}")
    print()
    print("Kam to skopírovať:")
    print("  macOS / Linux : ~/packettracer/nets")
    print("                 alebo ~/.packettracer*/nets")
    print("  Windows       : %USERPROFILE%\\packettracer\\nets")
    print("                 alebo Documents\\Cisco Packet Tracer *\\nets")


if __name__ == "__main__":
    main()
