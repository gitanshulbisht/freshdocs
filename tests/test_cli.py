"""Tests for the freshdocs CLI (refresh, heal, status commands)."""

from unittest.mock import MagicMock, patch

import pytest

from freshdocs.cli import main as cli_main
from freshdocs.rag import RagError
from freshdocs.schemas import HealthCheckFailure


def test_cli_refresh_dry_run(tmp_path):
    """refresh --dry-run should call collect + refresh_source without writing."""
    fake_rows = [
        {"url": "https://docs.docker.com/", "title": "Docker", "body_text": "content", "last_updated": "2026-08-10"},
    ]
    mock_source = MagicMock(key="docker", sitemap_url="https://docs.docker.com/sitemap.xml")
    mock_pipeline = MagicMock()
    mock_pipeline.data_dir = tmp_path
    mock_pipeline.outputs_dir = tmp_path / "outputs"
    mock_pipeline.outputs_dir.mkdir(exist_ok=True)
    mock_outcome = MagicMock(ok=True, rows=1, failures=[], notes="dry run")
    mock_pipeline.refresh_source.return_value = mock_outcome

    with patch("freshdocs.cli.load_registry", return_value=MagicMock(sources=[mock_source])), \
         patch("freshdocs.cli.Rag", side_effect=RagError("no key")), \
         patch("freshdocs.cli.Pipeline", return_value=mock_pipeline), \
         patch("freshdocs.cli.collect_source", return_value=fake_rows):
        rc = cli_main(["--data-dir", str(tmp_path), "refresh", "--dry-run"])
    assert rc == 0
    mock_pipeline.refresh_source.assert_called_once()
    _, kwargs = mock_pipeline.refresh_source.call_args
    assert kwargs["dry_run"] is True


def test_cli_refresh_unknown_source(tmp_path):
    """An unknown --source value should exit with code 2."""
    registry = MagicMock()
    registry.sources = []
    with patch("freshdocs.cli.load_registry", return_value=registry):
        rc = cli_main(["--data-dir", str(tmp_path), "refresh", "--source", "nonexistent"])
    assert rc == 2


def test_cli_refresh_handles_source_failure(tmp_path):
    """If collect_source raises, refresh should continue with other sources and exit 1."""
    fake_rows = [
        {"url": "https://docs.docker.com/", "title": "Docker", "body_text": "content", "last_updated": "2026-08-10"},
    ]
    mock_source = MagicMock(key="docker", sitemap_url="https://docs.docker.com/sitemap.xml")
    registry = MagicMock()
    registry.sources = [mock_source]

    mock_pipeline = MagicMock()
    mock_pipeline.data_dir = tmp_path
    mock_pipeline.outputs_dir = tmp_path / "outputs"
    mock_pipeline.outputs_dir.mkdir(exist_ok=True)
    mock_outcome = MagicMock(ok=True, rows=1, failures=[], notes="ok")
    mock_pipeline.refresh_source.return_value = mock_outcome

    with patch("freshdocs.cli.load_registry", return_value=registry), \
         patch("freshdocs.cli.Rag", side_effect=RagError("no key")), \
         patch("freshdocs.cli.Pipeline", return_value=mock_pipeline), \
         patch("freshdocs.cli.collect_source", side_effect=RuntimeError("network error")):
        rc = cli_main(["--data-dir", str(tmp_path), "refresh"])
    assert rc == 1
    mock_pipeline.refresh_source.assert_not_called()


