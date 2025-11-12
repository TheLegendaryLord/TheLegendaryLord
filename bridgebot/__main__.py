"""CLI entry point for the bridge bot."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bridgebot.bridge import BridgeBot
from bridgebot.config import ConfigError, load_config


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Telegram to Discord bridge bot")
    parser.add_argument("config", type=Path, help="Path to the configuration JSON file")
    return parser.parse_args()


def configure_logging() -> None:
    """Configure basic logging output."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main() -> None:
    """Run the bridge bot."""

    args = parse_args()
    configure_logging()
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logging.getLogger(__name__).error("Configuration error: %s", exc)
        raise SystemExit(2) from exc
    bot = BridgeBot(config)
    bot.run()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
