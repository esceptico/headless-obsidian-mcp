import os
from pathlib import Path

import click

from headless_obsidian_mcp.app.daemon import DaemonService
from headless_obsidian_mcp.app.launch_agent import LaunchAgentService
from headless_obsidian_mcp.core.config import load_settings
from headless_obsidian_mcp.core.constants import DEFAULT_SEARCH_LIMIT
from headless_obsidian_mcp.core.logging import configure_default_logging
from headless_obsidian_mcp.core.types import SearchMode
from headless_obsidian_mcp.transport.http import main as serve_main
from headless_obsidian_mcp.vault.service import Vault


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    pass


@cli.command()
@click.option("--host", default=None)
@click.option("--port", type=int, default=None)
def run(host: str | None, port: int | None) -> None:
    run_server(host, port)


@cli.command()
@click.option("--host", default=None)
@click.option("--port", type=int, default=None)
def start(host: str | None, port: int | None) -> None:
    pid = DaemonService.from_settings(host=host, port=port).start()
    click.echo(f"started, pid={pid}")


@cli.command()
@click.option("--timeout", type=float, default=None)
def stop(timeout: float | None) -> None:
    service = DaemonService.from_settings()
    click.echo(service.stop(timeout) if timeout is not None else service.stop())


@cli.command()
@click.option("--host", default=None)
@click.option("--port", type=int, default=None)
def status(host: str | None, port: int | None) -> None:
    click.echo(DaemonService.from_settings(host=host, port=port).status())


@cli.command()
@click.option("-f", "--follow", is_flag=True)
def logs(follow: bool) -> None:
    DaemonService.from_settings().logs(follow=follow)


@cli.command("install-launch-agent")
@click.option(
    "--working-directory",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
)
@click.option("--no-start", is_flag=True)
def install_launch_agent(working_directory: Path | None, no_start: bool) -> None:
    service = LaunchAgentService.from_defaults(working_directory=working_directory)
    path = service.install(start=not no_start)
    action = "installed" if no_start else "installed and started"
    click.echo(f"{action}: {path}")


@cli.command("uninstall-launch-agent")
@click.option(
    "--working-directory",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
)
def uninstall_launch_agent(working_directory: Path | None) -> None:
    service = LaunchAgentService.from_defaults(working_directory=working_directory)
    path = service.uninstall()
    click.echo(f"uninstalled: {path}")


@cli.command()
@click.argument("query")
@click.option("--limit", type=int, default=DEFAULT_SEARCH_LIMIT)
def search(query: str, limit: int) -> None:
    settings = load_settings()
    vault = Vault(settings.vault, settings.embeddings)
    click.echo(vault.search(query, limit=limit, mode=SearchMode.BM25).to_dict())


def main() -> None:
    cli()


def run_server(host: str | None, port: int | None) -> None:
    if host:
        os.environ["HEADLESS_OBSIDIAN_MCP_HOST"] = host
    if port is not None:
        os.environ["HEADLESS_OBSIDIAN_MCP_PORT"] = str(port)

    configure_default_logging()
    serve_main()


if __name__ == "__main__":
    main()
