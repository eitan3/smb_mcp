"""Command-line interface for the Network MCP Server."""

import asyncio
import logging
import sys
import os

from .server import NetworkMCPServer
from .config import load_config_from_env
from .exceptions import ConfigurationError


# Setup stderr logging for debugging
def setup_stderr_logging():
    """Setup logging to stderr for debugging."""
    log_level = os.getenv("SMB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)
    
    # Configure root logger to write to stderr
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stderr,
        force=True
    )


def main() -> None:
    """Main entry point for the SMB MCP server.
    
    Loads configuration from environment variables and runs the MCP server.
    """
    # Setup logging first
    setup_stderr_logging()
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("SMB MCP Server starting...")
        logger.debug("Loading configuration from environment variables")
        
        # Load configuration from environment variables
        config = load_config_from_env()
        
        logger.info(f"Configuration loaded: {len(config.shares)} share(s) configured")
        for share_name in config.shares.keys():
            logger.debug(f"  - Share configured: {share_name}")
        
        # Create and run the server
        logger.debug("Initializing NetworkMCPServer")
        server = NetworkMCPServer(config)
        
        logger.info("Starting MCP server...")
        asyncio.run(server.run())
        
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        print(f"Configuration error: {e}", file=sys.stderr)
        print("\nPlease set the required environment variables:", file=sys.stderr)
        print("  SMB_HOSTS='[\"192.168.1.100\"]'", file=sys.stderr)
        print("  SMB_SHARE_NAMES='[\"shared_folder\"]'", file=sys.stderr)
        print("  SMB_USERNAMES='[\"username\"]'", file=sys.stderr)
        print("  SMB_PASSWORDS='[\"password\"]'", file=sys.stderr)
        print("\nSee .env.example for all available options.", file=sys.stderr)
        sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        print("\nServer stopped by user", file=sys.stderr)
        sys.exit(0)
        
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
