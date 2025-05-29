"""
Storage handler for managing files in both local filesystem and AWS S3
Automatically switches based on STORAGE_MODE environment variable
"""

import os
import boto3
from pathlib import Path
from typing import Optional, List, BinaryIO
import logging

logger = logging.getLogger(__name__)

class StorageHandler:
    def __init__(self):
        self.storage_mode = os.getenv("STORAGE_MODE", "local").lower()
        self.s3_bucket = os.getenv("REPORTS_BUCKET")
        
        if self.storage_mode == "s3":
            if not self.s3_bucket:
                raise ValueError("REPORTS_BUCKET environment variable must be set when STORAGE_MODE=s3")
            
            self.s3_client = boto3.client('s3')
            logger.info(f"Initialized S3 storage handler with bucket: {self.s3_bucket}")
        else:
            logger.info("Initialized local filesystem storage handler")
    
    def save_file(self, content: bytes | str, relative_path: str) -> str:
        """
        Save a file to storage
        
        Args:
            content: File content (bytes or string)
            relative_path: Path relative to storage root (e.g., "output_files/report.xlsx")
            
        Returns:
            Full path or S3 URL of saved file
        """
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        if self.storage_mode == "s3":
            return self._save_to_s3(content, relative_path)
        else:
            return self._save_to_local(content, relative_path)
    
    def _save_to_local(self, content: bytes, relative_path: str) -> str:
        """Save file to local filesystem"""
        full_path = Path(relative_path)
        
        # Create directory if it doesn't exist
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        full_path.write_bytes(content)
        
        logger.info(f"Saved file locally: {full_path}")
        return str(full_path)
    
    def _save_to_s3(self, content: bytes, relative_path: str) -> str:
        """Save file to S3"""
        # Clean up path for S3 (no leading slashes)
        s3_key = relative_path.lstrip('/')
        
        self.s3_client.put_object(
            Bucket=self.s3_bucket,
            Key=s3_key,
            Body=content
        )
        
        s3_url = f"s3://{self.s3_bucket}/{s3_key}"
        logger.info(f"Saved file to S3: {s3_url}")
        return s3_url
    
    def read_file(self, relative_path: str) -> bytes:
        """
        Read a file from storage
        
        Args:
            relative_path: Path relative to storage root
            
        Returns:
            File content as bytes
        """
        if self.storage_mode == "s3":
            return self._read_from_s3(relative_path)
        else:
            return self._read_from_local(relative_path)
    
    def _read_from_local(self, relative_path: str) -> bytes:
        """Read file from local filesystem"""
        full_path = Path(relative_path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        
        return full_path.read_bytes()
    
    def _read_from_s3(self, relative_path: str) -> bytes:
        """Read file from S3"""
        s3_key = relative_path.lstrip('/')
        
        response = self.s3_client.get_object(
            Bucket=self.s3_bucket,
            Key=s3_key
        )
        
        return response['Body'].read()
    
    def list_files(self, prefix: str = "") -> List[str]:
        """
        List files in storage with optional prefix filter
        
        Args:
            prefix: Directory prefix to filter files
            
        Returns:
            List of file paths
        """
        if self.storage_mode == "s3":
            return self._list_s3_files(prefix)
        else:
            return self._list_local_files(prefix)
    
    def _list_local_files(self, prefix: str) -> List[str]:
        """List files from local filesystem"""
        base_path = Path(prefix) if prefix else Path(".")
        
        if not base_path.exists():
            return []
        
        files = []
        for path in base_path.rglob("*"):
            if path.is_file():
                files.append(str(path))
        
        return files
    
    def _list_s3_files(self, prefix: str) -> List[str]:
        """List files from S3"""
        prefix = prefix.lstrip('/')
        
        paginator = self.s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(
            Bucket=self.s3_bucket,
            Prefix=prefix
        )
        
        files = []
        for page in page_iterator:
            if 'Contents' in page:
                for obj in page['Contents']:
                    files.append(obj['Key'])
        
        return files
    
    def get_download_url(self, relative_path: str, expiration: int = 3600) -> str:
        """
        Get a download URL for a file
        
        Args:
            relative_path: Path relative to storage root
            expiration: URL expiration time in seconds (S3 only)
            
        Returns:
            Download URL
        """
        if self.storage_mode == "s3":
            s3_key = relative_path.lstrip('/')
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.s3_bucket, 'Key': s3_key},
                ExpiresIn=expiration
            )
            
            return url
        else:
            # For local storage, return a relative URL that the FastAPI app can serve
            return f"/download/{relative_path}"
    
    def delete_file(self, relative_path: str) -> bool:
        """
        Delete a file from storage
        
        Args:
            relative_path: Path relative to storage root
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.storage_mode == "s3":
                s3_key = relative_path.lstrip('/')
                self.s3_client.delete_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key
                )
                logger.info(f"Deleted file from S3: {s3_key}")
            else:
                full_path = Path(relative_path)
                if full_path.exists():
                    full_path.unlink()
                    logger.info(f"Deleted local file: {full_path}")
                else:
                    logger.warning(f"File not found for deletion: {full_path}")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Error deleting file {relative_path}: {e}")
            return False

# Global instance
storage = StorageHandler() 