# Droid Computer 管理指南

> 更新时间：2026-06-01

## 当前 Droid Computer 清单

| 名称 | ID | 类型 | 位置 |
|------|-----|------|------|
| busiji-mac-3 | d6cf2cd1-a7b8-4aad-a71f-ca89c90d2c33 | BYOM | 本机 |
| busiji-mac-2 | 18e815ea-22f2-4f4d-8d19-64ffeb8d005c | BYOM | Mac |
| node-22 | 313ac75f-0c3f-4893-81ae-a03807cd9ad5 | BYOM | 43.167.177.86 |

## 常用命令

```bash
# 列出所有 Droid Computer
droid computer list

# SSH 到远程 Droid Computer
droid computer ssh node-22

# 注册新机器为 BYOM
droid computer register <name>

# 取消注册
droid computer remove
```

## node-22 部署记录

1. 安装 droid: `curl -fsSL https://app.factory.ai/cli | sh`
2. 复制 auth 文件: `scp ~/.factory/auth.v2.{file,key} node-22:/root/.factory/`
3. 注册: `droid computer register node-22`
4. 启动 daemon: `droid daemon --remote-access`
5. 配置 systemd 自启: `/etc/systemd/system/droid-daemon.service`
6. 复制 BYOK 模型配置: `scp ~/.factory/settings.json node-22:/root/.factory/`

## Daemon systemd 配置

node-22 的 daemon 通过 systemd 管理，开机自启：

```ini
[Unit]
Description=Droid Daemon (Remote Access)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/root/.local/bin/droid daemon --remote-access
Restart=always
RestartSec=5
Environment=PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
```
