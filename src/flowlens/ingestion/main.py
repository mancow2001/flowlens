"""Flow Ingestion Service entry point.

Runs the UDP flow collector as a standalone service.
"""

import asyncio
import signal
import sys
from typing import NoReturn

from flowlens.common.config import get_settings
from flowlens.common.database import close_database, init_database
from flowlens.common.logging import get_logger, setup_logging
from flowlens.common.metrics import set_app_info
from flowlens.ingestion.server import FlowCollector

logger = get_logger(__name__)


async def main() -> None:
    """Main entry point for ingestion service."""
    settings = get_settings()

    # Setup logging
    setup_logging(settings.logging)

    # Set app info for metrics
    set_app_info(
        version=settings.app_version,
        environment=settings.environment,
    )

    logger.info(
        "Starting Flow Ingestion Service",
        version=settings.app_version,
        environment=settings.environment,
    )

    # Initialize database
    await init_database(settings)

    # Create collector
    collector = FlowCollector(settings.ingestion)

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler(sig: int) -> None:
        logger.info("Received shutdown signal", signal=sig)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        # Start collector
        await collector.start()

        # Wait for shutdown signal
        await stop_event.wait()

    except Exception as e:
        logger.error("Fatal error", error=str(e))
        raise
    finally:
        # Graceful shutdown
        logger.info("Shutting down")
        await collector.stop()
        await close_database()
        logger.info("Shutdown complete")


def run() -> NoReturn:
    """Run the ingestion service."""
    try:
        # Use uvloop for better performance
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except ImportError:
            pass

        asyncio.run(main())
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.error("Service failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    run()
