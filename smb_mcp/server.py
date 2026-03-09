"""Main MCP server implementation for network filesystem access."""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.models import InitializationOptions

from .config import NetworkMCPConfig, SMBShareConfig
from .smb_fs import AsyncSMBConnection, SMBFileInfo
from .security import SecurityValidator
from .exceptions import (
    NetworkMCPError,
    NetworkFileSystemError,
    AuthenticationError,
    FileNotFoundError,
    ValidationError,
    PermissionError,
    ConfigurationError,
    CopyError,
    MoveError,
    RenameError
)


logger = logging.getLogger(__name__)


class NetworkMCPServer:
    """Network MCP Server for accessing network filesystems."""
    
    def __init__(self, config: NetworkMCPConfig):
        self.config = config
        self.security = SecurityValidator(config.security)
        self.connections: Dict[str, AsyncSMBConnection] = {}
        
        self._setup_logging()
        
        logger.info("Initializing MCP Server")
        try:
            self.server = Server("network-mcp-server")
            logger.debug("MCP Server instance created successfully")
        except Exception as e:
            logger.error(f"Failed to create MCP Server instance: {e}", exc_info=True)
            raise
        
        self._register_tools()
        logger.info(f"MCP Server initialized successfully with {len(config.shares)} shares")
    
    def _setup_logging(self) -> None:
        """Configure logging (already configured in cli.py, but set level here)."""
        log_level = getattr(logging, self.config.logging_level.upper(), logging.INFO)
        logger.setLevel(log_level)
    
    def _register_tools(self) -> None:
        """Register MCP tools."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """List available tools."""
            return [
                types.Tool(
                    name="list_network_directory",
                    description="List contents of a network directory",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "path": {
                                "type": "string", 
                                "description": "Directory path to list (relative to share root)",
                                "default": ""
                            }
                        },
                        "required": ["share_name"]
                    }
                ),
                types.Tool(
                    name="read_network_file",
                    description="Read contents of a network file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "file_path": {
                                "type": "string",
                                "description": "File path to read (relative to share root)"
                            },
                            "encoding": {
                                "type": "string",
                                "description": "Text encoding for the file",
                                "default": "utf-8"
                            }
                        },
                        "required": ["share_name", "file_path"]
                    }
                ),
                types.Tool(
                    name="write_network_file",
                    description="Write contents to a network file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "file_path": {
                                "type": "string",
                                "description": "File path to write (relative to share root)"
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write to the file"
                            },
                            "encoding": {
                                "type": "string",
                                "description": "Text encoding for the file",
                                "default": "utf-8"
                            }
                        },
                        "required": ["share_name", "file_path", "content"]
                    }
                ),
                types.Tool(
                    name="delete_network_file",
                    description="Delete a network file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "file_path": {
                                "type": "string",
                                "description": "File path to delete (relative to share root)"
                            }
                        },
                        "required": ["share_name", "file_path"]
                    }
                ),
                types.Tool(
                    name="create_network_directory",
                    description="Create a directory on a network share",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "directory_path": {
                                "type": "string",
                                "description": "Directory path to create (relative to share root)"
                            }
                        },
                        "required": ["share_name", "directory_path"]
                    }
                ),
                types.Tool(
                    name="get_network_file_info",
                    description="Get information about a network file or directory",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "path": {
                                "type": "string",
                                "description": "File or directory path (relative to share root)"
                            }
                        },
                        "required": ["share_name", "path"]
                    }
                ),
                types.Tool(
                    name="get_share_info",
                    description="Get information about configured network shares",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of specific share (optional - if not provided, lists all shares)"
                            }
                        }
                    }
                ),
                # New file operation tools
                types.Tool(
                    name="copy_from_network",
                    description="""Copy files from a network share to a local directory.
Supports glob patterns in the source path for batch operations:
- Exact path: "/docs/report.pdf" - copies single file
- Wildcard: "/docs/*.pdf" - copies all PDFs in docs folder
- Recursive: "/projects/**/*.py" - copies all Python files recursively

