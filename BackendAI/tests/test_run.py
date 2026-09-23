import getpass
import os
from unittest.mock import Mock

import pytest

from run import configure_llm


@pytest.fixture(autouse=True)
def clean_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)


def test_hidden_prompt_sets_only_process_environment(monkeypatch, capsys):
    monkeypatch.setattr("run.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("run.getpass.getpass", lambda prompt: " test-key ")
    configure_llm("openai")
    assert os.environ["OPENAI_API_KEY"] == "test-key"
    captured = capsys.readouterr()
    assert "test-key" not in captured.out + captured.err
    assert "NVIDIA_API_KEY" not in os.environ


def test_existing_key_needs_no_terminal_prompt(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "already-configured")
    monkeypatch.setattr("run.sys.stdin.isatty", lambda: False)
    prompt = Mock(side_effect=AssertionError("Must not prompt"))
    monkeypatch.setattr("run.getpass.getpass", prompt)
    configure_llm("openai")
    assert os.environ["OPENAI_API_KEY"] == "already-configured"
    prompt.assert_not_called()


def test_noninteractive_startup_with_missing_key_fails_clearly(monkeypatch):
    monkeypatch.setattr("run.sys.stdin.isatty", lambda: False)
    with pytest.raises(ValueError, match="interactive terminal"):
        configure_llm("openai")


def test_empty_second_key_does_not_partially_configure_providers(monkeypatch):
    monkeypatch.setattr("run.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("run.getpass.getpass", Mock(side_effect=["test-first-key", " "]))
    with pytest.raises(ValueError, match="NVIDIA_API_KEY cannot be empty"):
        configure_llm("both")
    assert "OPENAI_API_KEY" not in os.environ
    assert "NVIDIA_API_KEY" not in os.environ


def test_terminal_without_hidden_input_does_not_echo_key(monkeypatch):
    monkeypatch.setattr("run.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("run.getpass.getpass", Mock(side_effect=getpass.GetPassWarning("Cannot hide input")))
    with pytest.raises(ValueError, match="Hidden input is unavailable"):
        configure_llm("openai")
    assert "OPENAI_API_KEY" not in os.environ
