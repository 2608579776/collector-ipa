#!/usr/bin/env python3
"""
gen_wordlist.py — 生成中文用户钱包弱口令字典

用法：
  python gen_wordlist.py > weak.txt
  python gen_wordlist.py --names 张伟,王芳,李娜 --dates 1980-2005 --out weak.txt

覆盖：
  - 通用弱口令 / 键盘序列 / 纯数字
  - 拼音姓名（全拼、首字母、加数字）
  - 生日：YYYYMMDD / YYMMDD / YYYYMM / MMDD
  - 吉利数字：520 / 1314 / 5201314 / 888 / 666 / 168
  - 钱包主题词：tp / tokenpocket / btc / eth / usdt / wallet / key
  - 组合变形：大小写、数字/符号后缀前缀、年份
"""
import argparse
import itertools
import sys

COMMON = """123456 12345678 123456789 111111 000000 666666 888888 123123 112233 121212
password passw0rd qwerty qwerty123 abc123 abc123456 iloveyou admin admin123 1q2w3e4r
1qaz2wsx 1qaz2wsx3edc zaq12wsx asdfgh zxcvbnm qwe123 a123456 aa123456 aA123456
woaini wangyi taobao alipay weixin wxid qq123456 aa123456789 5201314 1314520
520520 13141314 7758521 147258369 741852963 963852741 qazwsx qazwsxedc
123qwe 123qweasd zxc123 asd123 qweasdzxc 654321 987654321 555555 777777
88888888 168168 159357 246810 135790 102030 11111111 00000000"""

WALLET = """tp tokenpocket token pocket wallet wallet123 mywallet btc eth usdt trx bnb
metamask trust imtoken binance okx coinbase key privatekey seed mnemonic 123456tp
tp123456 tokenpocket123 wallet2024 wallet2025 wallet2026 btc2024 eth2024 usdt123"""

PINYIN = """zhangwei wangfang lina wangwei liwei zhangmin liujie chenjing yangyang
zhaolei huangwei zhoujie wuming wujun xujie sunli mawei zhujun hujun guojing
linfeng heping gaofeng luobin lucy tom jack michael jordan kobe messi ronaldo"""

GIVEN = """wei fang na jing jie min yan li juan xiu hua ping gang qiang lei jun
tao bin long peng hui feng lin yang yong qing xin yu hao ran chen xi"""

NUM_SUFFIX = ["", "0", "1", "123", "1234", "12345", "123456", "666", "888", "999",
              "520", "1314", "2023", "2024", "2025", "2026", "!"]
SYMBOLS = ["!", "@", "#", ".", "_", "..", "!@#", "@123", "123!"]


def birthday_range(start_year, end_year):
    for y in range(start_year, end_year + 1):
        for m, d in ((1, 1), (2, 14), (5, 20), (6, 1), (8, 8), (10, 1), (12, 25)):
            yield f"{y}{m:02d}{d:02d}"
            yield f"{str(y)[2:]}{m:02d}{d:02d}"
            yield f"{y}{m:02d}"
        yield str(y)
        yield f"{str(y)[2:]}"


def base_words(names):
    words = set()
    words.update(COMMON.split())
    words.update(WALLET.split())
    words.update(PINYIN.split())
    words.update(GIVEN.split())
    for n in names:
        words.add(n)
        words.add(n.lower())
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default="", help="额外姓名，逗号分隔（可用拼音）")
    ap.add_argument("--dates", default="1970-2010", help="生日年份范围，如 1980-2005")
    ap.add_argument("--out", default="-")
    ap.add_argument("--max", type=int, default=0, help="最多输出多少行（0=不限）")
    args = ap.parse_args()

    names = [x.strip() for x in args.names.split(",") if x.strip()]
    try:
        y0, y1 = (int(x) for x in args.dates.split("-"))
    except Exception:
        y0, y1 = 1970, 2010

    out = sys.stdout if args.out == "-" else open(args.out, "w", encoding="utf-8")
    seen = set()
    count = 0

    def emit(w):
        nonlocal count
        w = w.strip()
        if not w or w in seen:
            return False
        seen.add(w)
        out.write(w + "\n")
        count += 1
        return args.max and count >= args.max

    for w in sorted(base_words(names)):
        for suf in NUM_SUFFIX:
            if emit(w + suf):
                return
            if emit(w.capitalize() + suf):
                return
            if emit(w.upper() + suf):
                return
        for sym in SYMBOLS:
            if emit(w + sym):
                return
            if emit(w.capitalize() + sym):
                return

    for w in birthday_range(y0, y1):
        if emit(w):
            return
        for suf in ("!", "@", ".", "abc", "a"):
            if emit(w + suf):
                return

    for n in names:
        for g in GIVEN.split():
            for sep in ("", "_", ".", "-"):
                for suf in ("", "123", "1234", "520", "1314", "!"):
                    if emit(f"{n}{sep}{g}{suf}"):
                        return
                    if emit(f"{g}{sep}{n}{suf}"):
                        return

    if out is not sys.stdout:
        out.close()
    if args.out != "-":
        print(f"生成 {count} 条 → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
