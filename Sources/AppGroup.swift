//
//  AppGroup.swift — 解析 AltStore/SideStore 实际授予的 App Group
//
import Foundation

enum AppGroup {
    /// 从 embedded.mobileprovision 读出 profile 里的应用组
    static func profileGroups() -> [String] {
        guard let url = Bundle.main.url(forResource: "embedded", withExtension: "mobileprovision"),
              let data = try? Data(contentsOf: url),
              let text = String(data: data, encoding: .isoLatin1),
              let s = text.range(of: "<?xml"),
              let e = text.range(of: "</plist>"),
              let d = String(text[s.lowerBound..<e.upperBound]).data(using: .isoLatin1),
              let obj = try? PropertyListSerialization.propertyList(from: d, options: [], format: nil),
              let plist = obj as? [String: Any],
              let ent = plist["Entitlements"] as? [String: Any],
              let gs = ent["com.apple.security.application-groups"] as? [String] else {
            return []
        }
        return gs
    }

    /// 候选名单：profile 原值 + group.<bundle> + 去掉团队后缀的变体
    static func candidates() -> [String] {
        var out = profileGroups()
        let bid = Bundle.main.bundleIdentifier ?? "com.94zero.collector"
        out.append("group." + bid)
        out.append("group.com.94zero.collector")
        for g in profileGroups() {
            let parts = g.split(separator: ".").map(String.init)
            if parts.count > 3, parts.first == "group" {
                out.append(parts.dropLast().joined(separator: "."))
            }
        }
        var seen = Set<String>()
        return out.filter { seen.insert($0).inserted && !$0.isEmpty }
    }

    /// 返回第一个真正可用的 group，以及尝试过的全部候选
    static func resolve() -> (group: String?, tried: [String]) {
        let list = candidates()
        for g in list where FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: g) != nil {
            return (g, list)
        }
        return (nil, list)
    }
}
