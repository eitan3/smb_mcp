"""SMB MCP Server - Access SMB/CIFS network shares via MCP protocol."""

__version__ = "0.1.0"

from .server import NetworkMCPServer
from .config import load_config_from_env, NetworkMCPConfig

__all__ = ["NetworkMCPServer", "load_config_from_env", "NetworkMCPConfig", "__version__"]