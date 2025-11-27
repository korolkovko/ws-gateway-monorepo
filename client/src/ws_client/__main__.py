"""Entry point for WebSocket Proxy Client."""

import sys
import os
import signal
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from .proxy import PaymentGatewayProxy


def main():
    """Main entry point"""
    # Load environment variables from multiple locations
    # Priority: current dir > /etc/ws-client > ~/.ws-client
    env_paths = [
        Path.cwd() / ".env",
        Path("/etc/ws-client/.env"),
        Path.home() / ".ws-client" / ".env",
    ]

    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"✅ Loaded config from: {env_path}")
            break

    # Load configuration from environment
    ws_url = os.getenv('WS_SERVER_URL')
    ws_token = os.getenv('WS_TOKEN')
    log_level = os.getenv('LOG_LEVEL', 'INFO')

    # Routing config paths (priority order)
    routing_config_paths = [
        os.getenv('ROUTING_CONFIG_PATH'),
        str(Path.cwd() / "routing_config.yaml"),
        "/etc/ws-client/routing_config.yaml",
        str(Path.home() / ".ws-client" / "routing_config.yaml"),
    ]

    routing_config_path = None
    for path in routing_config_paths:
        if path and Path(path).exists():
            routing_config_path = path
            print(f"✅ Found routing config: {routing_config_path}")
            break

    # Validate required configuration
    if not all([ws_url, ws_token]):
        print("❌ Error: Missing required environment variables")
        print("\nRequired:")
        print("  WS_SERVER_URL  - WebSocket server URL")
        print("  WS_TOKEN       - JWT authentication token")
        print("\nOptional:")
        print("  LOG_LEVEL              - Log level (default: INFO)")
        print("  ROUTING_CONFIG_PATH    - Path to routing_config.yaml")
        print("\nConfiguration locations (checked in order):")
        print("  1. Current directory: .env")
        print("  2. System config: /etc/ws-client/.env")
        print("  3. User config: ~/.ws-client/.env")
        sys.exit(1)

    if not routing_config_path:
        print("❌ Error: routing_config.yaml not found")
        print("\nSearched in:")
        for path in routing_config_paths[1:]:
            print(f"  - {path}")
        sys.exit(1)

    # Create proxy instance
    proxy = PaymentGatewayProxy(
        ws_url=ws_url,
        ws_token=ws_token,
        routing_config_path=routing_config_path,
        log_level=log_level
    )

    # Handle shutdown signals
    def signal_handler(sig, frame):
        print("\n⚠️  Received shutdown signal")
        proxy.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run proxy
    try:
        asyncio.run(proxy.run())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
