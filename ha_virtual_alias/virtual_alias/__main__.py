import asyncio
import signal

from .app import create_app


async def main():
    app = create_app()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await app.start()

    try:
        await stop.wait()
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
