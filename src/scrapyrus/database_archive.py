"""Create and restore complete PostgreSQL database archives."""

from pathlib import Path
import subprocess
import tempfile


def dump_database(target: str | Path, conninfo: str = "") -> None:
    """Write a complete custom-format PostgreSQL archive to ``target``."""

    target = Path(target)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {target}")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"output directory does not exist: {target.parent}")

    with tempfile.NamedTemporaryFile(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        subprocess.run(
            [
                "pg_dump",
                f"--dbname={conninfo}",
                "--format=custom",
                f"--file={temporary_path}",
                "--verbose",
            ],
            check=True,
        )
        temporary_path.replace(target)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def import_database(
    source: str | Path,
    conninfo: str = "",
    *,
    no_owner: bool = False,
) -> None:
    """Restore a complete PostgreSQL archive into an existing database."""

    source = Path(source)
    subprocess.run(
        ["pg_restore", "--list", str(source)],
        check=True,
        stdout=subprocess.DEVNULL,
    )

    command = [
        "pg_restore",
        f"--dbname={conninfo}",
        "--exit-on-error",
        "--single-transaction",
        "--verbose",
    ]
    if no_owner:
        command.extend(("--no-owner", "--no-privileges"))
    command.append(str(source))
    subprocess.run(command, check=True)
