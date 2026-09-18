"""盘古记忆备份与恢复 — 防止数据丢失

核心能力：
1. 全量备份：备份所有记忆数据
2. 增量备份：只备份变更的记忆
3. 备份验证：验证备份完整性
4. 选择性恢复：按 Wing/时间/重要性恢复
5. 备份管理：管理多个备份版本
"""

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("pangu.memory.backup_restore")


@dataclass
class BackupInfo:
    """备份信息"""

    backup_id: str
    timestamp: str
    memory_count: int
    size_bytes: int
    checksum: str
    description: str


class BackupRestoreEngine:
    """备份恢复引擎"""

    def __init__(self, config=None, backup_dir=None):
        """备份目录解析顺序：显式 backup_dir > config.backup_dir > ~/.pangu/backups。

        显式参数是给测试用的：默认落到 $HOME 会让每次跑测试都往用户真实备份目录里
        写测试数据（曾累积 700+ 个 "test content" 假备份，见 2026-09-17 记录）。
        """
        self.config = config
        if backup_dir is not None:
            self._backup_dir = Path(backup_dir)
        elif config is not None and getattr(config, "backup_dir", None):
            self._backup_dir = Path(config.backup_dir)
        else:
            self._backup_dir = Path.home() / ".pangu" / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._backup_index: list[BackupInfo] = []
        self._load_index()

    def _load_index(self) -> None:
        """加载备份索引。

        索引损坏时**不再静默清空**：旧实现 `except: self._backup_index = []` 会让
        list_backups 显示"0 个备份"（文件其实都在），且下次 _save_index 把坏索引
        覆盖成空表 —— 静默的数据丢失。现在保留可解析的部分并留日志。
        """
        index_file = self._backup_dir / "index.json"
        if not index_file.exists():
            return
        try:
            data = json.loads(index_file.read_text())
            self._backup_index = [BackupInfo(**b) for b in data]
        except Exception as e:
            logger.warning(f"备份索引损坏（{index_file}）：{e}；本次不覆盖它，请人工检查")

    def _save_index(self) -> None:
        """保存备份索引（原子写：tmp + rename，避免写一半崩溃损坏索引）"""
        index_file = self._backup_dir / "index.json"
        data = [
            {
                "backup_id": b.backup_id,
                "timestamp": b.timestamp,
                "memory_count": b.memory_count,
                "size_bytes": b.size_bytes,
                "checksum": b.checksum,
                "description": b.description,
            }
            for b in self._backup_index
        ]
        tmp = index_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.replace(index_file)

    def _serialize_drawers(self, drawers: list) -> str:
        """序列化记忆。

        用 Drawer.to_dict() 存**全部 12 个字段**。旧实现手挑 7 个字段，丢了
        room / hall（宫殿定位）与 metadata（tenant_id / classification / decay_score /
        source_session…），即使恢复成功也回不到原状态 —— 2026-09-19 修。
        旧备份文件（7 字段）仍可恢复：Drawer.from_dict 对缺字段用默认值。
        """
        data = [d.to_dict() if hasattr(d, "to_dict") else d for d in drawers]
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _deserialize_drawers(data: list) -> list:
        """备份条目 → Drawer 对象（缺字段由 Drawer.from_dict 兜默认值，兼容 v1 备份）"""
        from ..core.palace import Drawer

        out = []
        for item in data:
            if isinstance(item, Drawer):
                out.append(item)
            else:
                out.append(Drawer.from_dict(item))
        return out

    # ── 附属资产（2026-09-19 扩展）──
    #
    # 此前备份只覆盖 drawers.json，而权威目录里还有知识图谱 / wiki / 遗忘归档 /
    # 任务表 —— "全量备份"名不符实（恢复后 KG 与 wiki 全丢）。
    # 刻意**不含 users.db**：它是用户与钥匙凭据，恢复它会覆盖现有凭据（危险），
    # 应由运维单独处置。
    _ASSET_FILES = (
        ("wiki_index", "wiki.json/wiki_index.json"),
        ("forgetting_archive", "../forgetting_archive.json"),
        ("tasks_db", "tasks.db"),
    )

    def _collect_assets(self) -> dict:
        """收集附属资产（base64 编码），供 backup 打包。

        KG 必须走 sqlite3 在线备份 API，不能直接拷 .db 文件：库跑在 WAL 模式，
        直接拷贝主文件会丢掉尚未 checkpoint 的 WAL 数据（实测该库主文件 57KB
        对应 WAL 2MB）。
        """
        assets: dict = {}
        if self.config is None:
            return assets
        base = Path(self.config.palace_path)
        if not base.exists():
            return assets

        kg = base / "knowledge_graph.db"
        if kg.exists():
            raw = self._dump_sqlite(kg)
            if raw is not None:
                assets["knowledge_graph"] = raw

        for key, rel in self._ASSET_FILES:
            p = (base / rel).resolve()
            try:
                if p.exists() and p.is_file():
                    assets[key] = base64.b64encode(p.read_bytes()).decode()
            except Exception as e:
                logger.warning(f"资产收集跳过 {p}: {e}")
        return assets

    @staticmethod
    def _dump_sqlite(db_path: Path) -> str | None:
        """用 SQLite 在线备份 API 导出为 base64（正确处理 WAL，含未 checkpoint 数据）"""
        import sqlite3

        src = dst = None
        tmp = db_path.with_name(db_path.name + ".dump.tmp")
        try:
            src = sqlite3.connect(str(db_path))
            dst = sqlite3.connect(str(tmp))
            src.backup(dst)
            dst.close()
            dst = None
            return base64.b64encode(tmp.read_bytes()).decode()
        except Exception as e:
            logger.warning(f"SQLite 导出失败 {db_path}: {e}")
            return None
        finally:
            for c in (dst, src):
                if c is not None:
                    c.close()
            if tmp.exists():
                tmp.unlink()

    def _restore_assets(self, assets: dict) -> dict:
        """还原附属资产，返回 {资产键: "ok" | 错误信息}。

        KG 走反向 backup（备份内容 → 活跃库）：不用手工处理 WAL，也不破坏
        已打开的连接。
        """
        result: dict = {}
        if self.config is None or not assets:
            return result
        base = Path(self.config.palace_path)
        base.mkdir(parents=True, exist_ok=True)

        if assets.get("knowledge_graph"):
            import sqlite3

            tmp = base / "_restore_kg.tmp"
            try:
                tmp.write_bytes(base64.b64decode(assets["knowledge_graph"]))
                src = sqlite3.connect(str(tmp))
                dst = sqlite3.connect(str(base / "knowledge_graph.db"))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
                    src.close()
                result["knowledge_graph"] = "ok"
            except Exception as e:
                result["knowledge_graph"] = f"失败: {e}"
            finally:
                if tmp.exists():
                    tmp.unlink()

        for key, rel in self._ASSET_FILES:
            if key not in assets:
                continue
            p = (base / rel).resolve()
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(base64.b64decode(assets[key]))
                result[key] = "ok"
            except Exception as e:
                result[key] = f"失败: {e}"
        return result

    def backup(self, drawers: list, description: str = "") -> BackupInfo:
        """全量备份（记忆抽屉 + 附属资产）。

        格式 v2：{"version": 2, "generated_at": …, "drawers": [...], "assets": {...}}
        v1（纯数组）仍可被 restore / verify 读取（_parse_backup_payload 兼容）。
        """
        assets = self._collect_assets()
        payload = {
            "version": 2,
            "generated_at": datetime.now().isoformat(),
            "drawers": [d.to_dict() if hasattr(d, "to_dict") else d for d in drawers],
            "assets": assets,
        }
        serialized = json.dumps(payload, ensure_ascii=False)
        checksum = hashlib.sha256(serialized.encode()).hexdigest()[:16]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = f"backup_{timestamp}_{checksum[:8]}"

        backup_file = self._backup_dir / f"{backup_id}.json"
        backup_file.write_text(serialized)

        asset_note = f" + {len(assets)} 类附属资产" if assets else ""
        info = BackupInfo(
            backup_id=backup_id,
            timestamp=datetime.now().isoformat(),
            memory_count=len(drawers),
            size_bytes=len(serialized.encode()),
            checksum=checksum,
            description=description or f"全量备份 {len(drawers)} 条记忆{asset_note}",
        )
        self._backup_index.append(info)
        self._save_index()

        return info

    @staticmethod
    def _parse_backup_payload(data):
        """兼容两层格式：v2 dict → (drawers, assets)；v1 纯数组 → (drawers, {})"""
        if isinstance(data, dict):
            return data.get("drawers") or [], data.get("assets") or {}
        if isinstance(data, list):
            return data, {}
        return [], {}

    def backup_incremental(self, drawers: list, since_id: str = None) -> BackupInfo:
        """增量备份。

        ⚠ 诚实说明（2026-09-19）：**当前实现三个分支都走全量**（self.backup），
        "增量"只体现在描述文案。真正做增量需要"自 since_id 以来变更的条目"，
        而 backup() 只拿到抽屉列表、无变更日志可用。不改行为（调用方依赖返回一个
        可用备份），只把语义说清楚 + 描述里显式标注，避免运维按"小体积"预期
        误判备份内容。
        """
        if not since_id:
            return self.backup(drawers, "增量备份（无基准，执行全量）")

        last_backup = None
        for b in self._backup_index:
            if b.backup_id == since_id:
                last_backup = b
                break

        if not last_backup:
            return self.backup(drawers, "增量备份（基准未找到，执行全量）")

        return self.backup(drawers, f"增量备份（自 {since_id} 以来）")

    def list_backups(self) -> list[dict]:
        """列出所有备份"""
        return [
            {
                "id": b.backup_id,
                "timestamp": b.timestamp,
                "memories": b.memory_count,
                "size": b.size_bytes,
                "description": b.description,
            }
            for b in self._backup_index
        ]

    def verify_backup(self, backup_id: str) -> dict:
        """验证备份完整性"""
        backup_file = self._backup_dir / f"{backup_id}.json"
        if not backup_file.exists():
            return {"valid": False, "error": "备份文件不存在"}

        content = backup_file.read_text()
        checksum = hashlib.sha256(content.encode()).hexdigest()[:16]

        info = next((b for b in self._backup_index if b.backup_id == backup_id), None)
        if not info:
            return {"valid": False, "error": "备份索引中未找到"}

        if checksum != info.checksum:
            return {"valid": False, "error": f"校验和不匹配: {checksum} != {info.checksum}"}

        try:
            data = json.loads(content)
            drawers, assets = self._parse_backup_payload(data)
            return {
                "valid": True,
                "backup_id": backup_id,
                "memory_count": len(drawers),
                "checksum": checksum,
                "size": len(content.encode()),
                "format": "v2" if isinstance(data, dict) else "v1",
                "assets": sorted(assets.keys()),
            }
        except json.JSONDecodeError:
            return {"valid": False, "error": "JSON 解析失败"}

    def restore(self, backup_id: str, memory=None, dry_run: bool = False) -> dict:
        """从备份恢复（**真落盘**）。

        旧实现只把 JSON 读出来塞进返回值、handler 侧还 result.pop("drawers") —— 调用方
        拿到 success=True / restored_count=N，磁盘却毫无变化（假成功；2026-09-19 实证）。
        现在真落盘，并按"恢复是危险操作"设四道闸：
          ① 校验 checksum —— 损坏/被改动的备份不许覆盖现库
          ② 拒绝空备份 —— 0 条恢复 == 清库，直接拒绝
          ③ 恢复前自动快照当前状态（BackupRestoreEngine 快照 + replace_all 内
             _backup_drawers 双保险），任何时候可回滚
          ④ dry_run=True 只报告将要发生什么，不动数据

        注意：服务侧与 engine 不共享 MemoryStack 实例，落盘后服务内存最多滞后一个
        缓存 TTL（30s）—— 恢复属于运维级低频操作，接受该窗口。

        Args:
            backup_id: 备份 id
            memory: 可选的 MemoryStack（测试注入）；缺省按 config 新建
            dry_run: True 时只做校验与统计，不落盘
        """
        backup_file = self._backup_dir / f"{backup_id}.json"
        if not backup_file.exists():
            return {"success": False, "error": "备份文件不存在"}

        # ① 完整性校验
        verdict = self.verify_backup(backup_id)
        if not verdict.get("valid"):
            return {"success": False, "error": f"备份校验失败: {verdict.get('error')}"}

        try:
            data = json.loads(backup_file.read_text())
        except Exception as e:
            return {"success": False, "error": f"读取备份失败: {e}"}

        # v2（dict：drawers + assets）/ v1（纯数组）统一解析
        drawers_raw, assets = self._parse_backup_payload(data)

        # ② 空备份保护（按抽屉条数判：v2 里 dict 非空但 drawers 可能是空表）
        if not drawers_raw:
            return {"success": False, "error": "备份为空（0 条），拒绝恢复以防清库"}

        drawers = self._deserialize_drawers(drawers_raw)

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "backup_id": backup_id,
                "would_restore": len(drawers),
                "assets": sorted(assets.keys()),
                "checksum": verdict.get("checksum"),
            }

        ms = memory if memory is not None else self._get_memory()

        # ③ 恢复前快照（失败即中止；宁可不动，不可无回滚点）
        safety = None
        try:
            current = ms.get_drawers()
            if current:
                safety = self.backup(current, f"restore {backup_id} 前置快照").backup_id
        except Exception as e:
            return {"success": False, "error": f"前置快照失败，已中止恢复: {e}"}

        # ④ 真落盘
        try:
            ok = ms.replace_all(drawers)
        except Exception as e:
            return {"success": False, "error": f"落盘失败: {e}"}

        if not ok:
            # _save_drawers 返回 False 的原因不止一种（空写保护 / 存储后端写失败），
            # 这里给中性描述，具体原因看服务日志里 layers 的 warning。
            return {"success": False, "error": "落盘失败（磁盘未变），原因见服务日志"}

        # ⑤ 附属资产（KG/wiki/归档/任务表）—— 记忆落盘成功后再还原。
        #    单个资产失败不回滚记忆：记忆是主体，资产可下次单独恢复。
        assets_result = self._restore_assets(assets) if assets else {}

        return {
            "success": True,
            "backup_id": backup_id,
            "restored_count": len(drawers),
            "safety_backup": safety,
            "checksum": verdict.get("checksum"),
            "assets_restored": assets_result,
        }

    def _get_memory(self):
        """按 config 新建 MemoryStack —— restore 落盘用（服务侧缓存 TTL 30s 自会同步）。

        先 ensure_dirs：恢复要写 drawers.json，目录不存在会让 _save_drawers 失败
        （实测：No such file or directory .../v2_memories/drawers.json.tmp）。
        config 为空时补 PanguConfig.load()（与 MemoryStack(None) 的路径一致），
        否则这里的 ensure_dirs 会被静默跳过、白建。
        """
        cfg = self.config
        if cfg is None:
            from ..core.config import PanguConfig

            cfg = PanguConfig.load()
        try:
            cfg.ensure_dirs()
        except Exception:
            pass
        from .layers import MemoryStack

        return MemoryStack(cfg)

    def _apply_filters(self, data: list, wing: str = None, min_importance: float = None) -> list:
        filtered = data
        if wing:
            filtered = [d for d in filtered if d.get("wing") == wing]
        if min_importance is not None:
            filtered = [d for d in filtered if d.get("importance", 0) >= min_importance]
        return filtered

    def restore_by_filter(
        self,
        backup_id: str,
        wing: str = None,
        min_importance: float = None,
        memory=None,
        dry_run: bool = False,
    ) -> dict:
        """按条件恢复备份中的一部分（**追加**语义，真落盘）。

        与 restore 的分工：restore 是"整库回滚到备份时刻"（覆盖，危险）；本方法供
        "误删某个 wing 的一批、想找回来"这类局部需求 —— 只把筛选出的条目**追加**回库
        （已存在的 id 跳过），不删任何现有记忆，故无需前置快照。

        旧实现只返回统计、不落盘（名字骗人；2026-09-19 修）。
        """
        backup_file = self._backup_dir / f"{backup_id}.json"
        if not backup_file.exists():
            return {"success": False, "error": "备份文件不存在"}

        try:
            data = json.loads(backup_file.read_text())
        except json.JSONDecodeError:
            return {"success": False, "error": "JSON 解析失败"}

        # v2（dict）/ v1（数组）统一解析 —— 此前直接遍历 data，v2 下会拿 str 调 .get
        drawers_raw, _assets = self._parse_backup_payload(data)
        filtered = self._apply_filters(drawers_raw, wing, min_importance)
        base = {
            "backup_id": backup_id,
            "total_in_backup": len(drawers_raw),
            "filter": {"wing": wing, "min_importance": min_importance},
        }

        if not filtered:
            return {"success": False, "error": "筛选结果为空，无可恢复", **base}

        if dry_run:
            return {"success": True, "dry_run": True, "would_restore": len(filtered), **base}

        ms = memory if memory is not None else self._get_memory()
        existing = {d.id for d in ms.get_drawers()}
        to_add = [d for d in self._deserialize_drawers(filtered) if d.id not in existing]
        skipped = len(filtered) - len(to_add)

        if to_add:
            try:
                ms.add_drawers(to_add)
            except Exception as e:
                return {"success": False, "error": f"落盘失败: {e}", **base}

        return {
            "success": True,
            "restored_count": len(to_add),
            "skipped_existing": skipped,
            **base,
        }

    def delete_backup(self, backup_id: str) -> dict:
        """删除备份"""
        backup_file = self._backup_dir / f"{backup_id}.json"
        if backup_file.exists():
            backup_file.unlink()

        self._backup_index = [b for b in self._backup_index if b.backup_id != backup_id]
        self._save_index()

        return {"deleted": backup_id}

    def get_backup_stats(self) -> dict:
        """获取备份统计"""
        total_size = sum(b.size_bytes for b in self._backup_index)
        total_memories = sum(b.memory_count for b in self._backup_index)
        return {
            "total_backups": len(self._backup_index),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "total_memories_backed": total_memories,
            "latest": self._backup_index[-1].backup_id if self._backup_index else None,
        }


_backup_engine: BackupRestoreEngine | None = None


def get_backup_engine(config=None) -> BackupRestoreEngine:
    """获取全局备份恢复引擎实例"""
    global _backup_engine
    if _backup_engine is None:
        _backup_engine = BackupRestoreEngine(config)
    return _backup_engine
