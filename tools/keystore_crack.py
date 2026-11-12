#!/usr/bin/env python3
"""
keystore_crack.py — 以太坊 V3 keystore 离线破解（TokenPocket/imToken/Trust 等通用格式）

支持：
  --keystore   eth V3 JSON（crypto/Crypto 两种大小写）
  --wordlist   字典
  --rules      字典变形（大小写、数字后缀、常见符号、年份）
  --mask       掩码暴破，如 ?d?d?d?d?d?d（hashcat 语法）
  --export-hashcat  输出 mode 15700(scrypt)/15600(pbkdf2) 的 hash 字符串与命令
  --selftest   自造 keystore → 破解一遍，验证代码正确

依赖：pip install pycryptodome
性能：scrypt N=262144 在单核约 0.5–1.5 次/秒；GPU（hashcat）可到 10–100 次/秒。
"""
import argparse
import hashlib
import itertools
import json
import os
import sys
import time

try:
    from Crypto.Cipher import AES
    from Crypto.Hash import keccak
except ImportError:
    print("缺少 pycryptodome：pip install pycryptodome", file=sys.stderr)
    raise

# ── keccak-256（以太坊用，不是 sha3） ──
def keccak256(b: bytes) -> bytes:
    h = keccak.new(digest_bits=256)
    h.update(b)
    return h.digest()


def load_keystore(path):
    with open(path, encoding="utf-8") as f:
        js = json.load(f)
    c = js.get("crypto") or js.get("Crypto")
    if not c:
        raise SystemExit("不是 V3 keystore（缺少 crypto 字段）")
    kdf = c["kdf"].lower()
    salt = bytes.fromhex(c["kdfparams"]["salt"])
    ct = bytes.fromhex(c["ciphertext"])
    mac = bytes.fromhex(c["mac"])
    iv = bytes.fromhex(c["cipherparams"]["iv"])
    if kdf == "scrypt":
        n = int(c["kdfparams"]["n"]); r = int(c["kdfparams"]["r"]); p = int(c["kdfparams"]["p"])
        dklen = int(c["kdfparams"].get("dklen", 32))

        def derive(pw: bytes) -> bytes:
            return hashlib.scrypt(pw, salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=1024 * 1024 * 1024)
        meta = f"scrypt n={n} r={r} p={p}"
    elif kdf == "pbkdf2":
        it = int(c["kdfparams"]["c"]); prf = c["kdfparams"].get("prf", "hmac-sha256")
        dklen = int(c["kdfparams"].get("dklen", 32))

        def derive(pw: bytes) -> bytes:
            return hashlib.pbkdf2_hmac("sha256", pw, salt, it, dklen)
        meta = f"pbkdf2 c={it} {prf}"
    else:
        raise SystemExit(f"不支持的 kdf: {kdf}")
    return {"kdf": kdf, "salt": salt, "ct": ct, "mac": mac, "iv": iv,
            "derive": derive, "meta": meta, "raw": js, "c": c,
            "n": locals().get("n"), "r": locals().get("r"), "p": locals().get("p"),
            "it": locals().get("it")}


def check_pass(ks, pw: str) -> bool:
    dk = ks["derive"](pw.encode())
    if keccak256(dk[16:32] + ks["ct"]) != ks["mac"]:
        return False
    # 解出私钥
    dec = AES.new(dk[:16], AES.MODE_CTR, nonce=b"", initial_value=int.from_bytes(ks["iv"], "big"))
    pk = dec.decrypt(ks["ct"])
    print(f"\n[+] 命中密码: {pw!r}")
    print(f"[+] 私钥: 0x{pk.hex()}")
    return True


def gen_candidates(wordlist, rules):
    with open(wordlist, encoding="utf-8", errors="ignore") as f:
        for line in f:
            base = line.strip()
            if not base:
                continue
            yield base
            if not rules:
                continue
            lows = [base.lower(), base.capitalize(), base.upper()]
            for v in lows:
                yield v
                for suf in ("1", "123", "1234", "123456", "!", "@", "2024", "2025", "2026", "520", "1314"):
                    yield v + suf
                    yield suf + v
                yield v + "1"


