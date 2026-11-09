"""Pure-Python codec for Cisco Packet Tracer .pka/.pkt files (no compiled dependencies).

File format (reverse engineered by Mirco De Zorzi, github.com/mircodz/pka2xml, BSD-2-Clause):
  xml --zlib (4-byte big-endian size prefix)--> --xor (len - i)--> --Twofish/EAX (key 0x89*16,
  nonce 0x10*16, 16-byte tag)--> --reverse + xor (len - i*len)--> file

This module implements Twofish (encryption direction only, which is all EAX needs) and EAX
(CTR + OMAC/CMAC) from their specifications.
"""
import zlib

# ------------------------------------------------------------------ Twofish

_Q0T = ([0x8, 0x1, 0x7, 0xD, 0x6, 0xF, 0x3, 0x2, 0x0, 0xB, 0x5, 0x9, 0xE, 0xC, 0xA, 0x4],
        [0xE, 0xC, 0xB, 0x8, 0x1, 0x2, 0x3, 0x5, 0xF, 0x4, 0xA, 0x6, 0x7, 0x0, 0x9, 0xD],
        [0xB, 0xA, 0x5, 0xE, 0x6, 0xD, 0x9, 0x0, 0xC, 0x8, 0xF, 0x3, 0x2, 0x4, 0x7, 0x1],
        [0xD, 0x7, 0xF, 0x4, 0x1, 0x2, 0x6, 0xE, 0x9, 0xB, 0x3, 0x0, 0x8, 0x5, 0xC, 0xA])
_Q1T = ([0x2, 0x8, 0xB, 0xD, 0xF, 0x7, 0x6, 0xE, 0x3, 0x1, 0x9, 0x4, 0x0, 0xA, 0xC, 0x5],
        [0x1, 0xE, 0x2, 0xB, 0x4, 0xC, 0x3, 0x7, 0x6, 0xD, 0xA, 0x5, 0xF, 0x9, 0x0, 0x8],
        [0x4, 0xC, 0x7, 0x5, 0x1, 0x6, 0x9, 0xA, 0x0, 0xE, 0xD, 0x8, 0x2, 0xB, 0x3, 0xF],
        [0xB, 0x9, 0x5, 0x1, 0xC, 0x3, 0xD, 0xE, 0x6, 0x4, 0x7, 0xF, 0x2, 0x0, 0x8, 0xA])


def _make_q(t):
    def ror4(x, n):
        return ((x >> n) | (x << (4 - n))) & 0xF
    out = []
    for x in range(256):
        a0, b0 = x >> 4, x & 0xF
        a1 = a0 ^ b0
        b1 = a0 ^ ror4(b0, 1) ^ ((8 * a0) & 0xF)
        a2, b2 = t[0][a1], t[1][b1]
        a3 = a2 ^ b2
        b3 = a2 ^ ror4(b2, 1) ^ ((8 * a2) & 0xF)
        a4, b4 = t[2][a3], t[3][b3]
        out.append((b4 << 4) | a4)
    return out


Q0, Q1 = _make_q(_Q0T), _make_q(_Q1T)


def _gf_mul(a, b, poly):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        if a & 0x100:
            a ^= poly
        b >>= 1
    return r


_MDS = ((0x01, 0xEF, 0x5B, 0x5B), (0x5B, 0xEF, 0xEF, 0x01),
        (0xEF, 0x5B, 0x01, 0xEF), (0xEF, 0x01, 0xEF, 0x5B))
_RS = ((0x01, 0xA4, 0x55, 0x87, 0x5A, 0x58, 0xDB, 0x9E),
       (0xA4, 0x56, 0x82, 0xF3, 0x1E, 0xC6, 0x68, 0xE5),
       (0x02, 0xA1, 0xFC, 0xC1, 0x47, 0xAE, 0x3D, 0x19),
       (0xA4, 0x55, 0x87, 0x5A, 0x58, 0xDB, 0x9E, 0x03))
M32 = 0xFFFFFFFF


def _rol(x, n):
    return ((x << n) | (x >> (32 - n))) & M32


def _ror(x, n):
    return ((x >> n) | (x << (32 - n))) & M32


