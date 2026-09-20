"""盘古 admin 凭据校验（唯一实现）。

为什么单独成模块（2026-09-20）：此前 `routes_keys.py`、`routes_platforms.py`、
`routes_dashboard.py` 各自复制了一份 `_verify_admin`，且都把 secret 路径**硬编码**
为 `Path.home() / ".pangu" / ".admin_secret"` —— 与 `PanguConfig.base_dir`
（可由 `PANGU_BASE_DIR` 覆盖）解耦。后果：

1. 换 `base_dir` 部署时，管理端点在错误的位置读写 secret；
2. 三处行为不一致：只有 `routes_keys` 会自动**生成** secret，另两处在文件缺失时
   直接返回 False —— 同一凭据在不同端点组表现不同；
3. 任意未鉴权的 admin 请求都会触发 `routes_keys` 的 secret 生成副作用。

现在路径统一由 config 派生，行为统一为「按需生成 + 常量时间比对」。
"""

import logging
import secrets
from pathlib import Path

from fastapi import Request

logger = logging.getLogger("pangu.api.admin_auth")


def admin_secret_path() -> Path:
    """admin secret 文件路径（跟随 base_dir，可用 PANGU_BASE_DIR 隔离）。"""
    try:
        from pangu.core.config import PanguConfig

        base = Path(PanguConfig.load().base_dir)
    except Exception:  # 配置不可用时退回默认目录，保证管理功能不瘫
        base = Path.home() / ".pangu"
    return base / ".admin_secret"


def ensure_admin_secret() -> str:
    """确保 admin secret 存在（首次自动生成，0600）。"""
    path = admin_secret_path()
    if path.exists():
        return path.read_text().strip()
    secret = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secret)
    path.chmod(0o600)
    logger.info(f"admin secret 已生成: {path}")
    return secret


def verify_admin(request: Request) -> bool:
    """校验 `X-Admin-Key`（常量时间比较）。"""
    admin_key = request.headers.get("X-Admin-Key", "")
    if not admin_key:
        return False
    try:
        return secrets.compare_digest(admin_key, ensure_admin_secret())
    except Exception as e:  # 读/建失败按未通过处理，不泄露内部状态
        logger.warning(f"admin secret 校验失败: {e}")
        return False
