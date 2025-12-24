"""Enrichment Service entry point.

Runs enrichment workers to process flow records.
"""

import asyncio
import signal
import sys
from typing import NoReturn

from flowlens.common.config import get_settings
from flowlens.common.database import close_database, init_database
from flowlens.common.logging import get_logger, setup_logging
from flowlens.common.metrics import set_app_info
from flowlens.enrichment.worker import EnrichmentWorker

logger = get_logger(__name__)


async def main() -> None:
    """Main entry point for enrichment service."""
    settings = get_settings()

    # Setup logging
    setup_logging(settings.logging)

    # Set app info for metrics
    set_app_info(
        version=settings.app_version,
        environment=settings.environment,
    )

    logger.info(
        "Starting Enrichment Service",
        version=settings.app_version,
        environment=settings.environment,
        worker_count=settings.enrichment.worker_count,
    )

    # Initialize database
    await init_database(settings)

    # Create workers
    workers = [
        EnrichmentWorker(settings.enrichment)
        for _ in range(settings.enrichment.worker_count)
    ]

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler(sig: int) -> None:
        logger.info("Received shutdown signal", signal=sig)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        # Start all workers
        worker_tasks = [
            asyncio.create_task(worker.start())
            for worker in workers
        ]

        # Wait for shutdown signal
        await stop_event.wait()

        # Stop workers
        logger.info("Stopping workers")
        for worker in workers:
            await worker.stop()

        # Wait for tasks to complete
        for task in worker_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error("Fatal error", error=str(e))
        raise
    finally:
        # Cleanup
        logger.info("Cleaning up")
        for worker in workers:
            await worker.cleanup()
        await close_database()
        logger.info("Shutdown complete")


def run() -> NoReturn:
    """Run the enrichment service."""
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
