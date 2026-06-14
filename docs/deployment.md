# 部署指南

## 1. 单机部署（systemd）

`/etc/systemd/system/pangu.service`：

```ini
[Unit]
Description=Pangu Memory Server
After=network.target

[Service]
Type=simple
User=pangu
Group=pangu
WorkingDirectory=/opt/pangu
Environment="PANGU_DATA_DIR=/var/lib/pangu"
Environment="PANGU_API_KEY=replace-with-strong-secret"  # 可选
ExecStart=/opt/pangu/.venv/bin/pangu-server
Restart=on-failure
RestartSec=5

# 资源限制
MemoryMax=2G
TasksMax=512

# 安全
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/pangu

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pangu
sudo journalctl -u pangu -f
```

## 2. Docker Compose

`docker-compose.yml`：

```yaml
version: '3.9'
services:
  pangu:
    image: pangu/pangu:0.1.0
    ports:
      - "127.0.0.1:19528:19528"  # 仅本机
    volumes:
      - pangu-data:/var/lib/pangu
    environment:
      - PANGU_DATA_DIR=/var/lib/pangu
      - PANGU_API_KEY=${PANGU_API_KEY}
      - PANGU_LLM_API_KEY=${PANGU_LLM_API_KEY}
      - PANGU_LLM_BASE_URL=${PANGU_LLM_BASE_URL}
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:19528/health"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  pangu-data:
```

## 3. 反向代理（Nginx）

`/etc/nginx/sites-available/pangu.conf`：

```nginx
upstream pangu_backend {
  server 127.0.0.1:19528;
  keepalive 16;
}

server {
  listen 443 ssl http2;
  server_name pangu.example.com;

  ssl_certificate     /etc/letsencrypt/live/pangu.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/pangu.example.com/privkey.pem;

  # 限流
  limit_req_zone $binary_remote_addr zone=pangu:10m rate=20r/s;
  limit_req zone=pangu burst=40 nodelay;

  location / {
    proxy_pass http://pangu_backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
  }

  # 拒绝外部访问文档
  location ~ ^/(docs|openapi\.json|redoc) {
    allow 10.0.0.0/8;     # 内部网段
    deny all;
    proxy_pass http://pangu_backend;
  }
}
```

## 4. 数据卷

```
/var/lib/pangu/
├── palace/        # 宫殿结构
├── wiki/          # Wiki 引擎
├── identity/      # L0 身份
├── cache/         # 持久化 LLM 缓存
│   └── cache.sqlite
├── vector/        # ChromaDB
└── kg.sqlite      # 知识图谱
```

**重要**：定期备份整个目录，或使用 `pangu-cli export`。

## 5. 横向扩展（v0.3+）

- 当前版本：单实例；SQLite + ChromaDB 本地存储
- v0.3.0：支持 PostgreSQL 后端 + 分布式 ChromaDB
- v0.9.0：内置只读副本

## 6. 健康检查清单

| 检查项 | 命令 | 期望 |
|:---|:---|:---|
| 进程存活 | `systemctl is-active pangu` | active |
| HTTP 200 | `curl /health` | `{"code":0,...}` |
| 数据可写 | `pangu-cli write-test` | OK |
| 磁盘空间 | `df -h /var/lib/pangu` | < 80% |
| 内存 | `systemctl status pangu` | < 1.5 GB |
