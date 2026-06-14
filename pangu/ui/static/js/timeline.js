/**
 * 盘古时间线可视化
 * 展示记忆的时间演进和事件链
 */

class Timeline {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.events = [];
        this.selectedRange = '7d';
        this.init();
    }

    init() {
        this.render();
    }

    loadData(data) {
        this.events = (data.memories || []).map(m => ({
            id: m.id,
            content: m.content,
            wing: m.wing,
            room: m.room,
            importance: m.importance || 3,
            timestamp: new Date(m.created_at),
            tags: m.tags || []
        }));

        // 按时间排序
        this.events.sort((a, b) => a.timestamp - b.timestamp);

        this.render();
    }

    render() {
        const container = this.container;
        container.innerHTML = '';

        if (this.events.length === 0) {
            container.innerHTML = '<p class="placeholder">暂无时间线数据</p>';
            return;
        }

        // 过滤事件
        const filteredEvents = this.filterEvents();

        // 创建时间线
        const timeline = document.createElement('div');
        timeline.className = 'timeline';

        // 时间线轴
        const axis = document.createElement('div');
        axis.className = 'timeline-axis';
        timeline.appendChild(axis);

        // 事件列表
        const eventsList = document.createElement('div');
        eventsList.className = 'timeline-events';

        filteredEvents.forEach((event, index) => {
            const eventEl = this.createEventElement(event, index);
            eventsList.appendChild(eventEl);
        });

        timeline.appendChild(eventsList);
        container.appendChild(timeline);

        // 添加动画
        this.animateEvents();
    }

    filterEvents() {
        const now = new Date();
        let cutoff;

        switch (this.selectedRange) {
            case '1d':
                cutoff = new Date(now - 24 * 60 * 60 * 1000);
                break;
            case '7d':
                cutoff = new Date(now - 7 * 24 * 60 * 60 * 1000);
                break;
            case '30d':
                cutoff = new Date(now - 30 * 24 * 60 * 60 * 1000);
                break;
            case 'all':
            default:
                cutoff = new Date(0);
        }

        return this.events.filter(e => e.timestamp >= cutoff);
    }

    createEventElement(event, index) {
        const isLeft = index % 2 === 0;
        const importanceClass = this.getImportanceClass(event.importance);

        const eventEl = document.createElement('div');
        eventEl.className = `timeline-event ${isLeft ? 'left' : 'right'} ${importanceClass}`;
        eventEl.dataset.id = event.id;

        eventEl.innerHTML = `
            <div class="event-dot"></div>
            <div class="event-content">
                <div class="event-time">${this.formatTime(event.timestamp)}</div>
                <div class="event-text">${this.truncateText(event.content, 100)}</div>
                <div class="event-meta">
                    <span class="event-wing">${event.wing}</span>
                    <span class="event-room">${event.room}</span>
                    ${event.tags.slice(0, 3).map(t => `<span class="event-tag">${t}</span>`).join('')}
                </div>
            </div>
        `;

        eventEl.addEventListener('click', () => this.onEventClick(event));

        return eventEl;
    }

    getImportanceClass(importance) {
        if (importance >= 8) return 'high';
        if (importance >= 5) return 'medium';
        return 'low';
    }

    formatTime(date) {
        const now = new Date();
        const diff = now - date;
        const days = Math.floor(diff / (24 * 60 * 60 * 1000));

        if (days === 0) {
            return '今天 ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        } else if (days === 1) {
            return '昨天 ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        } else if (days < 7) {
            return `${days}天前`;
        } else {
            return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
        }
    }

    truncateText(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    animateEvents() {
        const events = this.container.querySelectorAll('.timeline-event');
        events.forEach((event, index) => {
            event.style.opacity = '0';
            event.style.transform = 'translateY(20px)';
            setTimeout(() => {
                event.style.transition = 'all 0.3s ease';
                event.style.opacity = '1';
                event.style.transform = 'translateY(0)';
            }, index * 100);
        });
    }

    onEventClick(event) {
        // 显示事件详情
        const modal = document.getElementById('modal-content');
        modal.innerHTML = `
            <div class="event-detail">
                <h3>事件详情</h3>
                <div class="detail-meta">
                    <span>时间: ${event.timestamp.toLocaleString('zh-CN')}</span>
                    <span>空间: ${event.wing}</span>
                    <span>房间: ${event.room}</span>
                </div>
                <div class="detail-content">
                    ${event.content}
                </div>
                <div class="detail-tags">
                    ${event.tags.map(t => `<span class="tag">${t}</span>`).join('')}
                </div>
                <div class="detail-actions">
                    <button class="btn btn-outline" onclick="closeModal()">关闭</button>
                </div>
            </div>
        `;
        document.getElementById('modal-overlay').classList.remove('hidden');
    }

    setRange(range) {
        this.selectedRange = range;
        this.render();
    }

    // 获取事件链
    getEventChains() {
        const chains = [];
        let currentChain = [];

        this.events.forEach((event, index) => {
            if (index === 0) {
                currentChain.push(event);
            } else {
                const prevEvent = this.events[index - 1];
                const timeDiff = event.timestamp - prevEvent.timestamp;

                // 如果时间间隔小于2小时，认为是同一事件链
                if (timeDiff < 2 * 60 * 60 * 1000) {
                    currentChain.push(event);
                } else {
                    if (currentChain.length > 1) {
                        chains.push([...currentChain]);
                    }
                    currentChain = [event];
                }
            }
        });

        if (currentChain.length > 1) {
            chains.push(currentChain);
        }

        return chains;
    }

    // 获取因果关系
    getCausalLinks() {
        const links = [];

        this.events.forEach((event, index) => {
            if (index === 0) return;

            const prevEvent = this.events[index - 1];

            // 检查是否有因果关键词
            const causalKeywords = ['因为', '所以', '导致', '结果', '修复', '解决'];
            const hasCausal = causalKeywords.some(kw =>
                event.content.includes(kw) || prevEvent.content.includes(kw)
            );

            if (hasCausal) {
                links.push({
                    source: prevEvent,
                    target: event,
                    type: 'causal'
                });
            }
        });

        return links;
    }
}

// 导出
window.Timeline = Timeline;
