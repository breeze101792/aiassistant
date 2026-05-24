#!/usr/bin/env python3
"""AI Assistant — Remote Module Entry Point.

Connect a module to a remote bus via WebSocket. Use this to run
hardware-dependent modules (ears, mouth, eyes) on a separate machine
while the brain runs on the main host.

Usage:
  python main_remote.py --module MODULE [options]

Options:
  --module MODULE   Module type to run (ears, mouth, eyes, hands, etc.)
  --bus URL         Bus WebSocket URL (default: ws://127.0.0.1:8765)
  --token TOKEN     Auth token matching main bus remote_auth_token
  -h, --help        Show this help and exit

Examples:
  # Run ears (microphone/speech recognition) on a Pi, connect to main host
  python main_remote.py --module ears --bus ws://192.168.1.100:8765

  # Run mouth (TTS) on a machine with speakers
  python main_remote.py --module mouth --bus ws://192.168.1.100:8765

  # With auth token
  python main_remote.py --module hands --bus ws://10.0.0.5:8765 --token mysecret

Setup:
  On the main host, config.yaml must have:
    bus:
      websocket_port: 8765
      remote_auth_token: ""   # or set a shared secret
"""

import argparse
import asyncio
import json
import logging
import sys

import websockets

logger = logging.getLogger("remote")


async def connect_module(module_type: str, bus_url: str, token: str, config: dict):
    try:
        async with websockets.connect(bus_url) as ws:
            # Authenticate
            if token:
                await ws.send(json.dumps({"token": token}))

            # Register
            await ws.send(json.dumps({
                "action": "register",
                "module_name": module_type,
                "payload": {},
            }))

            logger.info(f"Registered as {module_type} on {bus_url}")

            # Subscribe to relevant topics
            await ws.send(json.dumps({
                "action": "subscribe",
                "topic": f"command.{module_type}.*",
            }))

            # Listen for messages and forward
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                    data = json.loads(msg)
                    topic = data.get("topic", "")
                    payload = data.get("payload", {})
                    logger.debug(f"Received: {topic}")

                    # Forward to local module logic
                    # (module-specific handling would go here)

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error: {e}")
                    break

    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return 1

    return 0


async def main():
    parser = argparse.ArgumentParser(
        description="Connect a module to a remote AI Assistant bus over WebSocket.",
        add_help=False,
    )
    parser.add_argument("--module", required=True,
                        help="Module type (ears, mouth, eyes, hands, etc.)")
    parser.add_argument("--bus", default="ws://127.0.0.1:8765",
                        help="Bus WebSocket URL (default: ws://127.0.0.1:8765)")
    parser.add_argument("--token", default="",
                        help="Auth token matching main bus remote_auth_token")
    parser.add_argument("-h", "--help", action="store_true",
                        help="Show help message and exit")
    args = parser.parse_args()

    if args.help:
        parser.print_help()
        print()
        print(__doc__)
        return 0

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = {}
    return await connect_module(args.module, args.bus, args.token, config)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
