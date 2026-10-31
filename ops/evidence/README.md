# 部署证据归档

> 用于存放 `ops/部署硬检查清单.md` 里每条打勾所需的**服务器实际输出**。

## 规矩

1. **只放证据，不放密钥**：命令输出里如果带口令，先用 `<略>` 替换再存。
2. 文件名与清单编号对应，例如清单 §1.1.2 → `1.1.2-oss-lifecycle.txt`。
3. 同一份证据更新时**追加**不复写，保留历史（`1.2.4-log-persist-2026-11-01.txt`）。
4. 截图放 `png/` 子目录。

## 预期文件清单（部署时逐个填补）

| 文件 | 对应清单项 | 内容 |
| --- | --- | --- |
| `1.1.2-oss-lifecycle.txt` | §1.1.2 | `ossutil lifecycle get` 输出 |
| `1.1.5-oss-ttl-proof.txt` | §1.1.5 | 当日/次日 `ossutil ls` 对比 |
| `1.2.2-api-mounts.json` | §1.2.2 | `docker inspect` 的 Mounts 段 |
| `1.2.4-log-persist-proof.txt` | §1.2.4 | 重建容器前后日志目录对比 |
| `1.3.2-sls-retention.json` | §1.3.2 | 三个 Logstore 的 ttl |
| `4.5-admin-blocked.txt` | §4.5 | 外部 IP 访问后台被拒 |
| `4.7-port-closed.txt` | §4.7 | 3306/6379 公网不可达 |
| `5.4-restore-drill.txt` | §5.4 | 恢复演练记录 |

> 本目录在部署前为空是正常的；**空了就是没部署**，不许拿本文件充当证据。