def test_cli_refresh_heal_on_failure(tmp_path):
    """When --heal is set and refresh_source reports a health failure,
    heal_and_approve should be called and recorded."""
    fake_rows = [{"url": "", "title": "", "body_text": ""}]
    mock_source = MagicMock(
        key="fixture", sitemap_url="http://localhost/sitemap.xml",
        collector_id="c_test123",
    )
    registry = MagicMock()
    registry.sources = [mock_source]

    mock_pipeline = MagicMock()
    mock_pipeline.data_dir = tmp_path
    mock_pipeline.outputs_dir = tmp_path / "outputs"
    mock_pipeline.outputs_dir.mkdir(exist_ok=True)

    failure = HealthCheckFailure(source="fixture", collector_id="c_test123", symptom="empty_body_text")
    mock_outcome = MagicMock(ok=False, rows=0, failures=[failure], notes="")
    mock_pipeline.refresh_source.return_value = mock_outcome

    with patch("freshdocs.cli.load_registry", return_value=registry), \
         patch("freshdocs.cli.Rag", side_effect=RagError("no key")), \
         patch("freshdocs.cli.Pipeline", return_value=mock_pipeline), \
         patch("freshdocs.cli.collect_source", return_value=fake_rows), \
         patch("freshdocs.cli.heal_and_approve", return_value="scrape healed successfully") as mock_heal:
        rc = cli_main(["--data-dir", str(tmp_path), "refresh", "--heal"])

    assert rc == 1  # health failure → failed = True
    mock_heal.assert_called_once_with("c_test123", "empty_body_text")
    mock_pipeline.index.record_heal.assert_called_once()


def test_cli_refresh_dry_run_does_not_heal(tmp_path):
    """--dry-run should not trigger healing even if there are failures."""
    fake_rows = [{"url": "", "title": "", "body_text": ""}]
    mock_source = MagicMock(
        key="fixture", sitemap_url="http://localhost/sitemap.xml",
        collector_id="c_test123",
    )
    registry = MagicMock()
    registry.sources = [mock_source]

    mock_pipeline = MagicMock()
    mock_pipeline.data_dir = tmp_path
    mock_pipeline.outputs_dir = tmp_path / "outputs"
    mock_pipeline.outputs_dir.mkdir(exist_ok=True)

    failure = HealthCheckFailure(source="fixture", collector_id="c_test123", symptom="empty_body_text")
    mock_outcome = MagicMock(ok=False, rows=0, failures=[failure], notes="dry run")
    mock_pipeline.refresh_source.return_value = mock_outcome

    with patch("freshdocs.cli.load_registry", return_value=registry), \
         patch("freshdocs.cli.Rag", side_effect=RagError("no key")), \
         patch("freshdocs.cli.Pipeline", return_value=mock_pipeline), \
         patch("freshdocs.cli.collect_source", return_value=fake_rows), \
         patch("freshdocs.cli.heal_and_approve") as mock_heal:
        rc = cli_main(["--data-dir", str(tmp_path), "refresh", "--dry-run", "--heal"])

    mock_heal.assert_not_called()
    assert rc == 1


def test_cli_status_prints_json(tmp_path):
    """The status command should print pipeline status as JSON."""
    mock_status = {"sources": [], "runs": [], "heals": []}
    mock_pipeline = MagicMock()
    mock_pipeline.status.return_value = mock_status

    with patch("freshdocs.cli.load_registry", return_value=MagicMock()), \
         patch("freshdocs.cli.Rag", side_effect=RagError("no key")), \
         patch("freshdocs.cli.Pipeline", return_value=mock_pipeline):
        rc = cli_main(["--data-dir", str(tmp_path), "status"])

    assert rc == 0
    assert mock_pipeline.status.called


def test_cli_heal_command_calls_heal_and_approve(tmp_path):
    """The heal subcommand should call heal_and_approve and print the result."""
    with patch("freshdocs.cli.heal_and_approve", return_value="scrape healed") as mock_heal:
        rc = cli_main(["--data-dir", str(tmp_path), "heal", "c_test123", "empty_body_text"])

    assert rc == 0
    mock_heal.assert_called_once_with("c_test123", "empty_body_text", auto_approve=True)


def test_cli_heal_command_manual(tmp_path):
    """--manual flag should set auto_approve=False."""
    with patch("freshdocs.cli.heal_and_approve", return_value="proposed heal") as mock_heal:
        rc = cli_main(["--data-dir", str(tmp_path), "heal", "c_test123", "symptom", "--manual"])

    assert rc == 0
    mock_heal.assert_called_once_with("c_test123", "symptom", auto_approve=False)


def test_cli_requires_subcommand():
    """Running with no subcommand should exit with an error."""
    with pytest.raises(SystemExit):
        cli_main([])
