import os
import time
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class FileLock:
    """
    A simple file-based lock mechanism to handle concurrent file operations.
    This helps prevent 'WinError 32: The process cannot access the file because it is being used by another process'
    """
    def __init__(self, lock_file, timeout=30, retry_interval=0.1):
        self.lock_file = lock_file
        self.timeout = timeout
        self.retry_interval = retry_interval
        self.is_locked = False
    
    def acquire(self):
        """
        Acquire the lock by creating a lock file.
        Retries until timeout is reached.
        """
        start_time = time.time()
        while True:
            try:
                # Try to create the lock file exclusively
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                self.is_locked = True
                logger.debug(f"Lock acquired: {self.lock_file}")
                return True
            except FileExistsError:
                # Lock file already exists, wait and retry
                if time.time() - start_time > self.timeout:
                    logger.warning(f"Timeout acquiring lock: {self.lock_file}")
                    return False
                time.sleep(self.retry_interval)
            except Exception as e:
                logger.error(f"Error acquiring lock: {str(e)}")
                return False
    
    def release(self):
        """
        Release the lock by removing the lock file.
        """
        if self.is_locked:
            try:
                os.remove(self.lock_file)
                self.is_locked = False
                logger.debug(f"Lock released: {self.lock_file}")
                return True
            except Exception as e:
                logger.error(f"Error releasing lock: {str(e)}")
                return False
        return True
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

@contextmanager
def file_lock(file_path, timeout=30, retry_interval=0.1):
    """
    Context manager for file locking.
    Usage:
    with file_lock('path/to/file.txt'):
        # Perform file operations
    """
    lock_file = f"{file_path}.lock"
    lock = FileLock(lock_file, timeout, retry_interval)
    try:
        if lock.acquire():
            yield
        else:
            logger.warning(f"Could not acquire lock for {file_path}")
            yield
    finally:
        lock.release()

@contextmanager
def media_operation_lock(media_id, operation_type, timeout=30):
    """
    Context manager specifically for media operations.
    Usage:
    with media_operation_lock('media_123', 'download'):
        # Perform media operation
    """
    lock_dir = os.path.join(os.getcwd(), "locks")
    os.makedirs(lock_dir, exist_ok=True)
    
    lock_file = os.path.join(lock_dir, f"{media_id}_{operation_type}.lock")
    lock = FileLock(lock_file, timeout)
    
    try:
        if lock.acquire():
            yield
        else:
            logger.warning(f"Could not acquire lock for {media_id} {operation_type}")
            yield
    finally:
        lock.release()