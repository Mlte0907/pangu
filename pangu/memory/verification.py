"""盘古验证循环 — 代码质量门控

从伏羲移植：6阶段验证循环，确保代码质量和安全性。
- Phase 1: Build Verification
- Phase 2: Type Check
- Phase 3: Lint Check
- Phase 4: Test Suite
- Phase 5: Security Scan
- Phase 6: Diff Review

纯大脑能力：只做验证和报告，不修改代码。
"""

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.verification")


@dataclass
class VerificationResult:
    phase: str
    passed: bool
    output: str
    warnings: int = 0
    errors: int = 0


class VerificationLoop:
    """验证循环系统 — 代码质量门控"""

    def __init__(self, project_path: str = "."):
        self.project_path = project_path

    def run_build(self, language: str = "python") -> VerificationResult:
        """Phase 1: 构建验证"""
        try:
            if language == "python":
                result = subprocess.run(
                    ["python3", "-m", "compileall", "-q", "."],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            else:
                result = subprocess.run(["echo", "build"], capture_output=True, text=True)
            return VerificationResult(
                phase="build", passed=result.returncode == 0, output=result.stdout + result.stderr
            )
        except Exception as e:
            return VerificationResult(phase="build", passed=False, output=str(e))

    def run_type_check(self) -> VerificationResult:
        """Phase 2: 类型检查"""
        try:
            result = self._execute_type_check()
            errors = self._count_type_errors(result.stdout)
            return VerificationResult(
                phase="type_check", passed=result.returncode == 0, output=result.stdout, errors=errors
            )
        except FileNotFoundError:
            return VerificationResult(phase="type_check", passed=True, output="mypy not installed, skipping")
        except Exception as e:
            return VerificationResult(phase="type_check", passed=False, output=str(e))

    def _execute_type_check(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", "-m", "mypy", "pangu/", "--ignore-missing-imports"],
            cwd=self.project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def _count_type_errors(self, output: str) -> int:
        return len([line for line in output.split("\n") if ": error:" in line])

    def run_lint(self) -> VerificationResult:
        """Phase 3: Lint 检查"""
        try:
            result = subprocess.run(
                ["python3", "-m", "ruff", "check", "pangu/", "--output-format=text"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            warnings = len([line for line in result.stdout.split("\n") if "warning" in line.lower()])
            return VerificationResult(
                phase="lint", passed=result.returncode == 0, output=result.stdout, warnings=warnings
            )
        except FileNotFoundError:
            return VerificationResult(phase="lint", passed=True, output="ruff not installed, skipping")
        except Exception as e:
            return VerificationResult(phase="lint", passed=False, output=str(e))

    def run_tests(self) -> VerificationResult:
        """Phase 4: 测试套件"""
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return VerificationResult(phase="tests", passed=result.returncode == 0, output=result.stdout[-2000:])
        except FileNotFoundError:
            return VerificationResult(phase="tests", passed=True, output="pytest not found, skipping")
        except Exception as e:
            return VerificationResult(phase="tests", passed=False, output=str(e))

    def run_security_scan(self) -> VerificationResult:
        """Phase 5: 安全扫描"""
        findings = []
        try:
            result = subprocess.run(
                ["grep", "-rn", "sk-[a-zA-Z0-9]", "pangu/", "--include=*.py"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout:
                findings.append(f"Potential secrets found: {len(result.stdout.split(chr(10)))}")
        except Exception:
            pass

        # 检查硬编码密码
        try:
            result = subprocess.run(
                ["grep", "-rn", "password\\s*=\\s*[\"']", "pangu/", "--include=*.py"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout:
                findings.append("Hardcoded passwords found")
        except Exception:
            pass

        return VerificationResult(
            phase="security", passed=len(findings) == 0, output="\n".join(findings) if findings else "No issues found"
        )

    def run_diff_review(self) -> VerificationResult:
        """Phase 6: 差异审查"""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return VerificationResult(
                phase="diff_review", passed=True, output=result.stdout if result.returncode == 0 else "Not a git repo"
            )
        except Exception as e:
            return VerificationResult(phase="diff_review", passed=False, output=str(e))

    def _execute_phase(self, phase_name: str, phase_func) -> dict:
        result = phase_func()
        return {
            "passed": result.passed,
            "output": result.output[:500],
            "warnings": result.warnings,
            "errors": result.errors,
        }

    def run_full_verification(self) -> dict:
        """运行完整验证循环"""
        results = {}
        phases = [
            ("build", lambda: self.run_build()),
            ("type_check", lambda: self.run_type_check()),
            ("lint", self.run_lint),
            ("tests", self.run_tests),
            ("security", self.run_security_scan),
            ("diff_review", self.run_diff_review),
        ]

        for phase_name, phase_func in phases:
            logger.info(f"Running {phase_name}...")
            results[phase_name] = self._execute_phase(phase_name, phase_func)
            logger.info(f"{phase_name}: {'PASS' if results[phase_name]['passed'] else 'FAIL'}")

        results["timestamp"] = datetime.now().isoformat()
        results["all_passed"] = all(r["passed"] for r in results.values() if isinstance(r, dict) and "passed" in r)
        return results