def gen_mask(mask):
    classes = {"d": "0123456789", "l": "abcdefghijklmnopqrstuvwxyz",
               "u": "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "s": "!@#$%^&*.-_"}
    parts = []
    i = 0
    while i < len(mask):
        if mask[i] == "?":
            parts.append(classes[mask[i + 1]]); i += 2
        else:
            parts.append(mask[i]); i += 1
    return ("".join(p) for p in itertools.product(*parts))


def export_hashcat(ks):
    c = ks["c"]
    if ks["kdf"] == "scrypt":
        line = f"$ethereum$s*{ks['n']}*{ks['r']}*{ks['p']}*{ks['salt'].hex()}*{ks['ct'].hex()}*{ks['mac'].hex()}"
        print("\n[hashcat] mode 15700 (Ethereum Wallet, scrypt):")
        print(line)
        print("\nhashcat -m 15700 hash.txt wordlist.txt -r rules/best64.rule")
        print("hashcat -m 15700 hash.txt -a 3 ?d?d?d?d?d?d?d?d")
    else:
        line = f"$ethereum$p*{ks['it']}*{ks['salt'].hex()}*{ks['ct'].hex()}*{ks['mac'].hex()}"
        print("\n[hashcat] mode 15600 (Ethereum Wallet, PBKDF2-HMAC-SHA256):")
        print(line)
        print("hashcat -m 15600 hash.txt wordlist.txt -r rules/best64.rule")


def selftest():
    print("[*] 生成测试 keystore（密码 Test@2026，scrypt n=16384 加速自测）")
    password = "Test@2026"
    priv = bytes.fromhex("4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318")
    salt = os.urandom(32); iv = os.urandom(16)
    n, r, p = 16384, 8, 1
    dk = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    enc = AES.new(dk[:16], AES.MODE_CTR, nonce=b"", initial_value=int.from_bytes(iv, "big"))
    ct = enc.encrypt(priv)
    mac = keccak256(dk[16:32] + ct)
    ks_json = {"version": 3, "id": "00000000-0000-0000-0000-000000000000",
               "crypto": {"cipher": "aes-128-ctr", "cipherparams": {"iv": iv.hex()},
                          "ciphertext": ct.hex(), "kdf": "scrypt",
                          "kdfparams": {"dklen": 32, "n": n, "r": r, "p": p, "salt": salt.hex()},
                          "mac": mac.hex()}}
    path = "/tmp/_selftest_keystore.json"
    open(path, "w").write(json.dumps(ks_json))
    ks = load_keystore(path)
    print(f"[*] {ks['meta']}")
    # 字典里放一个接近的密码，验证不会误命中
    wl = "/tmp/_selftest_words.txt"
    open(wl, "w").write("password\n123456\nTest@2025\nTest@2026\n")
    for line in gen_candidates(wl, True):
        if check_pass(ks, line):
            print("[+] 自测通过：命中弱口令字典")
            return
    print("[-] 自测失败")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keystore")
    ap.add_argument("--wordlist")
    ap.add_argument("--rules", action="store_true")
    ap.add_argument("--mask")
    ap.add_argument("--export-hashcat", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest(); return
    if not args.keystore:
        ap.error("需要 --keystore")

    ks = load_keystore(args.keystore)
    print(f"[*] {ks['meta']}")
    print(f"[*] 盐 {ks['salt'].hex()}  密文 {len(ks['ct'])}B  mac {ks['mac'].hex()}")
    if args.export_hashcat:
        export_hashcat(ks); return
    if not args.wordlist and not args.mask:
        ap.error("需要 --wordlist 或 --mask")

    t0 = time.time(); tried = 0
    if args.wordlist:
        for pw in gen_candidates(args.wordlist, args.rules):
            tried += 1
            if check_pass(ks, pw):
                print(f"[+] 共试 {tried} 次，{time.time()-t0:.1f}s")
                return
    if args.mask:
        for pw in gen_mask(args.mask):
            tried += 1
            if check_pass(ks, pw):
                print(f"[+] 共试 {tried} 次，{time.time()-t0:.1f}s")
                return
    print(f"[-] 未命中（试了 {tried} 次，{time.time()-t0:.1f}s）")


if __name__ == "__main__":
    main()
