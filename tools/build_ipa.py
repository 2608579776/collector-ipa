#!/usr/bin/env python3
"""
build_ipa.py — 全自动：GitHub 建仓库 → 传代码 → 跑 Actions → 下 IPA

两种认证：
  --device-login      设备码登录（浏览器授权，不传 token）
  --token <PAT>       直接给 Personal Access Token（repo + workflow）

用法：
  python3 build_ipa.py --device-login --dir /path/to/collector
  python3 build_ipa.py --token ghp_xxx --dir /path/to/collector
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
# GitHub CLI 的公开 OAuth client，用于 device flow
CLIENT_ID = "178c6fc778ccc68e1d6a"
UA = "collector-build/1.0"


def req(url, token=None, method="GET", data=None, raw=False, headers=None):
    h = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            b = resp.read()
            return resp.status, (b if raw else json.loads(b.decode() or "{}"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="ignore")[:400]


def device_login():
    st, d = req("https://github.com/login/device/code",
                method="POST",
                headers={"Accept": "application/json",
                         "Content-Type": "application/x-www-form-urlencoded"},
                data=None) if False else (None, None)
    # 手工构造 form 请求
    form = urllib.parse.urlencode({"client_id": CLIENT_ID, "scope": "repo workflow"}).encode()
    r = urllib.request.Request("https://github.com/login/device/code", data=form,
                               headers={"Accept": "application/json",
                                        "Content-Type": "application/x-www-form-urlencoded",
                                        "User-Agent": UA})
    with urllib.request.urlopen(r, timeout=60) as resp:
        d = json.load(resp)
    print("\n" + "=" * 60)
    print("  在浏览器打开: " + d["verification_uri"])
    print("  输入代码    : " + d["user_code"])
    print("=" * 60 + "\n")
    interval = int(d.get("interval", 5))
    deadline = time.time() + int(d.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        form = urllib.parse.urlencode({"client_id": CLIENT_ID, "device_code": d["device_code"],
                                      "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}).encode()
        r = urllib.request.Request("https://github.com/login/oauth/access_token", data=form,
                                   headers={"Accept": "application/json",
                                            "Content-Type": "application/x-www-form-urlencoded",
                                            "User-Agent": UA})
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                tok = json.load(resp)
        except Exception as e:
            print("poll err", e); continue
        if tok.get("access_token"):
            print("[+] 授权成功")
            return tok["access_token"]
        err = tok.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5; continue
        print("[-] 授权失败:", tok); return None
    print("[-] 超时"); return None


def whoami(token):
    st, d = req(API + "/user", token)
    if st != 200:
        sys.exit(f"token 无效: {st} {d}")
    return d["login"]


def ensure_repo(token, owner, name):
    st, d = req(f"{API}/repos/{owner}/{name}", token)
    if st == 200:
        print(f"[=] 仓库已存在: {d['html_url']}"); return d
    st, d = req(f"{API}/user/repos", token, "POST",
                {"name": name, "private": True, "auto_init": False,
                 "description": "collector IPA build"})
    if st not in (200, 201):
        sys.exit(f"建仓库失败: {st} {d}")
    print(f"[+] 建仓库: {d['html_url']}")
    return d


def list_files(root):
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [x for x in dns if x not in (".git", "build", "Payload")]
        for fn in fns:
            if fn.endswith((".ipa", ".zip")) and "collector-github" not in fn:
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root).replace("\\", "/")
            out.append((p, rel))
    return out


def put_file(token, owner, repo, path, rel, branch="main", tries=3):
    data = open(path, "rb").read()
    payload = {"message": f"add {rel}", "content": base64.b64encode(data).decode(), "branch": branch}
    st, d = req(f"{API}/repos/{owner}/{repo}/contents/{urllib.parse.quote(rel)}",
                token, "PUT", payload)
    if st in (200, 201):
        return True
    print(f"  ! {rel} -> {st} {str(d)[:120]}")
    return False


def trigger(token, owner, repo):
    st, d = req(f"{API}/repos/{owner}/{repo}/actions/workflows/build-collector.yml/dispatches",
                token, "POST", {"ref": "main", "inputs": {}})
    if st not in (200, 204):
        sys.exit(f"触发失败: {st} {d}")
    print("[+] workflow 已触发")


def wait_run(token, owner, repo, timeout=1800):
    t0 = time.time()
    run_id = None
    while time.time() - t0 < timeout:
        st, d = req(f"{API}/repos/{owner}/{repo}/actions/runs?per_page=5", token)
        if st == 200 and d.get("workflow_runs"):
            for r in d["workflow_runs"]:
                if r.get("name") == "Collector · iOS 27 采集端" or r.get("path", "").endswith("build-collector.yml"):
                    if run_id is None:
                        run_id = r["id"]
                    if r["status"] == "completed":
                        print(f"[+] 运行完成: {r['conclusion']}  {r['html_url']}")
                        return run_id, r["conclusion"]
        time.sleep(10)
    print("[-] 等待超时"); return run_id, "timeout"


def download_artifact(token, owner, repo, run_id, outdir="/tmp/ipa_out"):
    os.makedirs(outdir, exist_ok=True)
    st, d = req(f"{API}/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts", token)
    if st != 200 or not d.get("artifacts"):
        print("[-] 没有 artifact"); return None
    art = d["artifacts"][0]
    url = art["archive_download_url"]
    st, blob = req(url, token, raw=True)
    if st != 200:
        print("[-] 下载失败", st, blob); return None
    zpath = os.path.join(outdir, "artifact.zip")
    open(zpath, "wb").write(blob)
    print(f"[+] artifact 已下载: {zpath} ({len(blob)} bytes)")
    import zipfile
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        z.extractall(outdir)
    ipa = None
    for dp, _, fns in os.walk(outdir):
        for fn in fns:
            if fn.endswith(".ipa"):
                ipa = os.path.join(dp, fn)
    print("[+] IPA:", ipa)
    return ipa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device-login", action="store_true")
    ap.add_argument("--token")
    ap.add_argument("--dir", required=True, help="collector 源码目录")
    ap.add_argument("--repo", default="collector")
    ap.add_argument("--out", default="/tmp/ipa_out")
    args = ap.parse_args()

    token = args.token
    if not token and args.device_login:
        token = device_login()
    if not token:
        sys.exit("需要 --token 或 --device-login")

    owner = whoami(token)
    print(f"[*] 登录用户: {owner}")
    repo = ensure_repo(token, owner, args.repo)

    files = list_files(args.dir)
    print(f"[*] 上传 {len(files)} 个文件")
    ok = 0
    for p, rel in files:
        if put_file(token, owner, args.repo, p, rel):
            ok += 1
    print(f"[+] 上传完成 {ok}/{len(files)}")

    trigger(token, owner, args.repo)
    run_id, concl = wait_run(token, owner, args.repo)
    if concl != "success":
        print("[-] 构建未成功，请到 Actions 页面看日志")
        print(f"    https://github.com/{owner}/{args.repo}/actions")
        return
    ipa = download_artifact(token, owner, args.repo, run_id, args.out)
    if ipa:
        print("\n===== 完成 =====")
        print("IPA:", ipa)


if __name__ == "__main__":
    main()
