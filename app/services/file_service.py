import os
import shutil
from pathlib import Path
from typing import Optional

from app.config import LOGO_STORAGE_PATH
from app.utils.logger import errorLog

class FileService:
    """
    Service for handling file operations, specifically for account logos.
    """

    def __init__(self, base_storage_path: str = LOGO_STORAGE_PATH):
        self.base_storage_path = Path(base_storage_path)
        # Ensure the base storage directory exists
        self.base_storage_path.mkdir(parents=True, exist_ok=True)

    def save_logo(self, filename: str, file_content: bytes, tenant_id: Optional[str] = None) -> Optional[str]:
        """
        Saves a logo file.

        Args:
            filename: The name of the file.
            file_content: The content of the file in bytes.
            tenant_id: Optional tenant ID to store the file in a tenant-specific subdirectory.

        Returns:
            The relative path to the saved file (e.g., "tenant_id/filename" or "filename")
            or None if saving failed.
        """
        try:
            if tenant_id:
                tenant_dir = self.base_storage_path / tenant_id
                tenant_dir.mkdir(parents=True, exist_ok=True)
                save_path = tenant_dir / filename
                relative_path = f"{tenant_id}/{filename}"
            else:
                save_path = self.base_storage_path / filename
                relative_path = filename

            with open(save_path, "wb") as f:
                f.write(file_content)

            return relative_path
        except IOError as e:
            errorLog(
                module_name="FileService",
                message=f"Error saving logo file '{filename}' for tenant '{tenant_id}'",
                details=e
            )
            return None
        except Exception as e:
            errorLog(
                module_name="FileService",
                message=f"An unexpected error occurred while saving logo file '{filename}' for tenant '{tenant_id}'",
                details=e
            )
            return None

    def delete_logo(self, relative_logo_path: str) -> bool:
        """
        Deletes a logo file.

        Args:
            relative_logo_path: The relative path to the logo file (e.g., "tenant_id/filename" or "filename").

        Returns:
            True if deletion was successful, False otherwise.
        """
        try:
            full_path = self.base_storage_path / relative_logo_path
            if not full_path.exists():
                errorLog(
                    module_name="FileService",
                    message=f"Logo file not found for deletion: '{relative_logo_path}' (Full path: {full_path})",
                )
                return False

            os.remove(full_path)
            return True
        except FileNotFoundError:
            errorLog(
                module_name="FileService",
                message=f"Logo file not found for deletion: '{relative_logo_path}'",
            )
            return False
        except IOError as e:
            errorLog(
                module_name="FileService",
                message=f"Error deleting logo file '{relative_logo_path}'",
                details=e
            )
            return False
        except Exception as e:
            errorLog(
                module_name="FileService",
                message=f"An unexpected error occurred while deleting logo file '{relative_logo_path}'",
                details=e
            )
            return False

    def get_logo_path(self, relative_logo_path: str) -> Optional[str]:
        """
        Gets the full absolute path to a logo file.

        Args:
            relative_logo_path: The relative path to the logo file (e.g., "tenant_id/filename" or "filename").

        Returns:
            The full absolute path to the logo file, or None if the file does not exist.
        """
        full_path = self.base_storage_path / relative_logo_path
        if full_path.exists() and full_path.is_file():
            return str(full_path.resolve())
        else:
            errorLog(
                module_name="FileService",
                message=f"Logo file not found at expected path: {full_path}. Relative path: {relative_logo_path}",
            )
            return None

# Example Usage (for testing purposes, can be removed)
if __name__ == "__main__":
    # Ensure app.utils.logger and app.config are accessible if running this directly
    # This might require adjusting PYTHONPATH or running from the project root.

    # Mock logger for standalone execution if needed
    class MockLogger:
        def errorLog(self, module_name, message, details=None):
            print(f"ERROR: [{module_name}] {message} - Details: {details}")

    # Check if the real logger is available, otherwise use mock
    try:
        from app.utils.logger import errorLog
    except ImportError:
        print("Warning: Real logger not found, using mock logger for example.")
        errorLog = MockLogger().errorLog

    # Use a temporary storage path for this example
    temp_logo_storage = Path("./temp_logo_storage_test")

    file_service = FileService(base_storage_path=str(temp_logo_storage))

    # Test save_logo
    print("\n--- Testing save_logo ---")
    test_content = b"This is a test logo content."
    saved_path1 = file_service.save_logo("test_logo.png", test_content)
    print(f"Saved logo (no tenant): {saved_path1}")

    saved_path2 = file_service.save_logo("tenant_logo.png", test_content, tenant_id="tenant123")
    print(f"Saved logo (with tenant): {saved_path2}")

    saved_path_fail = file_service.save_logo("///invalid///path.png", test_content) # Should fail
    print(f"Saved logo (invalid path): {saved_path_fail}")


    # Test get_logo_path
    print("\n--- Testing get_logo_path ---")
    if saved_path1:
        path1 = file_service.get_logo_path(saved_path1)
        print(f"Path for '{saved_path1}': {path1}, Exists: {Path(path1).exists() if path1 else False}")

    if saved_path2:
        path2 = file_service.get_logo_path(saved_path2)
        print(f"Path for '{saved_path2}': {path2}, Exists: {Path(path2).exists() if path2 else False}")

    non_existent_path = file_service.get_logo_path("non_existent_logo.png")
    print(f"Path for 'non_existent_logo.png': {non_existent_path}")

    # Test delete_logo
    print("\n--- Testing delete_logo ---")
    if saved_path1:
        deleted1 = file_service.delete_logo(saved_path1)
        print(f"Deleted '{saved_path1}': {deleted1}")
        print(f"Path for '{saved_path1}' after delete: {file_service.get_logo_path(saved_path1)}")

    if saved_path2:
        deleted2 = file_service.delete_logo(saved_path2)
        print(f"Deleted '{saved_path2}': {deleted2}")
        print(f"Path for '{saved_path2}' after delete: {file_service.get_logo_path(saved_path2)}")

    deleted_non_existent = file_service.delete_logo("non_existent_logo.png")
    print(f"Deleted 'non_existent_logo.png': {deleted_non_existent}")

    # Clean up the temporary directory
    if temp_logo_storage.exists():
        try:
            shutil.rmtree(temp_logo_storage)
            print(f"\nCleaned up temporary directory: {temp_logo_storage}")
        except Exception as e:
            print(f"Error cleaning up temp directory: {e}")
