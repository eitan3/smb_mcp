"""SMB/CIFS filesystem implementation with async wrapper."""

import io
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Using pysmb for SMB/CIFS support
from smb.SMBConnection import SMBConnection as PySMBConnection

from .config import SMBShareConfig
from .exceptions import NetworkFileSystemError, AuthenticationError, FileNotFoundError


logger = logging.getLogger(__name__)


class SMBFileInfo:
    """File information from SMB share."""
    
    def __init__(self, name: str, path: str, is_directory: bool, size: int, 
                 modified_time: Optional[float] = None):
        self.name = name
        self.path = path
        self.is_directory = is_directory
        self.size = size
        self.modified_time = modified_time


class SMBConnection:
    """Manages SMB/CIFS connections and operations using pysmb."""
    
    def __init__(self, config: SMBShareConfig):
        self.config = config
        self.connection: Optional[PySMBConnection] = None
        self._connected = False
    
    def connect(self) -> None:
        """Establish connection to SMB share."""
        try:
            # Create SMB connection
            self.connection = PySMBConnection(
                username=self.config.username,
                password=self.config.password,
                my_name="network-mcp-client",
                remote_name=self.config.host,
                domain=self.config.domain,
                use_ntlm_v2=self.config.use_ntlm_v2,
                is_direct_tcp=True  # Use direct TCP connection (port 445)
            )
            
            # Connect to server
            connected = self.connection.connect(
                self.config.host, 
                self.config.port,
                timeout=self.config.timeout
            )
            
            if not connected:
                raise NetworkFileSystemError("Failed to connect to SMB server")
            
            self._connected = True
            logger.info(f"Connected to SMB share {self.config.host}\\{self.config.share_name}")
            
        except Exception as e:
            logger.error(f"SMB connection failed: {e}")
            if "authentication" in str(e).lower() or "login" in str(e).lower():
                raise AuthenticationError(f"SMB authentication failed: {e}")
            raise NetworkFileSystemError(f"SMB connection failed: {e}")
    
    def disconnect(self) -> None:
        """Close SMB connection."""
        try:
            if self.connection and self._connected:
                self.connection.close()
            self._connected = False
            logger.info("Disconnected from SMB share")
        except Exception as e:
            logger.warning(f"Error during SMB disconnect: {e}")
    
    def _ensure_connected(self) -> None:
        """Ensure we have an active connection."""
        if not self._connected or not self.connection:
            raise NetworkFileSystemError("Not connected to SMB share")
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path for SMB operations."""
        # Convert backslashes to forward slashes for pysmb
        path = path.replace('\\', '/')
        
        # Remove leading slash if present
        if path.startswith('/'):
            path = path[1:]
        
        return path
    
    def list_directory(self, path: str = "") -> List[SMBFileInfo]:
        """List contents of a directory."""
        self._ensure_connected()
        
        try:
            normalized_path = self._normalize_path(path)
            
            # List directory contents
            file_list = self.connection.listPath(self.config.share_name, normalized_path or "/")
            
            result = []
            for file_info in file_list:
                if file_info.filename in ['.', '..']:
                    continue
                
                entry_path = os.path.join(path, file_info.filename).replace('\\', '/')
                is_directory = file_info.isDirectory
                
                smb_file_info = SMBFileInfo(
                    name=file_info.filename,
                    path=entry_path,
                    is_directory=is_directory,
                    size=file_info.file_size if not is_directory else 0,
                    modified_time=file_info.last_write_time if file_info.last_write_time else None
                )
                result.append(smb_file_info)
            
            return result
            
        except Exception as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise FileNotFoundError(f"Directory not found: {path}")
            logger.error(f"SMB directory listing failed for {path}: {e}")
            raise NetworkFileSystemError(f"Failed to list directory {path}: {e}")
    
    def read_file(self, path: str) -> bytes:
        """Read contents of a file."""
        self._ensure_connected()
        
        try:
            normalized_path = self._normalize_path(path)
            
            # Read file into BytesIO buffer
            file_buffer = io.BytesIO()
            self.connection.retrieveFile(self.config.share_name, normalized_path, file_buffer)
            
            content = file_buffer.getvalue()
            file_buffer.close()
            
            return content
            
        except Exception as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise FileNotFoundError(f"File not found: {path}")
            logger.error(f"SMB file read failed for {path}: {e}")
            raise NetworkFileSystemError(f"Failed to read file {path}: {e}")
    
    def write_file(self, path: str, content: Union[str, bytes]) -> None:
        """Write contents to a file."""
        self._ensure_connected()
        
        try:
            if isinstance(content, str):
                content = content.encode('utf-8')
            
            normalized_path = self._normalize_path(path)
            
            # Write file from BytesIO buffer
            file_buffer = io.BytesIO(content)
            self.connection.storeFile(self.config.share_name, normalized_path, file_buffer)
            file_buffer.close()
            
            logger.info(f"Successfully wrote {len(content)} bytes to {path}")
            
        except Exception as e:
            logger.error(f"SMB file write failed for {path}: {e}")
            raise NetworkFileSystemError(f"Failed to write file {path}: {e}")
    
    def delete_file(self, path: str) -> None:
        """Delete a file."""
        self._ensure_connected()
        
        try:
            normalized_path = self._normalize_path(path)
            self.connection.deleteFiles(self.config.share_name, normalized_path)
            logger.info(f"Successfully deleted file {path}")
            
        except Exception as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise FileNotFoundError(f"File not found: {path}")
            logger.error(f"SMB file deletion failed for {path}: {e}")
            raise NetworkFileSystemError(f"Failed to delete file {path}: {e}")
    
    def create_directory(self, path: str) -> None:
        """Create a directory."""
        self._ensure_connected()
        
        try:
            normalized_path = self._normalize_path(path)
            self.connection.createDirectory(self.config.share_name, normalized_path)
            logger.info(f"Successfully created directory {path}")
            
        except Exception as e:
            if "already exists" in str(e).lower() or "file exists" in str(e).lower():
                logger.info(f"Directory {path} already exists")
                return
            logger.error(f"SMB directory creation failed for {path}: {e}")
            raise NetworkFileSystemError(f"Failed to create directory {path}: {e}")
    
    def get_file_info(self, path: str) -> SMBFileInfo:
        """Get information about a file or directory."""
        self._ensure_connected()
        
        try:
            normalized_path = self._normalize_path(path)
            
            # Get file attributes
            attributes = self.connection.getAttributes(self.config.share_name, normalized_path)
            
            return SMBFileInfo(
                name=os.path.basename(path),
                path=path,
                is_directory=attributes.isDirectory,
                size=attributes.file_size if not attributes.isDirectory else 0,
                modified_time=attributes.last_write_time if attributes.last_write_time else None
            )
            
        except Exception as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise FileNotFoundError(f"File or directory not found: {path}")
            logger.error(f"SMB file info query failed for {path}: {e}")
            raise NetworkFileSystemError(f"Failed to get info for {path}: {e}")
    
    def copy_from_share(self, source_path: str, local_dest: str,
                        recursive: bool = True,
                        overwrite: bool = False) -> Dict[str, Any]:
        """
        Copy files/directories from SMB share to local filesystem.
        Supports glob patterns embedded in source_path.
        
        Args:
            source_path: Source path (may contain glob patterns: *.txt, **/*.py, etc.)
            local_dest: Local destination path
            recursive: Copy directories recursively (only for explicit directories)
            overwrite: Overwrite existing files
            
        Returns:
            Dictionary with copy operation summary
            
        Examples:
            copy_from_share("/docs/report.pdf", "/local/docs")  # Single file
            copy_from_share("/docs/*.pdf", "/local/docs")       # All PDFs in docs
            copy_from_share("/projects/**/*.py", "/local/code") # Recursive Python files
        """
        from .file_utils import (split_path_pattern, match_glob_pattern, ensure_local_directory,
                                  create_operation_summary, join_paths)
        from .exceptions import CopyError
        
        self._ensure_connected()
        
        files_copied = 0
        dirs_copied = 0
        bytes_transferred = 0
        failed = 0
        items = []
        
        try:
            # Parse source path for patterns
            base_dir, pattern, is_recursive_pattern = split_path_pattern(source_path)
            
            if pattern is None:
                # Exact path - no pattern matching
                file_info = self.get_file_info(source_path)
                
                if file_info.is_directory:
                    # Copy directory recursively
                    ensure_local_directory(local_dest)
                    dirs_copied += 1
                    
                    if recursive:
                        files = self.list_directory(source_path)
                        for f in files:
                            src = f.path
                            dest = os.path.join(local_dest, f.name)
                            
                            try:
                                if f.is_directory:
                                    result = self.copy_from_share(src, dest, recursive, overwrite)
                                    files_copied += result['files_processed']
                                    dirs_copied += result['directories_processed']
                                    bytes_transferred += result['bytes_transferred']
                                    items.extend(result.get('items', []))
                                else:
                                    # Copy file
                                    if not overwrite and os.path.exists(dest):
                                        logger.warning(f"Skipping existing file: {dest}")
                                        continue
                                    
                                    content = self.read_file(src)
                                    with open(dest, 'wb') as f_out:
                                        f_out.write(content)
                                    
                                    files_copied += 1
                                    bytes_transferred += len(content)
                                    items.append(dest)
                                    logger.info(f"Copied {src} to {dest}")
                            except Exception as e:
                                logger.error(f"Failed to copy {src}: {e}")
                                failed += 1
                else:
                    # Copy single file
                    # Ensure parent directory exists
                    parent_dir = os.path.dirname(local_dest)
                    if parent_dir:
                        ensure_local_directory(parent_dir)
                    
                    if not overwrite and os.path.exists(local_dest):
                        raise CopyError(f"Destination file already exists: {local_dest}")
                    
                    content = self.read_file(source_path)
                    with open(local_dest, 'wb') as f_out:
                        f_out.write(content)
                    
                    files_copied = 1
                    bytes_transferred = len(content)
                    items.append(local_dest)
                    logger.info(f"Copied {source_path} to {local_dest}")
            else:
                # Pattern-based copy
                ensure_local_directory(local_dest)
                
                # Handle simple patterns (non-recursive) vs recursive patterns (**)
                if not is_recursive_pattern:
                    # Simple pattern like "*.txt" - only match files in base_dir
                    files = self.list_directory(base_dir)
                    for f in files:
                        if not match_glob_pattern(f.name, pattern):
                            continue
                        
                        src = f.path
                        dest = os.path.join(local_dest, f.name)
                        
                        try:
                            if f.is_directory and recursive:
                                result = self.copy_from_share(src, dest, recursive, overwrite)
                                files_copied += result['files_processed']
                                dirs_copied += result['directories_processed']
                                bytes_transferred += result['bytes_transferred']
                                items.extend(result.get('items', []))
                            elif not f.is_directory:
                                if not overwrite and os.path.exists(dest):
                                    logger.warning(f"Skipping existing file: {dest}")
                                    continue
                                
                                content = self.read_file(src)
                                with open(dest, 'wb') as f_out:
                                    f_out.write(content)
                                
                                files_copied += 1
                                bytes_transferred += len(content)
                                items.append(dest)
                                logger.info(f"Copied {src} to {dest}")
                        except Exception as e:
                            logger.error(f"Failed to copy {src}: {e}")
                            failed += 1
                else:
                    # Recursive pattern like "**/*.py"
                    # Need to walk the directory tree
                    def walk_and_copy(current_dir: str, local_base: str, pattern_to_match: str):
                        nonlocal files_copied, dirs_copied, bytes_transferred, failed, items
                        
                        try:
                            files = self.list_directory(current_dir)
                            for f in files:
                                src = f.path
                                
                                if f.is_directory:
                                    # Recurse into subdirectory
                                    new_local_base = os.path.join(local_base, f.name)
                                    walk_and_copy(src, new_local_base, pattern_to_match)
                                else:
                                    # Check if file matches pattern (just filename part)
                                    if match_glob_pattern(f.name, pattern_to_match.split('/')[-1]):
                                        ensure_local_directory(local_base)
                                        dest = os.path.join(local_base, f.name)
                                        
                                        try:
                                            if not overwrite and os.path.exists(dest):
                                                logger.warning(f"Skipping existing file: {dest}")
                                                continue
                                            
                                            content = self.read_file(src)
                                            with open(dest, 'wb') as f_out:
                                                f_out.write(content)
                                            
                                            files_copied += 1
                                            bytes_transferred += len(content)
                                            items.append(dest)
                                            logger.info(f"Copied {src} to {dest}")
                                        except Exception as e:
                                            logger.error(f"Failed to copy {src}: {e}")
                                            failed += 1
                        except Exception as e:
                            logger.error(f"Failed to list directory {current_dir}: {e}")
                    
                    walk_and_copy(base_dir, local_dest, pattern)
                
        except CopyError:
            raise
        except Exception as e:
            logger.error(f"Copy from share failed: {e}")
            raise CopyError(f"Failed to copy from {source_path}: {e}")
        
        return create_operation_summary(
            files_count=files_copied,
            dirs_count=dirs_copied,
            bytes_transferred=bytes_transferred,
            failed_count=failed,
            items=items,
            operation="copy_from_network"
        )
    
    def copy_to_share(self, local_src: str, dest_path: str,
                      pattern: Optional[str] = None, recursive: bool = True,
                      overwrite: bool = False) -> Dict[str, Any]:
        """
        Copy files/directories from local filesystem to SMB share.
        
        Args:
            local_src: Local source path
            dest_path: Destination path on SMB share
            pattern: Regex pattern for filtering files (optional)
            recursive: Copy directories recursively
            overwrite: Overwrite existing files
            
        Returns:
            Dictionary with copy operation summary
        """
        from .file_utils import match_pattern, create_operation_summary, join_paths
        from .exceptions import CopyError
        
        self._ensure_connected()
        
        files_copied = 0
        dirs_copied = 0
        bytes_transferred = 0
        failed = 0
        items = []
        
        try:
            if not os.path.exists(local_src):
                raise CopyError(f"Local source does not exist: {local_src}")
            
            if os.path.isdir(local_src):
                # Copy directory recursively
                try:
                    self.create_directory(dest_path)
                    dirs_copied += 1
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        raise
                
                if recursive:
                    for entry in os.listdir(local_src):
                        if not match_pattern(entry, pattern):
                            continue
                        
                        src = os.path.join(local_src, entry)
                        dest = join_paths(dest_path, entry)
                        
                        try:
                            if os.path.isdir(src):
                                result = self.copy_to_share(src, dest, pattern, recursive, overwrite)
                                files_copied += result['files_processed']
                                dirs_copied += result['directories_processed']
                                bytes_transferred += result['bytes_transferred']
                                items.extend(result.get('items', []))
                            else:
                                # Copy file
                                if not overwrite:
                                    try:
                                        self.get_file_info(dest)
                                        logger.warning(f"Skipping existing file: {dest}")
                                        continue
                                    except FileNotFoundError:
                                        pass
                                
                                with open(src, 'rb') as f:
                                    content = f.read()
                                
                                self.write_file(dest, content)
                                files_copied += 1
                                bytes_transferred += len(content)
                                items.append(dest)
                                logger.info(f"Copied {src} to {dest}")
                        except Exception as e:
                            logger.error(f"Failed to copy {src}: {e}")
                            failed += 1
            else:
                # Copy single file
                if not match_pattern(os.path.basename(local_src), pattern):
                    raise CopyError(f"File does not match pattern: {local_src}")
                
                if not overwrite:
                    try:
                        self.get_file_info(dest_path)
                        raise CopyError(f"Destination file already exists: {dest_path}")
                    except FileNotFoundError:
                        pass
                
                with open(local_src, 'rb') as f:
                    content = f.read()
                
                self.write_file(dest_path, content)
                files_copied = 1
                bytes_transferred = len(content)
                items.append(dest_path)
                logger.info(f"Copied {local_src} to {dest_path}")
                
        except CopyError:
            raise
        except Exception as e:
            logger.error(f"Copy to share failed: {e}")
            raise CopyError(f"Failed to copy to {dest_path}: {e}")
        
        return create_operation_summary(
            files_count=files_copied,
            dirs_count=dirs_copied,
            bytes_transferred=bytes_transferred,
            failed_count=failed,
            items=items,
            operation="copy_to_network"
        )
    
    def rename_item(self, path: str, new_name: str) -> Dict[str, Any]:
        """
        Rename a single file or directory on the SMB share.
        
        Args:
            path: Current path of item
            new_name: New name for the item
            
        Returns:
            Dictionary with rename operation summary
        """
        from .file_utils import join_paths, create_operation_summary
        from .exceptions import RenameError
        
        self._ensure_connected()
        
        try:
            # Get file info to verify it exists
            file_info = self.get_file_info(path)
            
            # Build new path
            parent = os.path.dirname(path)
            new_path = join_paths(parent, new_name) if parent else new_name
            
            # Check if destination exists
            try:
                self.get_file_info(new_path)
                raise RenameError(f"Destination already exists: {new_path}")
            except FileNotFoundError:
                pass
            
            # Perform rename by copying and deleting
            # Note: pysmb doesn't have a direct rename operation
            if file_info.is_directory:
                raise RenameError("Directory rename not yet implemented. Use move operation instead.")
            
            # Read content
            content = self.read_file(path)
            
            # Write to new location
            self.write_file(new_path, content)
            
            # Delete old file
            self.delete_file(path)
            
            logger.info(f"Renamed {path} to {new_path}")
            
            return {
                "success": True,
                "old_path": path,
                "new_path": new_path,
                "operation": "rename"
            }
            
        except RenameError:
            raise
        except Exception as e:
            logger.error(f"Rename failed: {e}")
            raise RenameError(f"Failed to rename {path}: {e}")
    
    def rename_items_batch(self, directory: str, pattern: str, 
                           replacement: str) -> Dict[str, Any]:
        """
        Batch rename files/directories using regex pattern.
        
        Args:
            directory: Directory containing items to rename
            pattern: Regex pattern to match filenames
            replacement: Replacement pattern with backreferences
            
        Returns:
            Dictionary with rename operation summary
        """
        from .file_utils import apply_rename_pattern, join_paths
        from .exceptions import RenameError, PatternError
        
        self._ensure_connected()
        
        renamed_count = 0
        failed_count = 0
        renames = []
        
        try:
            # Validate pattern
            import re
            try:
                re.compile(pattern)
            except re.error as e:
                raise PatternError(f"Invalid regex pattern: {e}")
            
            # List directory
            files = self.list_directory(directory)
            
            for file_info in files:
                try:
                    new_name = apply_rename_pattern(file_info.name, pattern, replacement)
                    
                    # Skip if name unchanged
                    if new_name == file_info.name:
                        continue
                    
                    old_path = file_info.path
                    new_path = join_paths(directory, new_name)
                    
                    # Perform rename
                    result = self.rename_item(old_path, new_name)
                    
                    renamed_count += 1
                    renames.append({"old": old_path, "new": new_path})
                    
                except Exception as e:
                    logger.error(f"Failed to rename {file_info.name}: {e}")
                    failed_count += 1
            
            return {
                "success": failed_count == 0,
                "items_renamed": renamed_count,
                "failed_count": failed_count,
                "renames": renames,
                "operation": "batch_rename"
            }
            
        except (RenameError, PatternError):
            raise
        except Exception as e:
            logger.error(f"Batch rename failed: {e}")
            raise RenameError(f"Failed to batch rename in {directory}: {e}")
    
    def move_item(self, source: str, destination: str,
                  overwrite: bool = False) -> Dict[str, Any]:
        """
        Move a single file or directory within the SMB share.
        Supports patterns in source path for batch moves.
        
        Args:
            source: Source path (may contain glob patterns)
            destination: Destination path or directory
            overwrite: Overwrite existing items
            
        Returns:
            Dictionary with move operation summary
            
        Examples:
            move_item("/docs/file.txt", "/archive/file.txt")  # Single file
            move_item("/docs/*.txt", "/archive")              # All TXT files
        """
        from .file_utils import split_path_pattern, match_glob_pattern, join_paths
        from .exceptions import MoveError
        
        self._ensure_connected()
        
        # Parse source for patterns
        base_dir, pattern, is_recursive = split_path_pattern(source)
        
        if pattern is None:
            # Single exact file/directory move
            try:
                # Get source file info
                file_info = self.get_file_info(source)
                
                # Check if destination exists
                if not overwrite:
                    try:
                        self.get_file_info(destination)
                        raise MoveError(f"Destination already exists: {destination}")
                    except FileNotFoundError:
                        pass
                
                if file_info.is_directory:
                    raise MoveError("Directory move not yet implemented. Use copy + delete instead.")
                
                # Read content
                content = self.read_file(source)
                
                # Write to destination
                self.write_file(destination, content)
                
                # Delete source
                self.delete_file(source)
                
                logger.info(f"Moved {source} to {destination}")
                
                return {
                    "success": True,
                    "from": source,
                    "to": destination,
                    "bytes_transferred": len(content),
                    "operation": "move"
                }
                
            except MoveError:
                raise
            except Exception as e:
                logger.error(f"Move failed: {e}")
                raise MoveError(f"Failed to move {source}: {e}")
        else:
            # Pattern-based move - use batch move
            return self.move_items_batch(base_dir, destination, pattern, overwrite)
    
    def move_items_batch(self, source_dir: str, dest_dir: str,
                         pattern: Optional[str] = None, overwrite: bool = False) -> Dict[str, Any]:
        """
        Batch move files/directories matching glob pattern.
        
        Args:
            source_dir: Source directory
            dest_dir: Destination directory
            pattern: Glob pattern for filtering files (e.g., "*.txt", "file?.doc")
                     If None or "*", moves all items
            overwrite: Overwrite existing items
            
        Returns:
            Dictionary with move operation summary
            
        Examples:
            move_items_batch("/docs", "/archive", "*.pdf")      # Move all PDFs
            move_items_batch("/temp", "/backup", None)          # Move all items
        """
        from .file_utils import match_glob_pattern, join_paths
        from .exceptions import MoveError
        
        self._ensure_connected()
        
        moved_count = 0
        failed_count = 0
        bytes_transferred = 0
        moves = []
        
        try:
            # Ensure destination directory exists
            try:
                self.create_directory(dest_dir)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    raise
            
            # List source directory
            files = self.list_directory(source_dir)
            
            for file_info in files:
                # Apply glob pattern matching if pattern is provided
                if pattern and pattern != "*":
                    if not match_glob_pattern(file_info.name, pattern):
                        continue
                
                try:
                    src = file_info.path
                    dest = join_paths(dest_dir, file_info.name)
                    
                    # Perform move (pass exact paths without pattern to avoid recursion)
                    # We need to call the underlying move logic directly
                    if file_info.is_directory:
                        logger.warning(f"Skipping directory: {file_info.name}")
                        continue
                    
                    # Check if destination exists
                    if not overwrite:
                        try:
                            self.get_file_info(dest)
                            logger.warning(f"Skipping existing file: {dest}")
                            continue
                        except FileNotFoundError:
                            pass
                    
                    # Read content
                    content = self.read_file(src)
                    
                    # Write to destination
                    self.write_file(dest, content)
                    
                    # Delete source
                    self.delete_file(src)
                    
                    moved_count += 1
                    bytes_transferred += len(content)
                    moves.append({"from": src, "to": dest})
                    logger.info(f"Moved {src} to {dest}")
                    
                except Exception as e:
                    logger.error(f"Failed to move {file_info.name}: {e}")
                    failed_count += 1
            
            return {
                "success": failed_count == 0,
                "items_moved": moved_count,
                "failed_count": failed_count,
                "bytes_transferred": bytes_transferred,
                "moves": moves,
                "operation": "batch_move"
            }
            
        except MoveError:
            raise
        except Exception as e:
            logger.error(f"Batch move failed: {e}")
            raise MoveError(f"Failed to batch move from {source_dir}: {e}")


# Async wrapper for SMB operations
class AsyncSMBConnection:
    """Async wrapper for SMB connection operations."""
    
    def __init__(self, config: SMBShareConfig):
        self.smb_connection = SMBConnection(config)
    
    async def connect(self) -> None:
        """Connect to SMB share asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.smb_connection.connect)
    
    async def disconnect(self) -> None:
        """Disconnect from SMB share asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.smb_connection.disconnect)
    
    async def list_directory(self, path: str = "") -> List[SMBFileInfo]:
        """List directory contents asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.smb_connection.list_directory, path)
    
    async def read_file(self, path: str) -> bytes:
        """Read file contents asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.smb_connection.read_file, path)
    
    async def write_file(self, path: str, content: Union[str, bytes]) -> None:
        """Write file contents asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.smb_connection.write_file, path, content)
    
    async def delete_file(self, path: str) -> None:
        """Delete file asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.smb_connection.delete_file, path)
    
    async def create_directory(self, path: str) -> None:
        """Create directory asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.smb_connection.create_directory, path)
    
    async def get_file_info(self, path: str) -> SMBFileInfo:
        """Get file info asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.smb_connection.get_file_info, path)
    
    async def copy_from_share(self, source_path: str, local_dest: str,
                               recursive: bool = True,
                               overwrite: bool = False) -> Dict[str, Any]:
        """Copy from share asynchronously. Supports glob patterns in source_path."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.smb_connection.copy_from_share,
            source_path, local_dest, recursive, overwrite
        )
    
    async def copy_to_share(self, local_src: str, dest_path: str,
                             recursive: bool = True,
                             overwrite: bool = False) -> Dict[str, Any]:
        """Copy to share asynchronously. Supports glob patterns in local_src."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.smb_connection.copy_to_share,
            local_src, dest_path, recursive, overwrite
        )
    
    async def rename_item(self, path: str, new_name: str) -> Dict[str, Any]:
        """Rename item asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.smb_connection.rename_item, path, new_name)
    
    async def rename_items_batch(self, directory: str, pattern: str,
                                  replacement: str) -> Dict[str, Any]:
        """Batch rename items asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.smb_connection.rename_items_batch,
            directory, pattern, replacement
        )
    
    async def move_item(self, source: str, destination: str,
                         overwrite: bool = False) -> Dict[str, Any]:
        """Move item asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.smb_connection.move_item,
            source, destination, overwrite
        )
    
    async def move_items_batch(self, source_dir: str, dest_dir: str,
                                pattern: Optional[str] = None, overwrite: bool = False) -> Dict[str, Any]:
        """Batch move items asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.smb_connection.move_items_batch,
            source_dir, dest_dir, pattern, overwrite
        )