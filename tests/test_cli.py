from pathlib import Path

from scrapyrus.__main__ import main

from click.testing import CliRunner


def test_images_subcommand_triggers_image_scrape(tmp_path, monkeypatch):
    calls = []

    def fake_scrape_images(target, todo_filename, error_filename, *, idp_data):
        calls.append((target, todo_filename, error_filename, idp_data))

    monkeypatch.setattr("scrapyrus.__main__.scrape_images", fake_scrape_images)
    idp_data = tmp_path / "idp.data"
    target = tmp_path / "images"
    runner = CliRunner()

    result = runner.invoke(
        main,
        (
            "--idp-data",
            str(idp_data),
            "images",
            str(target),
            "todo.txt",
            "error.txt",
        ),
    )

    assert result.exit_code == 0
    assert calls == [(target, "todo.txt", "error.txt", idp_data)]


def test_images_subcommand_uses_defaults(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.scrape_images",
        lambda target, todo_filename, error_filename, *, idp_data: calls.append(
            (target, todo_filename, error_filename, idp_data)
        ),
    )
    runner = CliRunner()

    result = runner.invoke(main, ("images",))

    assert result.exit_code == 0
    assert calls == [
        (Path("images"), "images_todo.txt", "images_error.txt", Path("idp.data"))
    ]
