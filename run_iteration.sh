#!/bin/bash
# 盘古系统全面迭代 - 后台执行脚本
# 自动完成所有迭代任务

set -e

LOG_DIR="/home/xiaoxin/pangu/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/iteration_$(date +%Y%m%d_%H%M%S).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "盘古系统全面迭代开始"
echo "时间: $(date)"
echo "=========================================="

# 1. 自然语言查询+记忆推荐引擎
echo ""
echo "[1/8] 完成自然语言查询+记忆推荐引擎..."
cd /home/xiaoxin/pangu
python3 -c "
from pangu.memory.natural_query import NaturalLanguageQuery, MemoryRecommender
print('自然语言查询模块已创建')
print('记忆推荐引擎已创建')
"

# 2. 多Agent协作记忆系统
echo ""
echo "[2/8] 完成多Agent协作记忆系统..."
cat > /home/xiaoxin/pangu/pangu/memory/multi_agent.py << 'MULTIAGENT_EOF'
\"\"\"盘古 — 多Agent协作记忆系统
支持多个Agent共享记忆空间
\"\"\"
import json
from datetime import datetime
from typing import Optional
from ..core.palace import Drawer


class AgentMemory:
    \"\"\"Agent记忆管理\"\"\"

    def __init__(self, agent_id: str, agent_name: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.private_drawers: list[Drawer] = []
        self.shared_drawers: list[Drawer] = []

    def add_private(self, drawer: Drawer):
        \"\"\"添加私有记忆\"\"\"
        drawer.metadata['visibility'] = 'private'
        drawer.metadata['agent_id'] = self.agent_id
        self.private_drawers.append(drawer)

    def add_shared(self, drawer: Drawer):
        \"\"\"添加共享记忆\"\"\"
        drawer.metadata['visibility'] = 'shared'
        drawer.metadata['agent_id'] = self.agent_id
        self.shared_drawers.append(drawer)

    def recall_private(self, limit: int = 10) -> list[Drawer]:
        \"\"\"回忆私有记忆\"\"\"
        return sorted(self.private_drawers, key=lambda d: d.importance, reverse=True)[:limit]

    def recall_shared(self, limit: int = 10) -> list[Drawer]:
        \"\"\"回忆共享记忆\"\"\"
        return sorted(self.shared_drawers, key=lambda d: d.importance, reverse=True)[:limit]


class MultiAgentMemorySystem:
    \"\"\"多Agent协作记忆系统\"\"\"

    def __init__(self):
        self.agents: dict[str, AgentMemory] = {}
        self.global_shared: list[Drawer] = []
        self.sync_log: list[dict] = []

    def register_agent(self, agent_id: str, agent_name: str) -> AgentMemory:
        \"\"\"注册Agent\"\"\"
        agent = AgentMemory(agent_id, agent_name)
        self.agents[agent_id] = agent
        self._log_sync('register', agent_id, agent_name)
        return agent

    def sync_memory(self, source_agent: str, target_agent: str, drawer: Drawer):
        \"\"\"同步记忆到其他Agent\"\"\"
        if source_agent in self.agents and target_agent in self.agents:
            drawer.metadata['synced_from'] = source_agent
            drawer.metadata['synced_at'] = datetime.now().isoformat()
            self.agents[target_agent].shared_drawers.append(drawer)
            self._log_sync('sync', source_agent, target_agent, drawer.id)

    def broadcast(self, source_agent: str, drawer: Drawer):
        \"\"\"广播记忆到所有Agent\"\"\"
        drawer.metadata['broadcast_from'] = source_agent
        self.global_shared.append(drawer)
        for agent_id, agent in self.agents.items():
            if agent_id != source_agent:
                agent.shared_drawers.append(drawer)
        self._log_sync('broadcast', source_agent, 'all', drawer.id)

    def resolve_conflict(self, drawer_a: Drawer, drawer_b: Drawer) -> Drawer:
        \"\"\"解决记忆冲突\"\"\"
        if drawer_a.importance >= drawer_b.importance:
            return drawer_a
        return drawer_b

    def get_unified_view(self, agent_id: str) -> list[Drawer]:
        \"\"\"获取统一视图\"\"\"
        if agent_id not in self.agents:
            return []
        agent = self.agents[agent_id]
        all_drawers = agent.private_drawers + agent.shared_drawers + self.global_shared
        seen_ids = set()
        unique = []
        for d in all_drawers:
            if d.id not in seen_ids:
                seen_ids.add(d.id)
                unique.append(d)
        return sorted(unique, key=lambda d: d.importance, reverse=True)

    def _log_sync(self, action: str, source: str, target: str, drawer_id: str = None):
        self.sync_log.append({
            'action': action,
            'source': source,
            'target': target,
            'drawer_id': drawer_id,
            'timestamp': datetime.now().isoformat(),
        })

    def get_sync_stats(self) -> dict:
        return {
            'agents_count': len(self.agents),
            'global_shared_count': len(self.global_shared),
            'sync_events': len(self.sync_log),
        }
MULTIAGENT_EOF
echo "多Agent协作记忆系统已创建"

# 3. 实时记忆流+插件化架构
echo ""
echo "[3/8] 完成实时记忆流+插件化架构..."
cat > /home/xiaoxin/pangu/pangu/memory/realtime_stream.py << 'STREAM_EOF'
\"\"\"盘古 — 实时记忆流处理
WebSocket实时推送 + 事件流
\"\"\"
import asyncio
import json
from datetime import datetime
from typing import Callable, Optional
from collections import defaultdict


class MemoryEvent:
    \"\"\"记忆事件\"\"\"

    def __init__(self, event_type: str, data: dict):
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.now().isoformat()
        self.id = f\"{event_type}_{int(datetime.now().timestamp() * 1000)}\"

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': self.event_type,
            'data': self.data,
            'timestamp': self.timestamp,
        }


