import argparse
import getpass
import os
import sys
import warnings

import uvicorn


def configure_llm(provider: str) -> None:
    names = {
        "openai": ("OPENAI_API_KEY",),
        "nvidia": ("NVIDIA_API_KEY",),
        "both": ("OPENAI_API_KEY", "NVIDIA_API_KEY"),
    }[provider]
    pending = {}
    for name in names:
        if os.environ.get(name, "").strip():
            continue
        if not sys.stdin.isatty():
            raise ValueError(f"Set {name} in the environment or run --llm {provider} in an interactive terminal.")
        try:
            with warnings.catch_warnings():
                # Never let getpass fall back to echoing a key on an unsupported terminal.
                warnings.simplefilter("error", getpass.GetPassWarning)
                key = getpass.getpass(f"Paste {name} (input hidden): ").strip()
        except (getpass.GetPassWarning, EOFError) as exc:
            raise ValueError("Hidden input is unavailable. Run this command in your PowerShell terminal.") from exc
        if not key:
            raise ValueError(f"{name} cannot be empty.")
        pending[name] = key
    # Publish only after every requested key has been entered successfully.
    os.environ.update(pending)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start the Career Quest backend.")
    parser.add_argument(
        "--llm", choices=("openai", "nvidia", "both"),
        help="Prompt privately for missing API keys; keep them only in this process environment.",
    )
    args = parser.parse_args(argv)
    if args.llm:
        try:
            configure_llm(args.llm)
        except ValueError as exc:
            parser.error(str(exc))
        except KeyboardInterrupt:
            parser.exit(130, "\nStartup cancelled.\n")

    # Settings must be created after the key is added to the environment.
    from app.core.config import settings

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    main()
