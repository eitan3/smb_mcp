# EH SMB MCP Server

A Model Context Protocol (MCP) server that provides secure access to SMB/CIFS network shares. This server allows AI assistants to interact with files on network drives through a controlled, validated interface.

## Features

- 🔌 **Multiple SMB Shares**: Connect to multiple SMB/CIFS shares simultaneously
- 🔒 **Security Controls**: Configurable file extension filtering, path restrictions, and size limits
- 🌍 **Environment-Based Configuration**: All settings via environment variables (no config files needed)
- 📦 **Easy Installation**: Install and run directly with `uvx`
- 🛡️ **Safety First**: Write and delete operations can be disabled independently

## Attribution

The original code is from [festion/mcp-servers](https://github.com/festion/mcp-servers/tree/main/mcp-servers/network-mcp-server/src/network_mcp).

## Available Tools

The server provides the following MCP tools:

### Core File Operations
1. **`list_network_directory`** - List contents of a network directory
2. **`read_network_file`** - Read contents of a file
3. **`write_network_file`** - Write contents to a file (if enabled)
4. **`delete_network_file`** - Delete a file (if enabled)
5. **`create_network_directory`** - Create a directory
6. **`get_network_file_info`** - Get file/directory metadata
7. **`get_share_info`** - Get information about configured shares

### File Transfer Operations
8. **`copy_from_network`** - Copy files from network share to local directory (supports glob patterns)
9. **`copy_to_network`** - Copy files from local filesystem to network share (supports glob patterns)
10. **`move_in_network`** - Move files within a network share (supports glob patterns)

### Rename Operations
11. **`rename_network_item`** - Rename a single file or directory
12. **`rename_network_batch`** - Batch rename files using regex patterns

## Installation

### Using uvx (Recommended)

```bash
# Install and run directly from PyPI (once published)
uvx eh-smb-mcp

# Or install from local directory during development
uvx --from . eh-smb-mcp
```

### Using pip

```bash
pip install eh-smb-mcp
eh-smb-mcp
```

## Configuration

All configuration is done through environment variables using JSON list format. Each list index corresponds to a share.

### Quick Start

Create a `.env` file with minimal required configuration:

```bash
# Single share example
SMB_HOSTS='["192.168.1.100"]'
SMB_SHARE_NAMES='["shared_folder"]'
SMB_USERNAMES='["myuser"]'
SMB_PASSWORDS='["mypassword"]'
```

### Multiple Shares

```bash
# Multiple shares - each index corresponds to the same share
SMB_NAMES='["data", "backup"]'
SMB_HOSTS='["192.168.1.100", "192.168.1.101"]'
SMB_SHARE_NAMES='["shared_folder", "backup_drive"]'
SMB_USERNAMES='["user1", "user2"]'
SMB_PASSWORDS='["password1", "password2"]'
SMB_DOMAINS='["WORKGROUP", "DOMAIN"]'
```

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SMB_HOSTS` | SMB server hostnames/IPs | `["192.168.1.100"]` |
| `SMB_SHARE_NAMES` | Remote share names | `["shared"]` |
| `SMB_USERNAMES` | Authentication usernames | `["user"]` |
| `SMB_PASSWORDS` | Authentication passwords | `["pass"]` |

### Optional Environment Variables

#### Share Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SMB_NAMES` | Share identifiers | `["share_1", "share_2", ...]` |
| `SMB_DOMAINS` | NT domains | `["", ""]` |
| `SMB_PORTS` | SMB ports | `[445, 445]` |

#### Security Configuration

| Variable | Description | Default                         |
|----------|-------------|---------------------------------|
| `SMB_ALLOWED_EXTENSIONS` | Allowed file extensions | `[".txt", ".py", ".json", ...]` |
| `SMB_BLOCKED_EXTENSIONS` | Blocked file extensions | `[".exe", ".bat", ".cmd", ...]` |
| `SMB_MAX_FILE_SIZE` | Maximum file size | `10000MB`                       |
| `SMB_ALLOWED_PATHS` | Allowed paths (empty = all) | `[]`                            |
| `SMB_BLOCKED_PATHS` | Blocked paths | `["/etc", "/root", ...]`        |
| `SMB_ENABLE_WRITE` | Enable write operations | `true`                          |
| `SMB_ENABLE_DELETE` | Enable delete operations | `false`                         |

#### Server Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SMB_LOG_LEVEL` | Logging level | `INFO` |
| `SMB_MAX_CONNECTIONS` | Max concurrent connections | `10` |

See [`.env.example`](.env.example) for a complete configuration template.

## Usage with Claude Desktop

Add this server to your Claude Desktop configuration:

### macOS/Linux

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "smb": {
      "command": "uvx",
      "args": ["eh-smb-mcp"],
      "env": {
        "SMB_HOSTS": "[\"192.168.1.100\"]",
        "SMB_SHARE_NAMES": "[\"shared\"]",
        "SMB_USERNAMES": "[\"myuser\"]",
        "SMB_PASSWORDS": "[\"mypassword\"]",
        "SMB_ENABLE_DELETE": "false"
      }
    }
  }
}
```

### Windows

Edit `%APPDATA%\Claude\claude_desktop_config.json` with the same configuration.

## Security Considerations

⚠️ **Important Security Notes:**

1. **Password Storage**: Passwords are stored in environment variables or config files. Consider using:
   - Restricted file permissions
   - Environment variable management tools
   - Secrets management systems for production use

2. **Network Security**: 
   - Use this server only on trusted networks
   - Consider using VPN for remote access
   - Be aware of SMB security vulnerabilities

3. **Access Control**:
   - Start with write/delete disabled
   - Use extension filtering to block executable files
   - Set appropriate path restrictions
   - Configure file size limits

4. **Default Security Settings**:
   - System paths are blocked by default

## Development

### Running Locally

```bash
# Clone the repository
git clone https://github.com/yourusername/eh-smb-mcp
cd eh-smb-mcp

