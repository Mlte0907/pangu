# 部署指南

## 部署方式

### 方式 1: Docker Compose（推荐）

```bash
# 1. 克隆
git clone https://github.com/xiaoxin/pangu.git
cd pangu

# 2. 配置
cp .env.example .env
vim .env  # 填入 API 密钥

# 3. 启动
docker compose up -d

# 4. 验证
curl http://localhost:19528/health
```

### 方式 2: 单容器

```bash
docker run -d \
  --name pangu \
  -p 19528:19528 \
  -e PANGU_LLM_API_KEY=sk-xxxxx \
  -v pangu-data:/data \
  ghcr.io/xiaoxin/pangu:latest
```

### 方式 3: 源码部署

```bash
git clone https://github.com/xiaoxin/pangu.git
cd pangu
pip install -e .
pangu serve --host 0.0.0.0 --port 19528
```

## 端口说明

| 端口 | 服务 | 说明 |
|:---|:---|:---|
| 19528 | API + MCP + Metrics | 主端口 |
| 8866 | Web UI（可选） | 浏览器界面 |
| 9090 | Prometheus | 指标采集 |
| 3000 | Grafana | 可视化大盘 |

## 数据持久化

### Docker Volume

```yaml
# docker-compose.yml
volumes:
  - pangu_data:/data
```

### 备份

```bash
# 手动备份
docker run --rm \
  -v pangu_pangu_data:/data \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/pangu-$(date +%Y%m%d).tar.gz /data

# 自动备份（cron）
0 2 * * * /path/to/backup-script.sh
```

### 恢复

```bash
docker run --rm \
  -v pangu_pangu_data:/data \
  -v $(pwd)/backup:/backup \
  alpine tar xzf /backup/pangu-20260101.tar.gz -C /
```

## 多架构支持

盘古镜像支持 `linux/amd64` 和 `linux/arm64`：

```bash
# 自动选择（Apple Silicon / ARM 服务器）
docker pull ghcr.io/xiaoxin/pangu:latest

# 显式拉取
docker pull --platform linux/arm64 ghcr.io/xiaoxin/pangu:latest
```

## 反向代理（Nginx）

```nginx
server {
    listen 80;
    server_name pangu.example.com;

    location / {
        proxy_pass http://localhost:19528;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 支持
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

## HTTPS（Let's Encrypt）

```bash
certbot --nginx -d pangu.example.com
```

## Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pangu
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pangu
  template:
    metadata:
      labels:
        app: pangu
    spec:
      containers:
      - name: pangu
        image: ghcr.io/xiaoxin/pangu:v0.1.0
        ports:
        - containerPort: 19528
        env:
        - name: PANGU_LLM_API_KEY
          valueFrom:
            secretKeyRef:
              name: pangu-secrets
              key: llm-api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2"
        livenessProbe:
          httpGet:
            path: /health
            port: 19528
          initialDelaySeconds: 30
          periodSeconds: 30
        volumeMounts:
        - name: data
          mountPath: /data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: pangu-pvc
```

## 监控集成

详见 [监控指南](monitoring.md)。

## 性能调优

详见 [性能调优](performance.md)。

## 升级

```bash
# Docker Compose
docker compose pull
docker compose up -d

# 单容器
docker pull ghcr.io/xiaoxin/pangu:latest
docker stop pangu && docker rm pangu
docker run -d ... ghcr.io/xiaoxin/pangu:latest
```

## 故障排查

```bash
# 查看日志
docker logs pangu-api -f

# 健康检查
docker inspect pangu-api | jq '.[0].State.Health'

# 进入容器调试
docker exec -it pangu-api bash

# 资源占用
docker stats pangu-api
```
