import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from headless_obsidian_mcp.app.launch_agent import (
    LAUNCH_AGENT_LABEL,
    LaunchAgentConfig,
    LaunchAgentService,
)


class LaunchAgentTests(unittest.TestCase):
    def test_plist_runs_server_in_foreground(self) -> None:
        config = LaunchAgentConfig(
            home=Path("/Users/me"),
            working_directory=Path("/repo"),
            uv_path=Path("/opt/homebrew/bin/uv"),
            uid=501,
        )

        plist = plistlib.loads(config.plist_bytes())

        self.assertEqual(plist["Label"], LAUNCH_AGENT_LABEL)
        self.assertEqual(plist["WorkingDirectory"], "/repo")
        self.assertEqual(
            plist["ProgramArguments"],
            ["/opt/homebrew/bin/uv", "run", "headless-obsidian-mcp", "run"],
        )
        self.assertTrue(plist["RunAtLoad"])
        self.assertTrue(plist["KeepAlive"])
        self.assertEqual(
            plist["StandardOutPath"],
            "/Users/me/Library/Logs/headless-obsidian-mcp.launchd.log",
        )
        self.assertEqual(
            plist["StandardErrorPath"],
            "/Users/me/Library/Logs/headless-obsidian-mcp.launchd.log",
        )

    def test_install_writes_plist_and_starts_launchd_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = LaunchAgentConfig(
                home=home,
                working_directory=Path("/repo"),
                uv_path=Path("/opt/homebrew/bin/uv"),
                uid=501,
            )
            runner = Mock(
                return_value=subprocess.CompletedProcess(
                    args=["launchctl"], returncode=0
                )
            )
            stop_existing = Mock(return_value="stopped")
            service = LaunchAgentService(
                config, runner=runner, stop_existing=stop_existing
            )

            path = service.install(start=True)

            self.assertEqual(
                path, home / "Library/LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
            )
            self.assertTrue(path.exists())
            stop_existing.assert_called_once_with()
            self.assertEqual(
                [call.args[0] for call in runner.call_args_list],
                [
                    ["launchctl", "bootout", "gui/501/com.headlessobsidianmcp.server"],
                    ["launchctl", "bootstrap", "gui/501", str(path)],
                    [
                        "launchctl",
                        "kickstart",
                        "-k",
                        "gui/501/com.headlessobsidianmcp.server",
                    ],
                ],
            )
            self.assertEqual(runner.call_args_list[0].kwargs["check"], False)
            self.assertEqual(runner.call_args_list[1].kwargs["check"], True)
            self.assertEqual(runner.call_args_list[2].kwargs["check"], True)

    def test_install_retries_bootstrap_once_after_bootout_race(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = LaunchAgentConfig(
                home=home,
                working_directory=Path("/repo"),
                uv_path=Path("/opt/homebrew/bin/uv"),
                uid=501,
            )
            runner = Mock(
                side_effect=[
                    subprocess.CompletedProcess(args=["launchctl"], returncode=0),
                    subprocess.CalledProcessError(
                        5,
                        [
                            "launchctl",
                            "bootstrap",
                            "gui/501",
                            str(config.plist_path),
                        ],
                    ),
                    subprocess.CompletedProcess(args=["launchctl"], returncode=0),
                    subprocess.CompletedProcess(args=["launchctl"], returncode=0),
                ]
            )
            sleep = Mock()
            service = LaunchAgentService(config, runner=runner, sleeper=sleep)

            service.install(start=True)

            self.assertEqual(
                [call.args[0] for call in runner.call_args_list],
                [
                    ["launchctl", "bootout", "gui/501/com.headlessobsidianmcp.server"],
                    ["launchctl", "bootstrap", "gui/501", str(config.plist_path)],
                    ["launchctl", "bootstrap", "gui/501", str(config.plist_path)],
                    [
                        "launchctl",
                        "kickstart",
                        "-k",
                        "gui/501/com.headlessobsidianmcp.server",
                    ],
                ],
            )
            sleep.assert_called_once()

    def test_uninstall_boots_out_and_removes_plist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = LaunchAgentConfig(
                home=home,
                working_directory=Path("/repo"),
                uv_path=Path("/opt/homebrew/bin/uv"),
                uid=501,
            )
            path = config.plist_path
            path.parent.mkdir(parents=True)
            path.write_bytes(config.plist_bytes())
            runner = Mock(
                return_value=subprocess.CompletedProcess(
                    args=["launchctl"], returncode=0
                )
            )
            service = LaunchAgentService(config, runner=runner)

            removed = service.uninstall()

            self.assertEqual(removed, path)
            self.assertFalse(path.exists())
            runner.assert_called_once_with(
                ["launchctl", "bootout", "gui/501/com.headlessobsidianmcp.server"],
                check=False,
            )


if __name__ == "__main__":
    unittest.main()
