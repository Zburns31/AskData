from askdata.app.cli import main as cli_main


def main() -> None:
    """Delegate package execution to the CLI entry point and exit with its status."""
    raise SystemExit(cli_main())
