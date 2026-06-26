"""
盘古 — ABAC 属性访问控制
========================================

在 RBAC（角色 → 权限）基础上叠加 ABAC（属性 → 决策），
支持多租户隔离、资源所有权、密级控制等细粒度规则。

## 核心概念

• **Subject** (主体)：当前请求的 user
  - sub / role / scopes / tenant_id / department / clearance / groups

• **Resource** (资源)：被访问的对象
  - type / id / owner_id / tenant_id / classification / tags

• **Action** (动作)：read / write / delete / admin / search ...

• **Environment** (环境)：time / ip / method / path

• **Rule** (规则)：当 condition 为真时给 effect (allow | deny)
  多个 rule 组合成 policy，多个 policy 求值为 Decision

## 内置策略

1. **tenant_isolation** — 跨租户访问一律拒绝
2. **owner_or_admin** — 资源 owner 或 admin 可访问
3. **classification_based** — subject.clearance >= resource.classification
4. **public_or_anon** — visibility == "public" 对所有人开放
5. **deny_blacklist** — 显式 deny 列表最高优先级

## 用法

```python
from pangu.api.abac import (
    authorize, Policy, Rule, RequestContext, Effect,
    register_policy, load_policies_from_config,
)
from pangu.api.rbac import Principal

@app.get("/api/v2/memories/{mid}")
async def get_memory(
    mid: str,
    principal: Principal = Depends(...),
    decision = Depends(authorize("memories", "read", resource_loader=load_memory)),
):
    return decision.context.resource
```
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import HTTPException, Request, status

from pangu.api.rbac import Principal

logger = logging.getLogger("pangu.api.abac")


# ──────────────────────────────────────────────
# 基础类型
# ──────────────────────────────────────────────
class Effect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


# ──────────────────────────────────────────────
# 主体 / 资源 / 环境
# ──────────────────────────────────────────────
@dataclass
class Subject:
    user_id: str
    role: str = ""
    scopes: set[str] = field(default_factory=set)
    tenant_id: str = "default"
    department: str = ""
    clearance: int = 0  # 0=public, 1=internal, 2=confidential, 3=secret
    groups: set[str] = field(default_factory=set)
    is_admin: bool = False

    @classmethod
    def from_principal(cls, principal: Principal, tenant_id: str = "default") -> Subject:
        # 从 token extra claim 读取 tenant / department / clearance
        claims = principal.claims
        extra = getattr(claims, "extra", {}) if claims else {}
        return cls(
            user_id=principal.user_id,
            role=principal.role,
            scopes=principal.scopes,
            tenant_id=extra.get("tenant_id", tenant_id),
            department=extra.get("department", ""),
            clearance=int(extra.get("clearance", 0)),
            groups=set(extra.get("groups", [])),
            is_admin=principal.is_admin(),
        )


@dataclass
class Resource:
    type: str  # "memories" / "system" / "engines" / ...
    id: str = ""
    owner_id: str = ""
    tenant_id: str = "default"
    classification: int = 0  # 0=public, 1=internal, 2=confidential, 3=secret
    visibility: str = "private"  # "private" | "tenant" | "public"
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass
class Environment:
    timestamp: float = field(default_factory=time.time)
    client_ip: str = ""
    method: str = ""
    path: str = ""


@dataclass
class RequestContext:
    """完整的 ABAC 决策上下文。"""

    subject: Subject
    action: str  # "read" / "write" / "delete" / "admin" / "search" / ...
    resource: Resource
    environment: Environment = field(default_factory=Environment)


# ──────────────────────────────────────────────
# 规则 / 策略
# ──────────────────────────────────────────────
@dataclass
class Rule:
    """单条规则：condition 满足时返回 effect。"""

    effect: Effect
    description: str = ""
    # 简单条件：用 Python 表达式求值（仅限访问 context 的字段）
    condition: str = ""  # 留空 = 始终匹配

    def matches(self, ctx: RequestContext) -> bool:
        if not self.condition:
            return True
        try:
            # 安全评估：仅暴露 ctx 属性
            ns = {"ctx": ctx, "s": ctx.subject, "r": ctx.resource, "e": ctx.environment, "act": ctx.action}
            return bool(eval(self.condition, {"__builtins__": {}}, ns))
        except Exception:  # noqa: BLE001
            return False


@dataclass
class Policy:
    name: str
    rules: list[Rule] = field(default_factory=list)
    priority: int = 100  # 数字越小越先评估

    def evaluate(self, ctx: RequestContext) -> Effect | None:
        """返回首个匹配的 effect；无匹配返回 None 表示 '未决'。"""
        for rule in self.rules:
            if rule.matches(ctx):
                logger.debug(f"ABAC 策略 {self.name!r} 命中规则: {rule.description!r} → {rule.effect.value}")
                return rule.effect
        return None


# ──────────────────────────────────────────────
# 决策
# ──────────────────────────────────────────────
@dataclass
class Decision:
    allowed: bool
    effect: Effect
    reason: str
    policy: str = ""
    context: RequestContext | None = None


# ──────────────────────────────────────────────
# 策略注册表
# ──────────────────────────────────────────────
_POLICY_REGISTRY: list[Policy] = []


def register_policy(policy: Policy) -> None:
    """注册一条策略到全局表。同一 name 覆盖。"""
    global _POLICY_REGISTRY
    _POLICY_REGISTRY = [p for p in _POLICY_REGISTRY if p.name != policy.name]
    _POLICY_REGISTRY.append(policy)
    _POLICY_REGISTRY.sort(key=lambda p: p.priority)


def clear_policies() -> None:
    """清空策略（测试用）。"""
    _POLICY_REGISTRY.clear()


def get_policies() -> list[Policy]:
    return list(_POLICY_REGISTRY)


# ──────────────────────────────────────────────
# 内置策略
# ──────────────────────────────────────────────
def register_builtin_policies() -> None:
    """注册盘古内置策略。"""

    # 1. 显式 deny 黑名单（最高优先级）
    # 默认：未配置黑名单时为无害的 allow，便于未来扩展。
    # 真正使用 deny 场景时，外部可通过 register_policy 注入 condition 包含黑名单的规则。
    register_policy(
        Policy(
            name="deny_blacklist",
            priority=0,
            rules=[
                # 占位规则：始终为 noop（由具体的黑名单策略覆盖）
                Rule(Effect.ALLOW, "黑名单占位（未命中任何规则）", condition="False"),  # 永不命中
            ],
        )
    )

    # 2. admin 角色 → 全放行
    register_policy(
        Policy(
            name="admin_full",
            priority=10,
            rules=[
                Rule(Effect.ALLOW, "admin 角色放行所有", condition="s.is_admin"),
            ],
        )
    )

    # 3. 公开资源 → 任何人都可读
    register_policy(
        Policy(
            name="public_resource",
            priority=20,
            rules=[
                Rule(
                    Effect.ALLOW,
                    "公开资源 read 放行",
                    condition='r.visibility == "public" and act in ("read", "search")',
                ),
            ],
        )
    )

    # 4. 租户隔离（必须同一租户，但公开资源 / admin / 缺省租户例外）
    register_policy(
        Policy(
            name="tenant_isolation",
            priority=30,
            rules=[
                Rule(
                    Effect.DENY,
                    "跨租户访问被拒",
                    condition='r.tenant_id != "" and s.tenant_id != "" and s.tenant_id != r.tenant_id and r.visibility != "public" and not s.is_admin',
                ),
            ],
        )
    )

    # 5. 资源所有权（owner 可访问）
    register_policy(
        Policy(
            name="owner_or_admin",
            priority=40,
            rules=[
                Rule(Effect.ALLOW, "资源 owner 放行", condition='r.owner_id != "" and r.owner_id == s.user_id'),
            ],
        )
    )

    # 6. 密级控制（subject.clearance >= resource.classification）
    register_policy(
        Policy(
            name="classification_based",
            priority=50,
            rules=[
                Rule(Effect.DENY, "密级不足被拒", condition="r.classification > s.clearance"),
            ],
        )
    )

    # 7. 租户级可见（同一租户都可读）
    register_policy(
        Policy(
            name="tenant_visibility",
            priority=60,
            rules=[
                Rule(
                    Effect.ALLOW,
                    "租户级可见资源 read",
                    condition='r.visibility == "tenant" and r.tenant_id == s.tenant_id and act in ("read", "search")',
                ),
            ],
        )
    )

    # 8. 默认 deny（仅当没有任何 allow 命中时）
    register_policy(
        Policy(
            name="default_deny",
            priority=9999,
            rules=[
                # 永不匹配自身：仅在 evaluate() 中作为 fallback 调用
            ],
        )
    )


# ──────────────────────────────────────────────
# 决策引擎
# ──────────────────────────────────────────────
def evaluate(ctx: RequestContext) -> Decision:
    """遍历所有策略。

    决策规则：
    - 任意 DENY 命中 → 立即返回（高优先级）
    - 首个 ALLOW 命中 → 记录但继续（让后续 DENY 仍能生效）
    - 全部遍历完无 DENY，有 ALLOW → 返回首个 ALLOW
    - 否则 → 默认拒绝
    """
    first_allow: Decision | None = None
    for policy in _POLICY_REGISTRY:
        effect = policy.evaluate(ctx)
        if effect is None:
            continue
        decision = Decision(
            allowed=(effect == Effect.ALLOW),
            effect=effect,
            reason=f"策略 {policy.name!r} 命中",
            policy=policy.name,
            context=ctx,
        )
        if effect == Effect.DENY:
            # DENY 最高优先级，立即返回
            return decision
        if first_allow is None:
            first_allow = decision
        # 否则继续（让后续 DENY 仍能覆盖 ALLOW）
    if first_allow:
        return first_allow
    return Decision(
        allowed=False,
        effect=Effect.DENY,
        reason="无策略命中，默认拒绝",
    )


# ──────────────────────────────────────────────
# 自定义策略加载（JSON）
# ──────────────────────────────────────────────
def policy_from_dict(data: dict) -> Policy:
    """从 dict 构造 Policy。格式：
    {
      "name": "my_policy",
      "priority": 100,
      "rules": [
        {"effect": "allow", "description": "...", "condition": "act == 'read'"},
        ...
      ]
    }
    """
    rules = []
    for r in data.get("rules", []):
        rules.append(
            Rule(
                effect=Effect(r["effect"]),
                description=r.get("description", ""),
                condition=r.get("condition", ""),
            )
        )
    return Policy(
        name=data["name"],
        rules=rules,
        priority=int(data.get("priority", 100)),
    )


def load_policies_from_config(policies: Iterable[dict]) -> None:
    """从配置加载额外策略。"""
    for p in policies:
        try:
            register_policy(policy_from_dict(p))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"加载策略失败：{e}")


# ──────────────────────────────────────────────
# FastAPI 依赖
# ──────────────────────────────────────────────
ResourceLoader = Callable[[RequestContext], Resource | None]


def _default_resource(ctx: RequestContext) -> Resource:
    """没有显式 loader 时，从 path 解析 resource。"""
    return ctx.resource


def authorize(
    resource_type: str,
    action: str,
    *,
    resource_loader: ResourceLoader | None = None,
    tenant_header: str = "x-tenant-id",
    deny_on_no_policy: bool = True,
):
    """FastAPI 依赖：ABAC 决策后决定是否放行。

    Args:
        resource_type: 资源类型（"memories" / "system" / ...）
        action: 操作（"read" / "write" / "delete" / "admin" / "search"）
        resource_loader: 加载资源的回调；返回 None 表示未找到（默认 deny）
        tenant_header: 用于从 header 提取 tenant_id 的键名
        deny_on_no_policy: 当没有策略注册时是否拒绝
    """
    from pangu.api.rbac import get_principal

    def _dep(request: Request) -> Decision:
        principal = get_principal(request)
        if principal.method == "anonymous":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": 401, "message": "Authentication required", "data": None},
            )

        # 默认 tenant 从 header / subject claim 取
        tenant_id = request.headers.get(tenant_header, "") or "default"
        subject = Subject.from_principal(principal, tenant_id=tenant_id)
        # 若 header 显式给了 tenant，覆盖 claim
        if request.headers.get(tenant_header):
            subject.tenant_id = request.headers.get(tenant_header)

        env = Environment(
            client_ip=request.client.host if request.client else "",
            method=request.method,
            path=str(request.url.path),
        )
        resource = Resource(type=resource_type, tenant_id=subject.tenant_id)

        ctx = RequestContext(subject=subject, action=action, resource=resource, environment=env)

        # 外部 loader 可补全 resource 详情
        if resource_loader is not None:
            loaded = resource_loader(ctx)
            if loaded is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": 404, "message": f"{resource_type} not found", "data": None},
                )
            ctx.resource = loaded

        # 没有任何策略 → 拒绝（除非显式关闭）
        if not _POLICY_REGISTRY:
            if deny_on_no_policy:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"code": 403, "message": "ABAC not initialized", "data": None},
                )
            return Decision(allowed=True, effect=Effect.ALLOW, reason="abac disabled")

        decision = evaluate(ctx)
        if not decision.allowed:
            # 资源已加载时用 loaded，未加载时用初始 resource
            res = ctx.resource
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": 403,
                    "message": f"ABAC deny: {decision.reason}",
                    "data": {
                        "policy": decision.policy,
                        "subject": {
                            "user_id": subject.user_id,
                            "role": subject.role,
                            "tenant_id": subject.tenant_id,
                            "clearance": subject.clearance,
                        },
                        "action": action,
                        "resource": {
                            "type": res.type,
                            "id": res.id,
                            "tenant_id": res.tenant_id,
                            "classification": res.classification,
                            "visibility": res.visibility,
                        },
                    },
                },
            )
        return decision

    return _dep


__all__ = [
    "Effect",
    "Subject",
    "Resource",
    "Environment",
    "RequestContext",
    "Rule",
    "Policy",
    "Decision",
    "register_policy",
    "register_builtin_policies",
    "clear_policies",
    "get_policies",
    "policy_from_dict",
    "load_policies_from_config",
    "evaluate",
    "authorize",
]