def _bytes_of(w):
    return [(w >> (8 * i)) & 0xFF for i in range(4)]


def _mds_col(i, b):
    """Word contribution of byte b at input position i through the MDS matrix."""
    return sum(_gf_mul(_MDS[r][i], b, 0x169) << (8 * r) for r in range(4))


def _h_bytes(y, L):
    """Twofish h-function before the MDS step; y: 4 bytes, L: list of key words (L[0] first)."""
    k = len(L)
    y = list(y)
    if k == 4:
        l = _bytes_of(L[3]); y = [Q1[y[0]] ^ l[0], Q0[y[1]] ^ l[1], Q0[y[2]] ^ l[2], Q1[y[3]] ^ l[3]]
    if k >= 3:
        l = _bytes_of(L[2]); y = [Q1[y[0]] ^ l[0], Q1[y[1]] ^ l[1], Q0[y[2]] ^ l[2], Q0[y[3]] ^ l[3]]
    l1, l0 = _bytes_of(L[1]), _bytes_of(L[0])
    return [Q1[Q0[Q0[y[0]] ^ l1[0]] ^ l0[0]],
            Q0[Q0[Q1[y[1]] ^ l1[1]] ^ l0[1]],
            Q1[Q1[Q0[y[2]] ^ l1[2]] ^ l0[2]],
            Q0[Q1[Q1[y[3]] ^ l1[3]] ^ l0[3]]]


def _h(x, L):
    y = _h_bytes(_bytes_of(x), L)
    r = 0
    for i in range(4):
        r ^= _mds_col(i, y[i])
    return r


class Twofish:
    def __init__(self, key):
        n = len(key)
        assert n in (16, 24, 32)
        k = n // 8
        m = [int.from_bytes(key[4 * i:4 * i + 4], "little") for i in range(2 * k)]
        me, mo = m[0::2], m[1::2]
        s = []
        for i in range(k):
            chunk = key[8 * i:8 * i + 8]
            v = [0, 0, 0, 0]
            for r in range(4):
                acc = 0
                for c in range(8):
                    acc ^= _gf_mul(_RS[r][c], chunk[c], 0x14D)
                v[r] = acc
            s.append(v[0] | v[1] << 8 | v[2] << 16 | v[3] << 24)
        sbox_key = s[::-1]                     # S = (S_{k-1}, ..., S_0)
        rho = 0x01010101
        self.K = []
        for i in range(20):
            a = _h(2 * i * rho & M32, me)
            b = _rol(_h((2 * i + 1) * rho & M32, mo), 8)
            self.K.append((a + b) & M32)
            self.K.append(_rol((a + 2 * b) & M32, 9))
        # key-dependent g tables: g(X) = T0[x0] ^ T1[x1] ^ T2[x2] ^ T3[x3]
        self.T = [[0] * 256 for _ in range(4)]
        for b in range(256):
            y = _h_bytes([b, b, b, b], sbox_key)
            for i in range(4):
                self.T[i][b] = _mds_col(i, y[i])

    def encrypt_block(self, block):
        T0, T1, T2, T3 = self.T
        K = self.K
        r0 = int.from_bytes(block[0:4], "little") ^ K[0]
        r1 = int.from_bytes(block[4:8], "little") ^ K[1]
        r2 = int.from_bytes(block[8:12], "little") ^ K[2]
        r3 = int.from_bytes(block[12:16], "little") ^ K[3]
        for rnd in range(16):
            t0 = T0[r0 & 0xFF] ^ T1[(r0 >> 8) & 0xFF] ^ T2[(r0 >> 16) & 0xFF] ^ T3[r0 >> 24]
            x = ((r1 << 8) | (r1 >> 24)) & M32
            t1 = T0[x & 0xFF] ^ T1[(x >> 8) & 0xFF] ^ T2[(x >> 16) & 0xFF] ^ T3[x >> 24]
            f0 = (t0 + t1 + K[2 * rnd + 8]) & M32
            f1 = (t0 + 2 * t1 + K[2 * rnd + 9]) & M32
            r2 ^= f0
            r2 = ((r2 >> 1) | (r2 << 31)) & M32
            r3 = (((r3 << 1) | (r3 >> 31)) & M32) ^ f1
            r0, r1, r2, r3 = r2, r3, r0, r1
        out = (r2 ^ K[4], r3 ^ K[5], r0 ^ K[6], r1 ^ K[7])
        return b"".join(w.to_bytes(4, "little") for w in out)

