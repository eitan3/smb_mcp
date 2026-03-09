"""Configuration models for the Network MCP Server."""

import os
import json
from typing import Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

from .exceptions import NetworkMCPError, ConfigurationError


class SMBShareConfig(BaseModel):
    """Configuration for SMB/CIFS share."""
    
    type: Literal["smb"] = "smb"
    name: str = Field(..., description="Name of the SMB server")
    host: str = Field(..., description="SMB server hostname or IP address")
    share_name: str = Field(..., description="Name of the SMB share")
    username: str = Field(..., description="Username for authentication")
    password: Optional[str] = Field(default=None, description="Password for authentication")
    domain: str = Field(default="", description="Domain for authentication")
    port: int = Field(default=445, description="SMB port (usually 445)")
    use_ntlm_v2: bool = Field(default=True, description="Use NTLMv2 authentication")
    timeout: int = Field(default=30, description="Connection timeout in seconds")


class NFSShareConfig(BaseModel):
    """Configuration for NFS share (future implementation)."""
    
    type: Literal["nfs"] = "nfs"
    host: str = Field(..., description="NFS server hostname or IP address")
    export_path: str = Field(..., description="NFS export path")
    version: str = Field(default="3", description="NFS version")
    mount_options: List[str] = Field(default_factory=list, description="NFS mount options")


class SecurityConfig(BaseModel):
    """Security configuration for the server."""
    
    allowed_extensions: List[str] = Field(
        default_factory=list,
        description="Allowed file extensions (empty list = all extensions allowed)"
    )
    blocked_extensions: List[str] = Field(
        default_factory=list,
        description="Blocked file extensions"
    )
    max_file_size: str = Field(default="100MB", description="Maximum file size")
    allowed_paths: List[str] = Field(
        default_factory=list,
        description="Allowed paths (empty means all paths allowed)"
    )
    blocked_paths: List[str] = Field(
        default_factory=lambda: ["/etc", "/root", "/sys", "/proc"],
        description="Blocked paths"
    )
    enable_write: bool = Field(default=True, description="Enable write operations")
    enable_delete: bool = Field(default=True, description="Enable delete operations")


class NetworkMCPConfig(BaseModel):
    """Main configuration for the Network MCP Server."""
    
    shares: Dict[str, Union[SMBShareConfig, NFSShareConfig]] = Field(
        ..., description="Configured network shares"
    )
    security: SecurityConfig = Field(
        default_factory=SecurityConfig, description="Security settings"
    )
    logging_level: str = Field(default="INFO", description="Logging level")
    max_connections: int = Field(default=10, description="Maximum concurrent connections")


def parse_file_size(size_str: str) -> int:
    """Parse file size string like '100MB' to bytes."""
    size_str = size_str.upper().strip()
    
    if size_str.endswith('KB'):
        return int(size_str[:-2]) * 1024
    elif size_str.endswith('MB'):
        return int(size_str[:-2]) * 1024 * 1024
    elif size_str.endswith('GB'):
        return int(size_str[:-2]) * 1024 * 1024 * 1024
    elif size_str.endswith('B'):
        return int(size_str[:-1])
    else:
        # Assume bytes if no unit
        return int(size_str)


def parse_json_list(env_value: str, default: Optional[List[str]] = None) -> List[str]:
    """Parse a JSON list from environment variable."""
    if not env_value:
        return default if default is not None else []
    
    try:
        result = json.loads(env_value)
        if isinstance(result, list):
            return [str(item) for item in result]
        return [str(result)]
    except json.JSONDecodeError:
        # If not JSON, treat as single value
        return [env_value]


def parse_json_bool(env_value: str, default: bool) -> bool:
    """Parse boolean from environment variable."""
    if not env_value:
        return default
    return env_value.lower() in ("true", "1", "yes", "on")


