"""Security validation and path checking."""

import os
import logging
from pathlib import Path
from typing import List, Optional

from .config import SecurityConfig, parse_file_size
from .exceptions import ValidationError, PermissionError


logger = logging.getLogger(__name__)


class SecurityValidator:
    """Validates file operations against security policies."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.max_file_size_bytes = parse_file_size(config.max_file_size)
    
    def validate_file_extension(self, file_path: str) -> None:
        """Validate file extension against allow/block lists."""
        file_ext = Path(file_path).suffix.lower()
        
        # Check blocked extensions first
        if file_ext in [ext.lower() for ext in self.config.blocked_extensions]:
            raise ValidationError(f"File extension '{file_ext}' is blocked")
        
        # Check allowed extensions if list is not empty
        if self.config.allowed_extensions:
            allowed_lower = [ext.lower() for ext in self.config.allowed_extensions]
            if file_ext not in allowed_lower:
                raise ValidationError(
                    f"File extension '{file_ext}' not in allowed list: {self.config.allowed_extensions}"
                )
    
    def validate_file_path(self, file_path: str) -> None:
        """Validate file path against allow/block lists."""
        # Normalize path
        normalized_path = os.path.normpath(file_path).replace('\\', '/')
        
        # Check blocked paths
        for blocked_path in self.config.blocked_paths:
            blocked_normalized = os.path.normpath(blocked_path).replace('\\', '/')
            if normalized_path.startswith(blocked_normalized):
                raise ValidationError(f"Path '{file_path}' is blocked (matches '{blocked_path}')")
        
        # Check allowed paths if list is not empty
        if self.config.allowed_paths:
            allowed = False
            for allowed_path in self.config.allowed_paths:
                allowed_normalized = os.path.normpath(allowed_path).replace('\\', '/')
                if normalized_path.startswith(allowed_normalized):
                    allowed = True
                    break
            
            if not allowed:
                raise ValidationError(
                    f"Path '{file_path}' not in allowed paths: {self.config.allowed_paths}"
                )
    
    def validate_file_size(self, file_size: int) -> None:
        """Validate file size against maximum limit."""
        if file_size > self.max_file_size_bytes:
            max_size_mb = self.max_file_size_bytes / (1024 * 1024)
            file_size_mb = file_size / (1024 * 1024)
            raise ValidationError(
                f"File size {file_size_mb:.2f}MB exceeds maximum {max_size_mb:.2f}MB"
            )
    
    def validate_write_operation(self, file_path: str) -> None:
        """Validate if write operations are allowed."""
        if not self.config.enable_write:
            raise PermissionError("Write operations are disabled")
        
        self.validate_file_path(file_path)
        self.validate_file_extension(file_path)
    
    def validate_delete_operation(self, file_path: str) -> None:
        """Validate if delete operations are allowed."""
        if not self.config.enable_delete:
            raise PermissionError("Delete operations are disabled")
        
        self.validate_file_path(file_path)
    
    def validate_read_operation(self, file_path: str) -> None:
        """Validate if read operations are allowed."""
        self.validate_file_path(file_path)
        self.validate_file_extension(file_path)
    
    def get_validation_summary(self) -> str:
        """Get a summary of current validation rules."""
        summary = []
        summary.append(f"Max file size: {self.config.max_file_size}")
        summary.append(f"Write enabled: {self.config.enable_write}")
        summary.append(f"Delete enabled: {self.config.enable_delete}")
        
        if self.config.allowed_extensions:
            summary.append(f"Allowed extensions: {', '.join(self.config.allowed_extensions)}")
        
        if self.config.blocked_extensions:
            summary.append(f"Blocked extensions: {', '.join(self.config.blocked_extensions)}")
        
        if self.config.allowed_paths:
            summary.append(f"Allowed paths: {', '.join(self.config.allowed_paths)}")
        
        if self.config.blocked_paths:
            summary.append(f"Blocked paths: {', '.join(self.config.blocked_paths)}")
        
        return "\n".join(summary)