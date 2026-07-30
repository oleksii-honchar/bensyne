#!/usr/bin/env python3
"""Better Mnemosyne — multi-tenant namespace-aware MCP server."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import signal
import sys
from pathlib import Path

# Add src to path for direct execution
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.infrastructure.config.manager import ConfigManager
from src.infrastructure.mnemosyne.bank_manager import BankManager
from src.services.namespace.router import NamespaceRouter
from src.app import create_application
from src.middleware.health import mark_default_instance_ready
from src.utils.logging import setup_logging


async def shutdown_handler(signum: int, router: NamespaceRouter) -> None:
    """Graceful shutdown handler.

    Args:
        signum: Signal number received.
        router: Namespace router to clean up.
    """
    logger = logging.getLogger("better-mnemosyne")
    logger.info("Received signal %d, shutting down...", signum)

    # Clean up instances
    for namespace, instance in list(router.instances.items()):
        logger.info("Cleaning up instance: %s", namespace)

    sys.exit(0)


def main() -> None:
    """Main entry point for the Better Mnemosyne server."""
    parser = argparse.ArgumentParser(
        description="Better Mnemosyne — multi-tenant namespace-aware MCP server"
    )
    parser.add_argument("--port", type=int, help="Port to listen on")
    parser.add_argument("--data-dir", type=str, help="Data directory for databases")
    parser.add_argument("--log-level", type=str, help="Log level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    # Step 1: Load config from YAML, merge CLI overrides
    config_manager = ConfigManager()
    config = config_manager.load()

    # Apply CLI overrides (dataclasses are frozen, use replace)
    if args.port is not None:
        config = dataclasses.replace(
            config,
            server=dataclasses.replace(config.server, port=args.port),
        )
    if args.data_dir is not None:
        config = dataclasses.replace(
            config,
            instance_pool=dataclasses.replace(config.instance_pool, data_dir=args.data_dir),
        )
    if args.log_level is not None:
        config = dataclasses.replace(
            config,
            logging=dataclasses.replace(config.logging, level=args.log_level),
        )

    # Step 2: Setup logging with configured level
    import os
    os.environ["LOG_LEVEL"] = config.logging.level
    logger = setup_logging()
    logger.info("Starting better-mnemosyne")
    logger.info("Config: port=%d, data_dir=%s, log_level=%s",
                config.server.port, config.instance_pool.data_dir, config.logging.level)

    # Step 3: Create BankManager with configured data_dir
    bank_manager = BankManager(
        data_dir=config.instance_pool.data_dir,
        default_bank=config.instance_pool.default_bank,
    )

    # Step 4: Create NamespaceRouter — creates default instance at boot
    router = NamespaceRouter(
        config=config.instance_pool,
        bank_manager=bank_manager,
    )

    # Step 5: Create FastMCP server, register all tools with router injected
    app = create_application(config, router)

    # Step 6: Call health.mark_default_instance_ready()
    mark_default_instance_ready()

    # Step 7: Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.ensure_future(shutdown_handler(s, router)),
        )

    # Step 8: Start server
    logger.info("Server listening on %s:%d", config.server.host, config.server.port)
    app.run(
        transport="streamable-http",
        host=config.server.host,
        port=config.server.port,
    )


if __name__ == "__main__":
    main()
