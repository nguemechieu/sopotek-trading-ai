"""Package entrypoint for the desktop runtime."""

from .launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