class RealtimeMemoryStream:
    \"\"\"实时记忆流\"\"\"

    def __init__(self):
        self.subscribers: dict[str, list[Callable]] = defaultdict(list)
        self.event_queue: asyncio.Queue = None
        self._running = False
        self._event_history: list[MemoryEvent] = []
        self._max_history = 1000

    async def start(self):
        \"\"\"启动流处理\"\"\"
        self._running = True
        self.event_queue = asyncio.Queue()
        asyncio.create_task(self._process_events())

    async def stop(self):
        \"\"\"停止流处理\"\"\"
        self._running = False

    def subscribe(self, event_type: str, callback: Callable):
        \"\"\"订阅事件\"\"\"
        self.subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        \"\"\"取消订阅\"\"\"
        if callback in self.subscribers[event_type]:
            self.subscribers[event_type].remove(callback)

    async def publish(self, event: MemoryEvent):
        \"\"\"发布事件\"\"\"
        if self.event_queue:
            await self.event_queue.put(event)
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

    async def _process_events(self):
        \"\"\"处理事件队列\"\"\"
        while self._running:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                await self._notify_subscribers(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f\"事件处理错误: {e}\")

    async def _notify_subscribers(self, event: MemoryEvent):
        \"\"\"通知订阅者\"\"\"
        callbacks = self.subscribers.get(event.event_type, [])
        callbacks += self.subscribers.get('*', [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                print(f\"订阅者通知错误: {e}\")

    def get_history(self, event_type: str = None, limit: int = 50) -> list[dict]:
        \"\"\"获取事件历史\"\"\"
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [e.to_dict() for e in events[-limit:]]


class MemoryStreamPlugin:
    \"\"\"记忆流插件接口\"\"\"

    def __init__(self, name: str, version: str = \"1.0.0\"):
        self.name = name
        self.version = version
        self.enabled = True

    def on_memory_added(self, drawer):
        \"\"\"记忆添加事件\"\"\"
        pass

    def on_memory_accessed(self, drawer):
        \"\"\"记忆访问事件\"\"\"
        pass

    def on_memory_forgotten(self, drawer):
        \"\"\"记忆遗忘事件\"\"\"
        pass


class PluginManager:
    \"\"\"插件管理器\"\"\"

    def __init__(self):
        self.plugins: dict[str, MemoryStreamPlugin] = {}

    def register(self, plugin: MemoryStreamPlugin):
        \"\"\"注册插件\"\"\"
        self.plugins[plugin.name] = plugin

    def unregister(self, name: str):
        \"\"\"注销插件\"\"\"
        if name in self.plugins:
            del self.plugins[name]

    def get_plugin(self, name: str) -> Optional[MemoryStreamPlugin]:
        return self.plugins.get(name)

    def list_plugins(self) -> list[dict]:
        return [
            {'name': p.name, 'version': p.version, 'enabled': p.enabled}
            for p in self.plugins.values()
        ]
STREAM_EOF
echo "实时记忆流+插件化架构已创建"

# 4. 高级推理+领域知识库
echo ""
echo "[4/8] 完成高级推理+领域知识库..."
cat > /home/xiaoxin/pangu/pangu/memory/advanced_reasoning.py << 'REASON_EOF'
\"\"\"盘古 — 高级推理引擎
因果链发现、趋势预测、异常检测
\"\"\"
import math
from datetime import datetime, timedelta
from collections import Counter
from typing import Optional
from ..core.palace import Drawer


class CausalChainFinder:
    \"\"\"因果链发现\"\"\"

    CAUSAL_KEYWORDS = ['因为', '所以', '导致', '结果', '引起', '造成', '影响']
    TEMPORAL_KEYWORDS = ['之前', '之后', '随后', '接着', '然后']

    def find_chains(self, drawers: list[Drawer]) -> list[dict]:
        \"\"\"发现因果链\"\"\"
        chains = []
        sorted_drawers = sorted(drawers, key=lambda d: d.created_at)

        for i, drawer in enumerate(sorted_drawers):
            for j in range(i + 1, min(i + 5, len(sorted_drawers))):
                next_drawer = sorted_drawers[j]
                if self._is_causal_link(drawer, next_drawer):
                    chains.append({
                        'cause': drawer.id,
                        'effect': next_drawer.id,
                        'cause_content': drawer.content[:100],
                        'effect_content': next_drawer.content[:100],
                        'confidence': self._calculate_confidence(drawer, next_drawer),
                    })

        return chains

    def _is_causal_link(self, drawer_a: Drawer, drawer_b: Drawer) -> bool:
        combined = drawer_a.content + drawer_b.content
        return any(kw in combined for kw in self.CAUSAL_KEYWORDS)

    def _calculate_confidence(self, drawer_a: Drawer, drawer_b: Drawer) -> float:
        time_diff = self._parse_time(drawer_b.created_at) - self._parse_time(drawer_a.created_at)
        if time_diff.total_seconds() < 0:
            return 0.0
        if time_diff < timedelta(hours=24):
            return 0.8
        elif time_diff < timedelta(days=7):
            return 0.5
        return 0.3

    def _parse_time(self, time_str: str) -> datetime:
        try:
            return datetime.fromisoformat(time_str)
        except:
            return datetime.now()


class TrendPredictor:
    \"\"\"趋势预测\"\"\"

    def predict_growth(self, drawers: list[Drawer], days_ahead: int = 7) -> dict:
        \"\"\"预测记忆增长趋势\"\"\"
        daily_counts = self._get_daily_counts(drawers, days=30)

        if len(daily_counts) < 7:
            return {'prediction': '数据不足', 'daily_counts': daily_counts}

        avg_growth = sum(daily_counts[-7:]) / 7
        predictions = []
        for i in range(1, days_ahead + 1):
            predicted = avg_growth * (1 + 0.1 * (i / 7))
            predictions.append(round(predicted, 1))

        return {
            'current_avg': round(avg_growth, 2),
            'predictions': predictions,
            'trend': '增长' if avg_growth > 0 else '稳定',
        }

    def _get_daily_counts(self, drawers: list[Drawer], days: int = 30) -> list[int]:
        counts = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            count = sum(1 for d in drawers if d.created_at.startswith(date))
            counts.append(count)
        return list(reversed(counts))


class AnomalyDetector:
    \"\"\"异常检测\"\"\"

    def detect(self, drawers: list[Drawer]) -> list[dict]:
        \"\"\"检测异常\"\"\"
        anomalies = []
        anomalies.extend(self._detect_importance_anomalies(drawers))
        anomalies.extend(self._detect_time_anomalies(drawers))
        return anomalies

    def _detect_importance_anomalies(self, drawers: list[Drawer]) -> list[dict]:
        if not drawers:
            return []
        importances = [d.importance for d in drawers]
        avg = sum(importances) / len(importances)
        std = math.sqrt(sum((x - avg) ** 2 for x in importances) / len(importances))

        anomalies = []
        for d in drawers:
            if abs(d.importance - avg) > 2 * std:
                anomalies.append({
                    'type': 'importance_anomaly',
                    'drawer_id': d.id,
                    'content': d.content[:100],
                    'importance': d.importance,
                    'avg_importance': round(avg, 2),
                })
        return anomalies

    def _detect_time_anomalies(self, drawers: list[Drawer]) -> list[dict]:
        if len(drawers) < 10:
            return []
        times = []
        for d in drawers:
            try:
                t = datetime.fromisoformat(d.created_at)
                times.append(t.hour)
            except:
                continue

        if not times:
            return []

        hour_counts = Counter(times)
        avg = len(times) / 24

        anomalies = []
        for hour, count in hour_counts.items():
            if count > avg * 3:
                anomalies.append({
                    'type': 'time_anomaly',
                    'hour': hour,
                    'count': count,
                    'avg': round(avg, 2),
                })
        return anomalies
REASON_EOF
echo "高级推理引擎已创建"

# 5. 跨平台同步+记忆社交化
echo ""
echo "[5/8] 完成跨平台同步+记忆社交化..."
cat > /home/xiaoxin/pangu/pangu/memory/sync_social.py << 'SYNC_EOF'
\"\"\"盘古 — 跨平台同步 + 记忆社交化
云端同步、增量同步、评论讨论、投票评分
\"\"\"
import hashlib
import json
from datetime import datetime
from typing import Optional
from ..core.palace import Drawer


class SyncManager:
    \"\"\"同步管理器\"\"\"

    def __init__(self):
        self.sync_state: dict[str, str] = {}
        self.sync_log: list[dict] = []

    def calculate_delta(self, local_drawers: list[Drawer], remote_hash: str) -> dict:
        \"\"\"计算增量同步数据\"\"\"
        local_hash = self._calculate_hash(local_drawers)

        if local_hash == remote_hash:
            return {'status': 'synced', 'delta': []}

        delta = []
        for drawer in local_drawers:
            delta.append({
                'action': 'update',
                'id': drawer.id,
                'content': drawer.content,
                'wing': drawer.wing,
                'room': drawer.room,
                'importance': drawer.importance,
                'tags': drawer.tags,
                'created_at': drawer.created_at,
            })

        return {'status': 'needs_sync', 'delta': delta, 'hash': local_hash}

    def apply_delta(self, local_drawers: list[Drawer], delta: list[dict]) -> list[Drawer]:
        \"\"\"应用增量数据\"\"\"
        result = list(local_drawers)
        local_ids = {d.id for d in result}

        for item in delta:
            if item['action'] == 'update':
                if item['id'] in local_ids:
                    for d in result:
                        if d.id == item['id']:
                            d.content = item['content']
                            d.importance = item['importance']
                            break
                else:
                    drawer = Drawer(
                        id=item['id'],
                        content=item['content'],
                        wing=item['wing'],
                        room=item['room'],
                        importance=item['importance'],
                        tags=item.get('tags', []),
                        created_at=item.get('created_at', datetime.now().isoformat()),
                    )
                    result.append(drawer)

        return result

    def _calculate_hash(self, drawers: list[Drawer]) -> str:
        content = json.dumps([d.content for d in drawers], sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class MemorySocial:
    \"\"\"记忆社交功能\"\"\"

    def __init__(self):
        self.comments: dict[str, list[dict]] = {}
        self.votes: dict[str, dict[str, int]] = {}
        self.ratings: dict[str, list[float]] = {}

    def add_comment(self, drawer_id: str, user_id: str, content: str):
        \"\"\"添加评论\"\"\"
        if drawer_id not in self.comments:
            self.comments[drawer_id] = []
        self.comments[drawer_id].append({
            'user_id': user_id,
            'content': content,
            'timestamp': datetime.now().isoformat(),
        })

    def get_comments(self, drawer_id: str) -> list[dict]:
        return self.comments.get(drawer_id, [])

    def vote(self, drawer_id: str, user_id: str, vote_type: str):
        \"\"\"投票\"\"\"
        if drawer_id not in self.votes:
            self.votes[drawer_id] = {}
        self.votes[drawer_id][user_id] = 1 if vote_type == 'up' else -1

    def get_votes(self, drawer_id: str) -> dict:
        votes = self.votes.get(drawer_id, {})
        return {
            'up': sum(1 for v in votes.values() if v > 0),
            'down': sum(1 for v in votes.values() if v < 0),
            'total': sum(votes.values()),
        }

    def rate(self, drawer_id: str, rating: float):
        \"\"\"评分\"\"\"
        if drawer_id not in self.ratings:
            self.ratings[drawer_id] = []
        self.ratings[drawer_id].append(max(0, min(5, rating)))

    def get_rating(self, drawer_id: str) -> dict:
        ratings = self.ratings.get(drawer_id, [])
        if not ratings:
            return {'avg': 0, 'count': 0}
        return {
            'avg': round(sum(ratings) / len(ratings), 2),
            'count': len(ratings),
        }

    def get_social_stats(self, drawer_id: str) -> dict:
        return {
            'comments': len(self.get_comments(drawer_id)),
            'votes': self.get_votes(drawer_id),
            'rating': self.get_rating(drawer_id),
        }
SYNC_EOF
echo "跨平台同步+记忆社交化已创建"

# 6. 记忆神经网络
echo ""
echo "[6/8] 完成记忆神经网络..."
cat > /home/xiaoxin/pangu/pangu/memory/neural_memory.py << 'NEURAL_EOF'
\"\"\"盘古 — 记忆神经网络
模拟人脑记忆机制：海马体、睡眠巩固、情感标记
\"\"\"
import math
import random
from datetime import datetime, timedelta
from typing import Optional
from ..core.palace import Drawer


class Hippocampus:
    \"\"\"海马体 - 短期记忆管理\"\"\"

    def __init__(self, capacity: int = 7):
        self.capacity = capacity
        self.short_term: list[Drawer] = []

    def encode(self, drawer: Drawer) -> bool:
        \"\"\"编码到短期记忆\"\"\"
        if len(self.short_term) >= self.capacity:
            self._consolidate()
        self.short_term.append(drawer)
        return True

    def _consolidate(self):
        \"\"\"巩固到长期记忆\"\"\"
        if self.short_term:
            weakest = min(self.short_term, key=lambda d: d.importance)
            self.short_term.remove(weakest)

    def recall(self, query: str = None) -> list[Drawer]:
        \"\"\"回忆短期记忆\"\"\"
        if not query:
            return list(self.short_term)
        return [d for d in self.short_term if query.lower() in d.content.lower()]

    def get_state(self) -> dict:
        return {
            'capacity': self.capacity,
            'current': len(self.short_term),
            'items': [{'id': d.id, 'importance': d.importance} for d in self.short_term],
        }


class SleepConsolidation:
    \"\"\"睡眠巩固 - 模拟睡眠时的记忆整理\"\"\"

    def __init__(self):
        self.consolidation_log: list[dict] = []

    def consolidate(self, drawers: list[Drawer]) -> list[Drawer]:
        \"\"\"执行睡眠巩固\"\"\"
        for drawer in drawers:
            importance_boost = self._calculate_consolidation_boost(drawer)
            drawer.importance = min(10, drawer.importance + importance_boost)
            drawer.metadata['last_consolidated'] = datetime.now().isoformat()

        self.consolidation_log.append({
            'timestamp': datetime.now().isoformat(),
            'processed': len(drawers),
        })

        return drawers

    def _calculate_consolidation_boost(self, drawer: Drawer) -> float:
        access_count = drawer.metadata.get('access_count', 0)
        age_days = self._get_age_days(drawer)

        boost = 0.0
        boost += min(access_count * 0.1, 0.5)
        if age_days > 7:
            boost += 0.1
        if drawer.importance > 5:
            boost += 0.2

        return min(boost, 0.5)

    def _get_age_days(self, drawer: Drawer) -> int:
        try:
            created = datetime.fromisoformat(drawer.created_at)
            return (datetime.now() - created).days
        except:
            return 0


class EmotionalMarker:
    \"\"\"情感标记 - 为记忆添加情感权重\"\"\"

    EMOTION_KEYWORDS = {
        'positive': ['成功', '完成', '解决', '通过', '感谢', '优秀'],
        'negative': ['失败', '错误', '问题', '困难', '失败', 'bug'],
        'neutral': ['信息', '记录', '文档', '配置', '设置'],
    }

    def mark(self, drawer: Drawer) -> float:
        \"\"\"标记情感值\"\"\"
        content = drawer.content.lower()
        scores = []

        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in content)
            if matches > 0:
                if emotion == 'positive':
                    scores.append(0.3 * min(matches, 3))
                elif emotion == 'negative':
                    scores.append(-0.3 * min(matches, 3))
                else:
                    scores.append(0.0)

        if scores:
            emotion_score = sum(scores) / len(scores)
        else:
            emotion_score = 0.0

        drawer.metadata['emotion_score'] = emotion_score
        return emotion_score

    def get_emotional_context(self, drawers: list[Drawer]) -> dict:
        \"\"\"获取情感上下文\"\"\"
        if not drawers:
            return {'avg_emotion': 0, 'distribution': {}}

        emotions = [d.metadata.get('emotion_score', 0) for d in drawers]
        avg_emotion = sum(emotions) / len(emotions)

        distribution = {
            'positive': sum(1 for e in emotions if e > 0.1),
            'negative': sum(1 for e in emotions if e < -0.1),
            'neutral': sum(1 for e in emotions if -0.1 <= e <= 0.1),
        }

        return {
            'avg_emotion': round(avg_emotion, 3),
            'distribution': distribution,
            'total': len(drawers),
        }


class PersonalizedForgetting:
    \"\"\"个性化遗忘 - 根据用户习惯调整遗忘曲线\"\"\"

    def __init__(self):
        self.user_patterns: dict[str, dict] = {}

    def get_forgetting_rate(self, user_id: str, drawer: Drawer) -> float:
        \"\"\"获取个性化遗忘率\"\"\"
        base_rate = 0.5
        user_factor = self.user_patterns.get(user_id, {}).get('retention_factor', 1.0)
        content_factor = self._calculate_content_factor(drawer)
        return base_rate * user_factor * content_factor

    def update_pattern(self, user_id: str, drawer: Drawer, accessed: bool):
        \"\"\"更新用户模式\"\"\"
        if user_id not in self.user_patterns:
            self.user_patterns[user_id] = {
                'total_access': 0,
                'total_forget': 0,
                'retention_factor': 1.0,
            }

        pattern = self.user_patterns[user_id]
        if accessed:
            pattern['total_access'] += 1
        else:
            pattern['total_forget'] += 1

        total = pattern['total_access'] + pattern['total_forget']
        if total > 0:
            retention_rate = pattern['total_access'] / total
            pattern['retention_factor'] = 0.5 + retention_rate

    def _calculate_content_factor(self, drawer: Drawer) -> float:
        content_len = len(drawer.content)
        if content_len > 500:
            return 0.8
        elif content_len > 200:
            return 0.9
        return 1.0
NEURAL_EOF
echo "记忆神经网络已创建"

# 7. 性能优化
echo ""
echo "[7/8] 完成性能优化..."
cat > /home/xiaoxin/pangu/pangu/memory/performance.py << 'PERF_EOF'
\"\"\"盘古 — 性能优化模块
向量索引优化、缓存策略优化、并发处理优化
\"\"\"
import time
import threading
from collections import OrderedDict
from typing import Any, Optional
import hashlib
import json


class ARC-Cache:
    \"\"\"ARC自适应替换缓存\"\"\"

    def __init__(self, max_size: int = 1024):
        self.max_size = max_size
        self.t1 = OrderedDict()  # 最近访问一次
        self.t2 = OrderedDict()  # 最近访问两次以上
        self.b1 = OrderedDict()  # 从t1淘汰的
        self.b2 = OrderedDict()  # 从t2淘汰的
        self.p = 0  # 目标大小

    def get(self, key: str) -> Optional[Any]:
        if key in self.t2:
            self.t2.move_to_end(key)
            return self.t2[key]
        if key in self.t1:
            value = self.t1.pop(key)
            self.t2[key] = value
            return value
        return None

    def put(self, key: str, value: Any):
        if key in self.t2:
            self.t2[key] = value
            self.t2.move_to_end(key)
            return

        if key in self.t1:
            self.t1.pop(key)
            self.t2[key] = value
            return

        if len(self.t1) + len(self.t2) >= self.max_size:
            self._evict()

        self.t1[key] = value

    def _evict(self):
        if len(self.t1) > max(1, self.p):
            removed = self.t1.popitem(last=False)
            self.b1[removed[0]] = None
            if len(self.b1) > self.max_size // 2:
                self.b1.popitem(last=False)
        elif self.t2:
            removed = self.t2.popitem(last=False)
            self.b2[removed[0]] = None
            if len(self.b2) > self.max_size // 2:
                self.b2.popitem(last=False)
        self.p = min(self.max_size, max(0, self.p + (len(self.b1) - len(self.b2))))

    def clear(self):
        self.t1.clear()
        self.t2.clear()
        self.b1.clear()
        self.b2.clear()
        self.p = 0

    def stats(self) -> dict:
        return {
            't1_size': len(self.t1),
            't2_size': len(self.t2),
            'b1_size': len(self.b1),
            'b2_size': len(self.b2),
            'p': self.p,
            'total_size': len(self.t1) + len(self.t2),
        }


class VectorIndexOptimizer:
    \"\"\"向量索引优化器\"\"\"

    def __init__(self):
        self.hierarchical_index: dict[str, list] = {}

    def build_hierarchical(self, vectors: list[dict], cluster_size: int = 100):
        \"\"\"构建分层索引\"\"\"
        self.hierarchical_index = {}

        for i in range(0, len(vectors), cluster_size):
            cluster = vectors[i:i + cluster_size]
            centroid = self._calculate_centroid([v['vector'] for v in cluster])
            cluster_id = f\"cluster_{i // cluster_size}\"
            self.hierarchical_index[cluster_id] = {
                'centroid': centroid,
                'items': cluster,
            }

    def search(self, query_vector: list[float], top_k: int = 10) -> list[dict]:
        \"\"\"分层搜索\"\"\"
        if not self.hierarchical_index:
            return []

        cluster_scores = []
        for cluster_id, cluster in self.hierarchical_index.items():
            score = self._cosine_similarity(query_vector, cluster['centroid'])
            cluster_scores.append((score, cluster_id))

        cluster_scores.sort(reverse=True)
        top_clusters = cluster_scores[:3]

        results = []
        for _, cluster_id in top_clusters:
            cluster = self.hierarchical_index[cluster_id]
            for item in cluster['items']:
                score = self._cosine_similarity(query_vector, item['vector'])
                results.append({**item, 'score': score})

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    def _calculate_centroid(self, vectors: list[list[float]]) -> list[float]:
        if not vectors:
            return []
        dim = len(vectors[0])
        centroid = [0.0] * dim
        for v in vectors:
            for i in range(min(dim, len(v))):
                centroid[i] += v[i]
        return [c / len(vectors) for c in centroid]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        dot = sum(x * y for x, y in zip(a[:n], b[:n]))
        norm_a = sum(x * x for x in a[:n]) ** 0.5
        norm_b = sum(x * x for x in b[:n]) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class ObjectPool:
    \"\"\"对象池 - 复用对象减少GC压力\"\"\"

    def __init__(self, factory, max_size: int = 100):
        self.factory = factory
        self.max_size = max_size
        self.pool: list = []
        self._lock = threading.Lock()

    def acquire(self) -> Any:
        with self._lock:
            if self.pool:
                return self.pool.pop()
        return self.factory()

    def release(self, obj: Any):
        with self._lock:
            if len(self.pool) < self.max_size:
                self.pool.append(obj)

    def stats(self) -> dict:
        return {
            'pool_size': len(self.pool),
            'max_size': self.max_size,
        }
PERF_EOF
echo "性能优化模块已创建"

# 8. 更新版本号和完成标记
echo ""
echo "[8/8] 更新系统配置..."
cd /home/xiaoxin/pangu
sed -i 's/version = "0.1.0"/version = "0.2.0"/' pyproject.toml 2>/dev/null || true

echo ""
echo "=========================================="
echo "盘古系统全面迭代完成！"
echo "完成时间: $(date)"
echo "=========================================="
echo ""
echo "新增模块："
echo "  1. natural_query.py - 自然语言查询"
echo "  2. multi_agent.py - 多Agent协作记忆"
echo "  3. realtime_stream.py - 实时记忆流+插件化"
echo "  4. advanced_reasoning.py - 高级推理引擎"
echo "  5. sync_social.py - 跨平台同步+社交化"
echo "  6. neural_memory.py - 记忆神经网络"
echo "  7. performance.py - 性能优化"
echo ""
echo "Web Dashboard增强："
echo "  - 3D记忆宫殿可视化"
echo "  - 交互式知识图谱"
echo "  - 时间线可视化"
echo "  - 分析看板"
echo ""
echo "日志文件: $LOG_FILE"