# ------------------------------------------------------------------ EAX


def _dbl(b):
    v = int.from_bytes(b, "big") << 1
    if v >> 128:
        v = (v & ((1 << 128) - 1)) ^ 0x87
    return v.to_bytes(16, "big")


def _xor(a, b):
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big")


class EAX:
    def __init__(self, cipher):
        self.E = cipher.encrypt_block
        L = self.E(bytes(16))
        self.k1 = _dbl(L)
        self.k2 = _dbl(self.k1)

    def _omac(self, t, msg):
        data = bytes(15) + bytes([t]) + msg
        n = len(data)
        full = n % 16 == 0
        last_start = n - 16 if full else n - n % 16
        state = bytes(16)
        for i in range(0, last_start, 16):
            state = self.E(_xor(state, data[i:i + 16]))
        last = data[last_start:]
        if full:
            last = _xor(last, self.k1)
        else:
            last = _xor(last + b"\x80" + bytes(15 - len(last)), self.k2)
        return self.E(_xor(state, last))

    def _ctr(self, n0, data):
        ctr = int.from_bytes(n0, "big")
        out = bytearray(len(data))
        E = self.E
        for i in range(0, len(data), 16):
            ks = E((ctr & ((1 << 128) - 1)).to_bytes(16, "big"))
            ctr += 1
            chunk = data[i:i + 16]
            out[i:i + len(chunk)] = _xor(chunk, ks[:len(chunk)])
        return bytes(out)

    def encrypt(self, nonce, plaintext, header=b""):
        n0 = self._omac(0, nonce)
        h0 = self._omac(1, header)
        c = self._ctr(n0, plaintext)
        tag = _xor(_xor(n0, h0), self._omac(2, c))
        return c + tag

    def decrypt(self, nonce, data, header=b""):
        c, tag = data[:-16], data[-16:]
        n0 = self._omac(0, nonce)
        h0 = self._omac(1, header)
        if _xor(_xor(n0, h0), self._omac(2, c)) != tag:
            raise ValueError("authentication tag mismatch: not a valid Packet Tracer file")
        return self._ctr(n0, c)

# ------------------------------------------------------------------ Packet Tracer file format

_PT_KEY = bytes([137]) * 16
_PT_IV = bytes([16]) * 16
_eax = None


def _get_eax():
    global _eax
    if _eax is None:
        _eax = EAX(Twofish(_PT_KEY))
    return _eax


def _xor_pos(data, f):
    n = len(data)
    return bytes(data[i] ^ (f(n, i) & 0xFF) for i in range(n))


def decrypt_pka(raw):
    """Packet Tracer file bytes -> XML bytes."""
    n = len(raw)
    # stage 1: reverse + xor (len - i*len)
    processed = bytes(raw[n - 1 - i] ^ ((n - i * n) & 0xFF) for i in range(n))
    # stage 2: Twofish/EAX
    out = _get_eax().decrypt(_PT_IV, processed)
    # stage 3: xor (len - i)
    out = _xor_pos(out, lambda m, i: m - i)
    # stage 4: zlib with 4-byte big-endian length prefix
    size = int.from_bytes(out[:4], "big")
    xml = zlib.decompress(out[4:])
    if len(xml) != size:
        raise ValueError("size mismatch after decompression")
    return xml


def encrypt_pka(xml):
    """XML bytes -> Packet Tracer file bytes."""
    comp = len(xml).to_bytes(4, "big") + zlib.compress(xml)
    comp = _xor_pos(comp, lambda m, i: m - i)
    enc = _get_eax().encrypt(_PT_IV, comp)
    n = len(enc)
    out = bytearray(n)
    for i in range(n):
        out[n - 1 - i] = enc[i] ^ ((n - i * n) & 0xFF)
    return bytes(out)