# Set environment variables
export SMB_HOSTS='["192.168.1.100"]'
export SMB_SHARE_NAMES='["shared"]'
export SMB_USERNAMES='["user"]'
export SMB_PASSWORDS='["password"]'

# Run with Python
python -m smb_mcp

# Or use uvx from local directory
uvx --from . eh-smb-mcp
```

### Project Structure

```
eh-smb-mcp/
├── smb_mcp/
│   ├── __init__.py          # Package initialization
│   ├── __main__.py          # Entry point for python -m
│   ├── cli.py               # Command-line interface
│   ├── config.py            # Configuration from env vars
│   ├── server.py            # MCP server implementation
│   ├── smb_fs.py            # SMB filesystem operations
│   ├── security.py          # Security validation
│   └── exceptions.py        # Custom exceptions
├── pyproject.toml           # Project metadata and dependencies
├── .env.example             # Example environment configuration
└── README.md                # This file
```

## Dependencies

- **mcp** (>=1.0.0) - Model Context Protocol implementation
- **pysmb** (>=1.2.9) - SMB/CIFS client library
- **pydantic** (>=2.0.0) - Data validation and settings management

## Troubleshooting

### Connection Issues

```
Error: Failed to connect to SMB server
```

**Solutions:**
- Verify the host is reachable: `ping <host>`
- Check SMB port is accessible: `telnet <host> 445`
- Verify credentials are correct
- Check Windows Firewall/network firewall rules

### Authentication Errors

```
Error: SMB authentication failed
```

**Solutions:**
- Verify username and password
- Check domain name (use `WORKGROUP` for workgroup environments)
- Ensure NTLMv2 authentication is enabled on the server

### Configuration Errors

```
Configuration error: SMB_HOSTS environment variable is required
```

**Solutions:**
- Ensure environment variables are set before running
- Use proper JSON format: `SMB_HOSTS='["192.168.1.100"]'`
- Check for typos in variable names
