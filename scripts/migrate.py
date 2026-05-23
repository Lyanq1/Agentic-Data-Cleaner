"""Run Alembic database migrations programmatically.

Usage:
    python scripts/migrate.py              # upgrade to head
    python scripts/migrate.py --revision <rev>  # upgrade to specific revision

TODO: set up Alembic with: alembic init alembic
"""
import subprocess
import sys
import typer

app = typer.Typer()


@app.command()
def migrate(revision: str = typer.Option("head", help="Target revision")) -> None:
    """Run Alembic upgrade migrations."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    app()