Pattern Examples:
- "*.txt" - all .txt files
- "file?.doc" - file1.doc, file2.doc, etc.
- "[0-9]*.log" - files starting with digits
- "**/*.py" - recursive Python files""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "source_path": {
                                "type": "string",
                                "description": "Source path on network share. May include glob patterns like *.txt or **/*.py"
                            },
                            "local_dest": {
                                "type": "string",
                                "description": "Local destination directory path"
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Copy directories recursively (default: true)",
                                "default": True
                            },
                            "overwrite": {
                                "type": "boolean",
                                "description": "Overwrite existing files (default: false)",
                                "default": False
                            }
                        },
                        "required": ["share_name", "source_path", "local_dest"]
                    }
                ),
                types.Tool(
                    name="copy_to_network",
                    description="""Copy files from local filesystem to a network share.
Supports glob patterns in the source path for batch operations:
- Exact path: "C:/docs/report.pdf" - copies single file
- Wildcard: "C:/docs/*.pdf" - copies all PDFs
- Recursive: "C:/projects/**/*.py" - copies all Python files recursively

Pattern Examples:
- "*.txt" - all .txt files
- "file?.doc" - file1.doc, file2.doc, etc.
- "[0-9]*.log" - files starting with digits
- "**/*.py" - recursive Python files""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "local_src": {
                                "type": "string",
                                "description": "Local source path. May include glob patterns like *.txt or **/*.py"
                            },
                            "dest_path": {
                                "type": "string",
                                "description": "Destination path on network share"
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Copy directories recursively (default: true)",
                                "default": True
                            },
                            "overwrite": {
                                "type": "boolean",
                                "description": "Overwrite existing files (default: false)",
                                "default": False
                            }
                        },
                        "required": ["share_name", "local_src", "dest_path"]
                    }
                ),
                types.Tool(
                    name="move_in_network",
                    description="""Move files within a network share.
Supports glob patterns in the source path for batch moves:
- Exact path: "/docs/file.txt" - moves single file
- Wildcard: "/docs/*.txt" - moves all TXT files
- Pattern: "/temp/[0-9]*.log" - moves files starting with digits

Pattern Examples:
- "*.txt" - all .txt files in directory
- "file?.doc" - file1.doc, file2.doc, etc.
- "[a-z]*.log" - files starting with lowercase letters""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "source": {
                                "type": "string",
                                "description": "Source path on share. May include glob patterns."
                            },
                            "destination": {
                                "type": "string",
                                "description": "Destination path or directory on share"
                            },
                            "overwrite": {
                                "type": "boolean",
                                "description": "Overwrite existing files (default: false)",
                                "default": False
                            }
                        },
                        "required": ["share_name", "source", "destination"]
                    }
                ),
                types.Tool(
                    name="rename_network_item",
                    description="""Rename a file or directory on a network share.
For simple rename of a single item.

For batch renaming with regex patterns, use rename_network_batch instead.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "path": {
                                "type": "string",
                                "description": "Current path of the item to rename"
                            },
                            "new_name": {
                                "type": "string",
                                "description": "New name for the item (just the filename, not full path)"
                            }
                        },
                        "required": ["share_name", "path", "new_name"]
                    }
                ),
                types.Tool(
                    name="rename_network_batch",
                    description="""Batch rename files using regex pattern matching.
Uses regex (not glob) patterns for find/replace on filenames.

Examples:
- Pattern: "(.*)\.txt$", Replacement: "\\1.bak" - rename .txt to .bak
- Pattern: "^old_", Replacement: "new_" - replace prefix
- Pattern: "([0-9]+)_(.+)", Replacement: "\\2_\\1" - swap number and name""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "share_name": {
                                "type": "string",
                                "description": "Name of the configured network share"
                            },
                            "directory": {
                                "type": "string",
                                "description": "Directory containing items to rename"
                            },
                            "pattern": {
                                "type": "string",
                                "description": "Regex pattern to match filenames"
                            },
                            "replacement": {
                                "type": "string",
                                "description": "Replacement pattern with backreferences (\\1, \\2, etc.)"
                            }
                        },
                        "required": ["share_name", "directory", "pattern", "replacement"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            """Handle tool calls."""
            try:
                if name == "list_network_directory":
                    return await self._handle_list_directory(**arguments)
                elif name == "read_network_file":
                    return await self._handle_read_file(**arguments)
                elif name == "write_network_file":
                    return await self._handle_write_file(**arguments)
                elif name == "delete_network_file":
                    return await self._handle_delete_file(**arguments)
                elif name == "create_network_directory":
                    return await self._handle_create_directory(**arguments)
                elif name == "get_network_file_info":
                    return await self._handle_get_file_info(**arguments)
                elif name == "get_share_info":
                    return await self._handle_get_share_info(**arguments)
                # New file operation tools
                elif name == "copy_from_network":
                    return await self._handle_copy_from_network(**arguments)
                elif name == "copy_to_network":
                    return await self._handle_copy_to_network(**arguments)
                elif name == "move_in_network":
                    return await self._handle_move_in_network(**arguments)
                elif name == "rename_network_item":
                    return await self._handle_rename_network_item(**arguments)
                elif name == "rename_network_batch":
                    return await self._handle_rename_network_batch(**arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
            
            except NetworkMCPError as e:
                logger.error(f"Network MCP error in {name}: {e}")
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]
            except Exception as e:
                logger.error(f"Unexpected error in {name}: {e}", exc_info=True)
                return [types.TextContent(type="text", text=f"Unexpected error: {str(e)}")]
    
    async def _get_connection(self, share_name: str) -> AsyncSMBConnection:
        """Get or create connection for a share."""
        if share_name not in self.config.shares:
            raise ConfigurationError(f"Share '{share_name}' not configured")
        
        if share_name not in self.connections:
            share_config = self.config.shares[share_name]
            
            if isinstance(share_config, SMBShareConfig):
                connection = AsyncSMBConnection(share_config)
                await connection.connect()
                self.connections[share_name] = connection
            else:
                raise ConfigurationError(f"Unsupported share type for '{share_name}'")
        
        return self.connections[share_name]
    
    async def _handle_list_directory(self, share_name: str, path: str = "") -> List[types.TextContent]:
        """Handle directory listing."""
        connection = await self._get_connection(share_name)
        
        # Validate path
        self.security.validate_file_path(path)
        
        files = await connection.list_directory(path)
        
        # Format results
        result_lines = []
        result_lines.append(f"Contents of {share_name}:{path or '/'}")
        result_lines.append("-" * 50)
        
        directories = [f for f in files if f.is_directory]
        files_list = [f for f in files if not f.is_directory]
        
        # List directories first
        for directory in sorted(directories, key=lambda x: x.name.lower()):
            result_lines.append(f"📁 {directory.name}/")
        
        # Then list files
        for file in sorted(files_list, key=lambda x: x.name.lower()):
            size_str = self._format_file_size(file.size)
            result_lines.append(f"📄 {file.name} ({size_str})")
        
        if not files:
            result_lines.append("(empty directory)")
        
        return [types.TextContent(type="text", text="\n".join(result_lines))]
    
    async def _handle_read_file(self, share_name: str, file_path: str, encoding: str = "utf-8") -> List[types.TextContent]:
        """Handle file reading."""
        connection = await self._get_connection(share_name)
        
        # Validate operation
        self.security.validate_read_operation(file_path)
        
        content_bytes = await connection.read_file(file_path)
        
        # Validate file size
        self.security.validate_file_size(len(content_bytes))
        
        try:
            content_text = content_bytes.decode(encoding)
            return [types.TextContent(type="text", text=content_text)]
        except UnicodeDecodeError as e:
            raise ValidationError(f"Failed to decode file with {encoding} encoding: {e}")
    
    async def _handle_write_file(self, share_name: str, file_path: str, content: str, encoding: str = "utf-8") -> List[types.TextContent]:
        """Handle file writing."""
        connection = await self._get_connection(share_name)
        
        # Validate operation
        self.security.validate_write_operation(file_path)
        
        # Encode content
        try:
            content_bytes = content.encode(encoding)
        except UnicodeEncodeError as e:
            raise ValidationError(f"Failed to encode content with {encoding} encoding: {e}")
        
        # Validate file size
        self.security.validate_file_size(len(content_bytes))
        
        await connection.write_file(file_path, content_bytes)
        
        size_str = self._format_file_size(len(content_bytes))
        return [types.TextContent(type="text", text=f"Successfully wrote {size_str} to {share_name}:{file_path}")]
    
    async def _handle_delete_file(self, share_name: str, file_path: str) -> List[types.TextContent]:
        """Handle file deletion."""
        connection = await self._get_connection(share_name)
        
        # Validate operation
        self.security.validate_delete_operation(file_path)
        
        await connection.delete_file(file_path)
        
        return [types.TextContent(type="text", text=f"Successfully deleted {share_name}:{file_path}")]
    
    async def _handle_create_directory(self, share_name: str, directory_path: str) -> List[types.TextContent]:
        """Handle directory creation."""
        connection = await self._get_connection(share_name)
        
        # Validate operation
        self.security.validate_write_operation(directory_path)
        
        await connection.create_directory(directory_path)
        
        return [types.TextContent(type="text", text=f"Successfully created directory {share_name}:{directory_path}")]
    
    async def _handle_get_file_info(self, share_name: str, path: str) -> List[types.TextContent]:
        """Handle file info retrieval."""
        connection = await self._get_connection(share_name)
        
        # Validate path
        self.security.validate_file_path(path)
        
        file_info = await connection.get_file_info(path)
        
        info_lines = []
        info_lines.append(f"Information for {share_name}:{path}")
        info_lines.append("-" * 50)
        info_lines.append(f"Name: {file_info.name}")
        info_lines.append(f"Type: {'Directory' if file_info.is_directory else 'File'}")
        
        if not file_info.is_directory:
            size_str = self._format_file_size(file_info.size)
            info_lines.append(f"Size: {size_str}")
        
        if file_info.modified_time:
            import datetime
            modified_dt = datetime.datetime.fromtimestamp(file_info.modified_time)
            info_lines.append(f"Modified: {modified_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return [types.TextContent(type="text", text="\n".join(info_lines))]
    
    async def _handle_get_share_info(self, share_name: Optional[str] = None) -> List[types.TextContent]:
        """Handle share info retrieval."""
        if share_name:
            if share_name not in self.config.shares:
                raise ConfigurationError(f"Share '{share_name}' not configured")
            
            shares_to_show = {share_name: self.config.shares[share_name]}
        else:
            shares_to_show = self.config.shares
        
        info_lines = []
        info_lines.append("Network Share Information")
        info_lines.append("=" * 50)
        
        for name, config in shares_to_show.items():
            info_lines.append(f"\nShare: {name}")
            info_lines.append(f"Type: {config.type.upper()}")
            
            if isinstance(config, SMBShareConfig):
                info_lines.append(f"Host: {config.host}:{config.port}")
                info_lines.append(f"Share Name: {config.share_name}")
                info_lines.append(f"Domain: {config.domain or '(none)'}")
                info_lines.append(f"Username: {config.username}")
                info_lines.append(f"Connected: {'Yes' if name in self.connections else 'No'}")
        
        info_lines.append(f"\nSecurity Settings:")
        info_lines.append(self.security.get_validation_summary())
        
        return [types.TextContent(type="text", text="\n".join(info_lines))]
    
    async def _handle_copy_from_network(
        self,
        share_name: str,
        source_path: str,
        local_dest: str,
        recursive: bool = True,
        overwrite: bool = False
    ) -> List[types.TextContent]:
        """Handle copying files from network share to local filesystem."""
        connection = await self._get_connection(share_name)
        
        # Validate source path (without glob characters for security check)
        from .file_utils import split_path_pattern
        base_dir, pattern, _ = split_path_pattern(source_path)
        self.security.validate_read_operation(base_dir)
        
        # Perform the copy
        result = await connection.copy_from_share(
            source_path=source_path,
            local_dest=local_dest,
            recursive=recursive,
            overwrite=overwrite
        )
        
        # Format response
        lines = []
        lines.append(f"Copy from {share_name}:{source_path} to {local_dest}")
        lines.append("=" * 50)
        lines.append(f"Status: {'✅ Success' if result['success'] else '⚠️ Completed with errors'}")
        lines.append(f"Files copied: {result['files_processed']}")
        lines.append(f"Directories processed: {result['directories_processed']}")
        lines.append(f"Total transferred: {result['bytes_transferred_formatted']}")
        
        if result['failed_count'] > 0:
            lines.append(f"Failed: {result['failed_count']}")
        
        if result.get('items') and len(result['items']) <= 20:
            lines.append("\nCopied items:")
            for item in result['items']:
                lines.append(f"  • {item}")
        elif result.get('items'):
            lines.append(f"\n({len(result['items'])} items copied)")
        
        return [types.TextContent(type="text", text="\n".join(lines))]
    
    async def _handle_copy_to_network(
        self,
        share_name: str,
        local_src: str,
        dest_path: str,
        recursive: bool = True,
        overwrite: bool = False
    ) -> List[types.TextContent]:
        """Handle copying files from local filesystem to network share."""
        connection = await self._get_connection(share_name)
        
        # Validate destination path for write operation
        self.security.validate_write_operation(dest_path)
        
        # Perform the copy
        result = await connection.copy_to_share(
            local_src=local_src,
            dest_path=dest_path,
            recursive=recursive,
            overwrite=overwrite
        )
        
        # Format response
        lines = []
        lines.append(f"Copy from {local_src} to {share_name}:{dest_path}")
        lines.append("=" * 50)
        lines.append(f"Status: {'✅ Success' if result['success'] else '⚠️ Completed with errors'}")
        lines.append(f"Files copied: {result['files_processed']}")
        lines.append(f"Directories processed: {result['directories_processed']}")
        lines.append(f"Total transferred: {result['bytes_transferred_formatted']}")
        
        if result['failed_count'] > 0:
            lines.append(f"Failed: {result['failed_count']}")
        
        if result.get('items') and len(result['items']) <= 20:
            lines.append("\nCopied items:")
            for item in result['items']:
                lines.append(f"  • {item}")
        elif result.get('items'):
            lines.append(f"\n({len(result['items'])} items copied)")
        
        return [types.TextContent(type="text", text="\n".join(lines))]
    
    async def _handle_move_in_network(
        self,
        share_name: str,
        source: str,
        destination: str,
        overwrite: bool = False
    ) -> List[types.TextContent]:
        """Handle moving files within a network share."""
        connection = await self._get_connection(share_name)
        
        # Validate both source (read) and destination (write) operations
        from .file_utils import split_path_pattern
        base_dir, pattern, _ = split_path_pattern(source)
        self.security.validate_read_operation(base_dir)
        self.security.validate_write_operation(destination)
        self.security.validate_delete_operation(base_dir)  # Move requires delete on source
        
        # Perform the move
        result = await connection.move_item(
            source=source,
            destination=destination,
            overwrite=overwrite
        )
        
        # Format response based on result type
        lines = []
        if 'items_moved' in result:
            # Batch move result
            lines.append(f"Move files from {share_name}:{source} to {share_name}:{destination}")
            lines.append("=" * 50)
            lines.append(f"Status: {'✅ Success' if result['success'] else '⚠️ Completed with errors'}")
            lines.append(f"Items moved: {result['items_moved']}")
            lines.append(f"Total transferred: {self._format_file_size(result['bytes_transferred'])}")
            
            if result['failed_count'] > 0:
                lines.append(f"Failed: {result['failed_count']}")
            
            if result.get('moves') and len(result['moves']) <= 20:
                lines.append("\nMoved items:")
                for move in result['moves']:
                    lines.append(f"  • {move['from']} → {move['to']}")
        else:
            # Single file move result
            lines.append(f"Move {share_name}:{result['from']} to {share_name}:{result['to']}")
            lines.append("=" * 50)
            lines.append(f"Status: ✅ Success")
            lines.append(f"Bytes transferred: {self._format_file_size(result['bytes_transferred'])}")
        
        return [types.TextContent(type="text", text="\n".join(lines))]
    
    async def _handle_rename_network_item(
        self,
        share_name: str,
        path: str,
        new_name: str
    ) -> List[types.TextContent]:
        """Handle renaming a single file or directory."""
        connection = await self._get_connection(share_name)
        
        # Validate the path for read and write (rename requires both)
        self.security.validate_read_operation(path)
        parent_dir = os.path.dirname(path)
        self.security.validate_write_operation(os.path.join(parent_dir, new_name) if parent_dir else new_name)
        
        # Perform the rename
        result = await connection.rename_item(path=path, new_name=new_name)
        
        # Format response
        lines = []
        lines.append(f"Rename on {share_name}")
        lines.append("=" * 50)
        lines.append(f"Status: ✅ Success")
        lines.append(f"Old path: {result['old_path']}")
        lines.append(f"New path: {result['new_path']}")
        
        return [types.TextContent(type="text", text="\n".join(lines))]
    
    async def _handle_rename_network_batch(
        self,
        share_name: str,
        directory: str,
        pattern: str,
        replacement: str
    ) -> List[types.TextContent]:
        """Handle batch renaming files using regex pattern."""
        connection = await self._get_connection(share_name)
        
        # Validate directory for read and write
        self.security.validate_read_operation(directory)
        self.security.validate_write_operation(directory)
        
        # Perform the batch rename
        result = await connection.rename_items_batch(
            directory=directory,
            pattern=pattern,
            replacement=replacement
        )
        
        # Format response
        lines = []
        lines.append(f"Batch Rename in {share_name}:{directory}")
        lines.append("=" * 50)
        lines.append(f"Pattern: {pattern}")
        lines.append(f"Replacement: {replacement}")
        lines.append(f"Status: {'✅ Success' if result['success'] else '⚠️ Completed with errors'}")
        lines.append(f"Items renamed: {result['items_renamed']}")
        
        if result['failed_count'] > 0:
            lines.append(f"Failed: {result['failed_count']}")
        
        if result.get('renames') and len(result['renames']) <= 20:
            lines.append("\nRenamed items:")
            for rename in result['renames']:
                old_name = os.path.basename(rename['old'])
                new_name = os.path.basename(rename['new'])
                lines.append(f"  • {old_name} → {new_name}")
        elif result.get('renames'):
            lines.append(f"\n({len(result['renames'])} items renamed)")
        
        return [types.TextContent(type="text", text="\n".join(lines))]
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    async def cleanup(self) -> None:
        """Cleanup connections."""
        for connection in self.connections.values():
            await connection.disconnect()
        self.connections.clear()
    
    async def run(self, transport: str = "stdio") -> None:
        """Run the MCP server."""
        try:
            logger.info(f"Starting MCP server with transport: {transport}")
            
            if transport == "stdio":
                logger.debug("Creating stdio server context")
                async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                    logger.debug("stdio server context created successfully")
                    
                    # Create proper initialization options using MCP types
                    try:
                        initialization_options = InitializationOptions(
                            server_name="network-mcp-server",
                            server_version="0.1.0",
                            capabilities=types.ServerCapabilities(
                                tools=types.ToolsCapability(listChanged=True)
                            )
                        )
                        logger.debug("Initialization options created successfully")
                    except Exception as e:
                        logger.error(f"Failed to create initialization options: {e}", exc_info=True)
                        raise
                    
                    logger.info("MCP server ready, starting event loop...")
                    await self.server.run(read_stream, write_stream, initialization_options)
                    logger.info("MCP server event loop ended")
            else:
                raise ValueError(f"Unsupported transport: {transport}")
        
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
            raise
        finally:
            logger.debug("Cleaning up connections...")
            await self.cleanup()
            logger.info("Server shutdown complete")


def main() -> None:
    """Main entry point for the server."""
    from .cli import main as cli_main
    cli_main()