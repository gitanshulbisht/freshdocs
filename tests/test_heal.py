"""Tests for the heal module (subprocess-based bdata scraper heal)."""

import shutil
import subprocess
from unittest.mock import patch

import pytest

from freshdocs.heal import HealError, heal_and_approve, find_bdata


def test_find_bdata_uses_which():
    with patch("freshdocs.heal.shutil.which", return_value="/usr/local/bin/bdata"):
        assert find_bdata() == "bdata"


def test_find_bdata_falls_back_to_npx():
    with patch("freshdocs.heal.shutil.which", side_effect=[None, "/usr/local/bin/npx"]):
        assert find_bdata() == "npx -p @brightdata/cli bdata"


def test_find_bdata_raises_when_not_found():
    with patch("freshdocs.heal.shutil.which", return_value=None):
        with pytest.raises(HealError, match="Bright Data CLI not found"):
            find_bdata()


@patch("freshdocs.heal.subprocess.run")
@patch("freshdocs.heal.find_bdata", return_value="bdata")
def test_heal_and_approve_success(mock_find, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(args="bdata", returncode=0, stdout="healed", stderr=""),
        subprocess.CompletedProcess(args="bdata", returncode=0, stdout="approved", stderr=""),
    ]
    log = heal_and_approve("c_test", "body_text extraction broken")
    assert "healed" in log
    assert "approved" in log
    assert mock_run.call_count == 2


@patch("freshdocs.heal.subprocess.run")
@patch("freshdocs.heal.find_bdata", return_value="bdata")
def test_heal_failure_raises(mock_find, mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args="bdata", returncode=1, stdout="", stderr="scrape not found"
    )
    with pytest.raises(HealError, match="heal failed"):
        heal_and_approve("c_test", "something broke")


@patch("freshdocs.heal.subprocess.run")
@patch("freshdocs.heal.find_bdata", return_value="bdata")
def test_approve_failure_raises(mock_find, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(args="bdata", returncode=0, stdout="healed", stderr=""),
        subprocess.CompletedProcess(args="bdata", returncode=1, stdout="", stderr="approve failed"),
    ]
    with pytest.raises(HealError, match="approve failed"):
        heal_and_approve("c_test", "something broke")


@patch("freshdocs.heal.subprocess.run")
@patch("freshdocs.heal.find_bdata", return_value="bdata")
def test_manual_approve_skips_approve(mock_find, mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args="bdata", returncode=0, stdout="healed", stderr=""
    )
    log = heal_and_approve("c_test", "something broke", auto_approve=False)
    assert mock_run.call_count == 1  # only heal, not approve
    assert "pending manual approval" in log
