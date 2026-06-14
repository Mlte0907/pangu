# 盘古 — 部署与运维指南

## 1. Docker Compose 一键部署

```bash
# 1. 准备环境变量
cp .env.example .env
vim .env  # 填入 LLM_API_KEY 等

# 2. 启动服务
docker compose up -d

# 3. 验证
curl http://localhost:19528/health

# 4. 查看 Grafana
open http://localhost:3000
# 默认账号 admin / admin
```

## 2. 访问端点

| 服务 | 端口 | 用途 |
|:---|:---|:---|
| 盘古 API | 19528 | REST API、MCP、METRICS |
| Web UI | 8866 | 可选 Web 界面 |
| Prometheus | 9090 | 指标采集 |
| Grafana | 3000 | 可视化大盘 |

## 3. 监控告警

### 内置告警规则
- `PanguAPIDown` — API 不可用（critical）
- `PanguAPIHighErrorRate` — 5xx 错误率 > 5%
- `PanguAPISlowResponse` — P95 延迟 > 1s
- `PanguMemoryGrowthExplosion` — 记忆增长异常
- `PanguEmbedServiceDown` — 嵌入服务故障
- `PanguEmbedHighLatency` — 嵌入 P95 > 2s
- `PanguEngineErrorSpike` — 引擎错误率飙升
- `PanguEngineStuck` — 引擎运行超时

### 查看告警
```bash
# Prometheus 规则
curl http://localhost:9090/api/v1/rules

# 当前告警
curl http://localhost:9090/api/v1/alerts
```

## 4. 数据持久化

```bash
# 备份数据卷
docker run --rm \
  -v pangu_pangu_data:/data \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/pangu-data-$(date +%Y%m%d).tar.gz /data

# 恢复
docker run --rm \
  -v pangu_pangu_data:/data \
  -v $(pwd)/backup:/backup \
  alpine tar xzf /backup/pangu-data-20260101.tar.gz -C /
```

## 5. 升级

```bash
git pull
docker compose build
docker compose up -d
```

## 6. 故障排查

```bash
# 查看容器日志
docker logs pangu-api -f

# 进入容器
docker exec -it pangu-api bash

# 健康检查
docker inspect pangu-api | jq '.[0].State.Health'

# 资源占用
docker stats pangu-api
```