def load_config_from_env() -> NetworkMCPConfig:
    """Load configuration from environment variables.
    
    Environment variable format:
    - SMB_NAMES='["share1", "share2"]'
    - SMB_HOSTS='["192.168.1.100", "192.168.1.101"]'
    - SMB_SHARE_NAMES='["data", "backup"]'
    - SMB_USERNAMES='["user1", "user2"]'
    - SMB_PASSWORDS='["pass1", "pass2"]'
    - SMB_DOMAINS='["WORKGROUP", "DOMAIN"]'
    - SMB_PORTS='[445, 445]'
    
    Returns:
        NetworkMCPConfig: Configuration loaded from environment variables
        
    Raises:
        ConfigurationError: If required environment variables are missing or invalid
    """
    # Load share lists
    names = parse_json_list(os.getenv("SMB_NAMES", "[]"))
    hosts = parse_json_list(os.getenv("SMB_HOSTS", "[]"))
    share_names = parse_json_list(os.getenv("SMB_SHARE_NAMES", "[]"))
    usernames = parse_json_list(os.getenv("SMB_USERNAMES", "[]"))
    passwords = parse_json_list(os.getenv("SMB_PASSWORDS", "[]"))
    domains = parse_json_list(os.getenv("SMB_DOMAINS", "[]"))
    ports = parse_json_list(os.getenv("SMB_PORTS", "[]"))
    
    # Validate we have at least one share configured
    if not hosts:
        raise ConfigurationError(
            "SMB_HOSTS environment variable is required. "
            "Set it as a JSON list: SMB_HOSTS='[\"192.168.1.100\"]'"
        )
    
    # Build shares dictionary
    shares = {}
    num_shares = len(hosts)
    
    for i in range(num_shares):
        # Generate name if not provided
        name = names[i] if i < len(names) else f"share_{i+1}"
        
        # Get share name (required for each share)
        if i >= len(share_names) or not share_names[i]:
            raise ConfigurationError(
                f"SMB_SHARE_NAMES must have an entry for share at index {i}. "
                f"Current value: {share_names}"
            )
        
        # Get username (required for each share)
        if i >= len(usernames) or not usernames[i]:
            raise ConfigurationError(
                f"SMB_USERNAMES must have an entry for share at index {i}. "
                f"Current value: {usernames}"
            )
        
        # Get password (required for each share)
        password = passwords[i] if i < len(passwords) else None
        if not password:
            raise ConfigurationError(
                f"SMB_PASSWORDS must have an entry for share at index {i}. "
                f"Current value: {passwords}"
            )
        
        # Create share config
        share_config = SMBShareConfig(
            name=name,
            host=hosts[i],
            share_name=share_names[i],
            username=usernames[i],
            password=password,
            domain=domains[i] if i < len(domains) else "",
            port=int(ports[i]) if i < len(ports) and ports[i] else 445,
        )
        shares[name] = share_config
    
    # Load security config with defaults
    default_allowed_ext = []  # ".txt", ".py", ".json", ".md", ".yaml", ".yml", ".xml", ".csv"
    default_blocked_ext = []  # ".exe", ".bat", ".cmd", ".ps1", ".sh"
    default_blocked_paths = ["/etc", "/root", "/sys", "/proc"]
    
    allowed_ext_env = os.getenv("SMB_ALLOWED_EXTENSIONS", "")
    blocked_ext_env = os.getenv("SMB_BLOCKED_EXTENSIONS", "")
    blocked_paths_env = os.getenv("SMB_BLOCKED_PATHS", "")
    
    security = SecurityConfig(
        allowed_extensions=parse_json_list(allowed_ext_env) if allowed_ext_env else default_allowed_ext,
        blocked_extensions=parse_json_list(blocked_ext_env) if blocked_ext_env else default_blocked_ext,
        max_file_size=os.getenv("SMB_MAX_FILE_SIZE", "10000MB"),
        allowed_paths=parse_json_list(os.getenv("SMB_ALLOWED_PATHS", "[]")),
        blocked_paths=parse_json_list(blocked_paths_env) if blocked_paths_env else default_blocked_paths,
        enable_write=parse_json_bool(os.getenv("SMB_ENABLE_WRITE", ""), True),
        enable_delete=parse_json_bool(os.getenv("SMB_ENABLE_DELETE", ""), True),
    )
    
    return NetworkMCPConfig(
        shares=shares,
        security=security,
        logging_level=os.getenv("SMB_LOG_LEVEL", "INFO"),
        max_connections=int(os.getenv("SMB_MAX_CONNECTIONS", "10")),
    )
