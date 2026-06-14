import os
import plistlib
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from headless_obsidian_mcp.app.daemon import DaemonService

LAUNCH_AGENT_LABEL = "com.headlessobsidianmcp.server"
_LOG_NAME = "headless-obsidian-mcp.launchd.log"
_BOOTSTRAP_RETRY_DELAY = 1.0


@dataclass(frozen=True)
class LaunchAgentConfig:
    home: Path
    working_directory: Path
    uv_path: Path
    uid: int

    @property
    def plist_path(self) -> Path:
        return self.home / "Library/LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"

    @property
    def log_path(self) -> Path:
        return self.home / "Library/Logs" / _LOG_NAME

    @property
    def job_target(self) -> str:
        return f"gui/{self.uid}/{LAUNCH_AGENT_LABEL}"

    @property
    def gui_target(self) -> str:
        return f"gui/{self.uid}"

    def plist_bytes(self) -> bytes:
        return plistlib.dumps(
            {
                "Label": LAUNCH_AGENT_LABEL,
                "WorkingDirectory": str(self.working_directory),
                "ProgramArguments": [
                    str(self.uv_path),
                    "run",
                    "headless-obsidian-mcp",
                    "run",
                ],
                "RunAtLoad": True,
                "KeepAlive": True,
                "StandardOutPath": str(self.log_path),
                "StandardErrorPath": str(self.log_path),
                "ThrottleInterval": 10,
            }
        )


Runner = Callable[..., subprocess.CompletedProcess[Any]]


class LaunchAgentService:
    def __init__(
        self,
        config: LaunchAgentConfig,
        *,
        runner: Runner = subprocess.run,
        stop_existing: Callable[[], str] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.runner = runner
        self.stop_existing = stop_existing
        self.sleeper = sleeper

    @classmethod
    def from_defaults(
        cls, *, working_directory: Path | None = None
    ) -> "LaunchAgentService":
        if sys.platform != "darwin":
            raise RuntimeError("LaunchAgent install is only supported on macOS")
        uv = shutil.which("uv")
        if uv is None:
            raise RuntimeError("uv was not found on PATH")
        config = LaunchAgentConfig(
            home=Path.home(),
            working_directory=(working_directory or Path.cwd()).resolve(),
            uv_path=Path(uv),
            uid=os.getuid(),
        )
        return cls(config, stop_existing=lambda: DaemonService.from_settings().stop())

    def install(self, *, start: bool = True) -> Path:
        self.config.plist_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.plist_path.write_bytes(self.config.plist_bytes())

        if not start:
            return self.config.plist_path

        self._launchctl(["bootout", self.config.job_target], check=False)
        if self.stop_existing is not None:
            self.stop_existing()
        self._bootstrap()
        self._launchctl(["kickstart", "-k", self.config.job_target], check=True)
        return self.config.plist_path

    def uninstall(self) -> Path:
        self._launchctl(["bootout", self.config.job_target], check=False)
        self.config.plist_path.unlink(missing_ok=True)
        return self.config.plist_path

    def _launchctl(self, args: Sequence[str], *, check: bool) -> None:
        self.runner(["launchctl", *args], check=check)

    def _bootstrap(self) -> None:
        args = ["bootstrap", self.config.gui_target, str(self.config.plist_path)]
        try:
            self._launchctl(args, check=True)
        except subprocess.CalledProcessError:
            self.sleeper(_BOOTSTRAP_RETRY_DELAY)
            self._launchctl(args, check=True)
