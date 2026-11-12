# 没有 Mac 怎么打包（Windows 全流程）

> 目标：把 `collector/` 变成能装到 iPhone 的 IPA，全程不碰 Mac。
> 原理：**GitHub Actions 的 macOS runner 负责编译**（免费额度 2000 分钟/月，一次构建约 3–5 分钟），产出 **unsigned IPA**；**Windows 上的 AltStore/SideStores 负责签名安装**（用你的 Apple ID，免费 7 天有效）。

---

## 一、上传代码到 GitHub（不用命令行）

1. 打开 https://github.com/new ，建一个 **Private** 仓库，名字随意（如 `collector`）；
2. 进入仓库 → **Add file → Upload files**；
3. 把 `collector/` 文件夹里的**内容**拖进去（`Sources/`、`Bridge/`、`project.yml`、`Collector.entitlements`、`.github/`），Commit；
   - 注意：`.github` 是隐藏目录，Windows 资源管理器要勾"显示隐藏项目"；如果拖不上去，用 `git push` 或 GitHub 网页手动新建 `.github/workflows/build-collector.yml` 再粘贴内容。
4. 确认仓库根能看到 `project.yml`（workflow 会自动识别"根目录"或"collector/ 子目录"两种布局）。

## 二、在 Actions 里构建

1. 仓库 → **Actions** 标签 → 左侧 `build-collector` → 右侧 **Run workflow**；
2. Bundle ID 留空（默认 `com.example.collector`）或改成你自己的（如 `com.yourname.collector`）；
3. 等 3–5 分钟，构建完成 → 点进这次 run → 底部 **Artifacts** 下载 `collector-unsigned-ipa`（一个 zip，里面是 `collector-unsigned.ipa`）。

常见失败：
- `找不到 project.yml` → 文件没传上去（`.github` 被忽略），检查仓库根；
- `xcodebuild: error: scheme Collector not found` → `project.yml` 里 scheme 段被改坏，恢复默认；
- 编译报 Swift 错误 → 把 Actions 日志贴给我，我改代码。

## 三、Windows 上签名安装（两选一）

### 方案 A：AltStore（推荐，图形化）

1. 装 [AltServer](https://altstore.io/)（Windows 版），同时装 iTunes（Microsoft Store 版）和 iCloud；
2. iPhone 用数据线连电脑，信任此电脑；
3. AltServer 托盘图标 → **Install AltStore → 选你的 iPhone**，输入 **Apple ID + 密码**（会走双重认证，需要 App 专用密码或弹窗确认）；
4. 手机上出现 AltStore，设置 → 通用 → VPN与设备管理 → 信任你的开发者证书；
5. 把 `collector-unsigned.ipa` 传到手机（AirDrop/微信/iCloud 均可），在 AltStore → **My Apps → 左上角 +** → 选这个 IPA → 自动用同一个 Apple ID 签名安装；
6. **App Group**：AltStore 签名时会自动补上 `group.<bundleid>` 这类 App Group（社区实测 WQ Files 就是这么跑起来的），装好后打开 collector，App Group 填 `group.com.example.collector`（或 Bundle ID 对应的那个）。

### 方案 B：SideStore / Sideloadly

- **Sideloadly**：Windows 装好后拖入 IPA，填 Apple ID，勾选 "Enable app groups"（如果有），Start；
- **SideStore**：需要先在同一台 Windows 上生成 pairing file（jitterbugpair），再配 WireGuard，步骤多但可无线续签。

> 免费 Apple ID 的限制：**7 天过期**、最多 3 个 App、同一周最多 10 个 App ID。到期重签一次即可（AltStore 会自动提醒）。

## 四、装好后先验证，再谈采集

打开 collector：

1. **① 测试沙盒逃逸** → 期望打印 `✅ 扩展句柄 = <正数>`；
   - `-1` = App Group 不存在/不可访问 → 把 App Group 改成实际签名生成的那个（AltStore 里能看到）；
   - `-2` = 私有符号解析失败 → 系统版本不在 worse_query 支持范围；
   - `-5/-6` = 容器管理器/内核拒绝 → 该 build 可能已修，或 flag 需要调（`worse_query.m` 的 `alt_flags`）。
2. **② 枚举容器** → 出现 bundle id 列表（第一次较慢，inode 爆破）；
3. **③ 读取并上传** → C2 填 `https://<你的 C2 隧道域名>`，后台「设备管理」会出现 `is_controlled=1` 的设备与 `container-*` 文件。

## 五、不想打包的替代方案

**WQ Files**（社区现成、同样基于 worse_query、AltStore 可装）：先用它确认这台机器上的逃逸是否成立、能看到哪些 App 的容器。
它没有自动回传；确认逃逸可用之后，再回来签 collector 做自动化。

## 六、这条路的边界

- 只能读**其他 App 容器**（Documents/Library），拿不到 Keychain/内核；
- 27.2.1 是否 100% 可用：上游 README 写到 27.2，Erosion 列到 27.2.1，苹果 27.2.1 安全说明没提沙盒修复 → **大概率可用，但要靠你 ① 那一步实测确认**。
