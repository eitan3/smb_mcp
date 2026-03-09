"""Utility functions for file operations."""

import re
import os
import logging
import fnmatch
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


logger = logging.getLogger(__name__)


def has_glob_pattern(path: str) -> bool:
    """
    Check if path contains glob pattern characters.
    
    Args:
        path: Path to check
        
    Returns:
        True if path contains wildcards (* ? [ ])
    """
    return any(char in path for char in ['*', '?', '[', ']'])


def split_path_pattern(path: str) -> Tuple[str, Optional[str], bool]:
    """
    Split path into base directory, pattern, and recursion flag.
    
    Args:
        path: Path that may contain glob patterns
        
    Returns:
        (base_dir, pattern, is_recursive)
        
    Examples:
        "/folder/file.txt" -> ("/folder/file.txt", None, False)
        "/folder/*.txt" -> ("/folder", "*.txt", False)
        "/docs/**/*.py" -> ("/docs", "**/*.py", True)
        "/*.txt" -> ("/", "*.txt", False)
    """
    if not has_glob_pattern(path):
        # No pattern, return path as-is
        return (path, None, False)
    
    # Check for recursive pattern
    is_recursive = '**' in path
    
    # Normalize path separators
    path = path.replace('\\', '/')
    
    # Split path into parts
    parts = path.split('/')
    base_parts = []
    pattern_parts = []
    found_pattern = False
    
    for part in parts:
        if not found_pattern and not has_glob_pattern(part):
            base_parts.append(part)
        else:
            found_pattern = True
            pattern_parts.append(part)
    
    # Build base directory
    if not base_parts:
        base_dir = '/'
    else:
        base_dir = '/'.join(base_parts)
        if not base_dir:
            base_dir = '/'
    
    # Build pattern
    pattern = '/'.join(pattern_parts) if pattern_parts else None
    
    return (base_dir, pattern, is_recursive)


def match_glob_pattern(name: str, pattern: str) -> bool:
    """
    Match filename against glob pattern.
    
    Args:
        name: Filename to match
        pattern: Glob pattern (* ? [])
        
    Returns:
        True if matches
        
    Examples:
        match_glob_pattern("file.txt", "*.txt") -> True
        match_glob_pattern("test.py", "*.txt") -> False
        match_glob_pattern("file1.txt", "file?.txt") -> True
    """
    return fnmatch.fnmatch(name, pattern)


def match_pattern(name: str, pattern: Optional[str]) -> bool:
    """
    Check if name matches regex pattern (deprecated - use match_glob_pattern).
    
    Args:
        name: Filename or path to match
        pattern: Regex pattern (None or "*" matches all)
        
    Returns:
        True if matches, False otherwise
    """
    if not pattern or pattern == "*":
        return True
    
    try:
        return bool(re.search(pattern, name))
    except re.error as e:
        logger.warning(f"Invalid regex pattern '{pattern}': {e}")
        return False


def apply_rename_pattern(name: str, pattern: str, replacement: str) -> str:
    """
    Apply regex replacement to filename.
    
    Args:
        name: Original filename
        pattern: Regex pattern with capture groups
        replacement: Replacement string with backreferences
        
    Returns:
        New filename after replacement
        
    Example:
        apply_rename_pattern("file.txt", r"(.*)\.txt", r"\1.bak")
        => "file.bak"
    """
    try:
        return re.sub(pattern, replacement, name)
    except re.error as e:
        logger.error(f"Regex error applying pattern '{pattern}': {e}")
        return name


def ensure_local_directory(path: str) -> None:
    """
    Ensure local directory exists, create if needed.
    
    Args:
        path: Local directory path
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create directory {path}: {e}")
        raise


def format_byte_size(size_bytes: int) -> str:
    """
    Format byte size to human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def normalize_path(path: str) -> str:
    """
    Normalize path separators for consistency.
    
    Args:
        path: Path to normalize
        
    Returns:
        Normalized path with forward slashes
    """
    return path.replace('\\', '/')


def get_relative_path(base: str, full_path: str) -> str:
    """
    Get relative path from base to full_path.
    
    Args:
        base: Base directory path
        full_path: Full path
        
    Returns:
        Relative path
    """
    try:
        return os.path.relpath(full_path, base).replace('\\', '/')
    except ValueError:
        # Paths on different drives on Windows
        return full_path.replace('\\', '/')


def join_paths(*parts: str) -> str:
    """
    Join path parts with forward slashes.
    
    Args:
        *parts: Path components to join
        
    Returns:
        Joined path with forward slashes
    """
    return '/'.join(part.strip('/').strip('\\') for part in parts if part)


def create_operation_summary(
    files_count: int = 0,
    dirs_count: int = 0,
    bytes_transferred: int = 0,
    failed_count: int = 0,
    items: Optional[List[str]] = None,
    operation: str = "operation"
) -> Dict[str, Any]:
    """
    Create a standardized operation summary dict.
    
    Args:
        files_count: Number of files processed
        dirs_count: Number of directories processed
        bytes_transferred: Total bytes transferred
        failed_count: Number of failed items
        items: List of processed item paths
        operation: Operation name for summary
        
    Returns:
        Summary dictionary
    """
    summary = {
        "success": failed_count == 0,
        "files_processed": files_count,
        "directories_processed": dirs_count,
        "total_items": files_count + dirs_count,
        "bytes_transferred": bytes_transferred,
        "bytes_transferred_formatted": format_byte_size(bytes_transferred),
        "failed_count": failed_count,
        "operation": operation
    }
    
    if items is not None:
        summary["items"] = items
        
    return summary
