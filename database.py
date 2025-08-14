import os
import json
import time
from datetime import datetime, timedelta
import random
import string
import secrets
import logging
import shutil
import uuid

logger = logging.getLogger(__name__)

import os

# Directory to save media files
MEDIA_DIR = os.path.join(os.getcwd(), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

# Directory for data storage
DATA_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DATA_DIR, exist_ok=True)

class Database:
    def __init__(self, db_dir=DATA_DIR):
        self.db_dir = db_dir
        os.makedirs(db_dir, exist_ok=True)
        
        # Database files
        self.users_file = os.path.join(db_dir, "users.json")
        self.keys_file = os.path.join(db_dir, "keys.json")
        self.media_file = os.path.join(db_dir, "media.json")
        self.messages_file = os.path.join(db_dir, "messages.json")
        self.stats_file = os.path.join(db_dir, "stats.json")
        
        # Initialize database files if they don't exist
        self._init_db()
        
        # Load data
        self.users = self._load_json(self.users_file)
        self.keys = self._load_json(self.keys_file)
        self.media = self._load_json(self.media_file)
        self.messages = self._load_json(self.messages_file)
        self.stats = self._load_json(self.stats_file)
        
        # Initialize stats if empty
        if not self.stats:
            self.stats = {
                "start_time": time.time(),
                "total_media_count": 0,
                "community_link": "https://t.me/SIN_CITY_C_BOT",
                "total_users": 0,
                "premium_users": 0,
                "active_users": 0,
                "banned_users": 0,
                "keys_generated": 0
            }
            self._save_json(self.stats_file, self.stats)
    
    def _init_db(self):
        """Initialize database files if they don't exist"""
        for file_path in [self.users_file, self.keys_file, self.media_file, self.messages_file, self.stats_file]:
            if not os.path.exists(file_path):
                with open(file_path, 'w') as f:
                    f.write('{}')
    
    def _load_json(self, file_path):
        """Load JSON data from file with file locking to prevent concurrent access issues"""
        from file_lock import file_lock
        
        try:
            # Use file lock to prevent concurrent access issues
            with file_lock(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {file_path}. Creating empty data.")
            return {}
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}. Creating empty data.")
            return {}
        except Exception as e:
            logger.error(f"Error loading JSON from {file_path}: {str(e)}. Creating empty data.")
            return {}
    
    def _save_json(self, file_path, data):
        """Save JSON data to file with file locking to prevent concurrent access issues"""
        from file_lock import file_lock
        
        # Use file lock to prevent concurrent access issues
        with file_lock(file_path):
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    # User management
    def add_user(self, user_id, username, first_name, access_key):
        """Add a new user to the database"""
        user_id = str(user_id)  # Convert to string for JSON compatibility
        
        # Check if user already exists
        if user_id in self.users:
            return False
        
        # Generate a random alias
        alias = self._generate_alias()
        
        # Get key type
        key_type = self.get_key_type(access_key) if access_key else "normal"
        
        # Create user entry
        self.users[user_id] = {
            "username": username,
            "first_name": first_name,
            "alias": alias,
            "join_date": time.time(),
            "access_key": access_key,
            "premium": key_type == "premium",
            "active": key_type == "premium",  # Premium users are always active
            "uploads": 0,
            "last_activity": time.time(),
            "activity_timer": time.time() + 86400,  # 24 hours from now
            "banned": False,
            "admin": False,
            "ghosted": False,
            "media_ids": [],
            "synced_media": [],
            "last_pin_view": 0  # Timestamp when user last saw pinned message
        }
        
        # Update key usage
        if access_key and access_key in self.keys:
            if "users" not in self.keys[access_key]:
                self.keys[access_key]["users"] = []
            self.keys[access_key]["users"].append(user_id)
            self.keys[access_key]["uses"] += 1
            self._save_json(self.keys_file, self.keys)
        
        # Update stats
        self.stats["total_users"] += 1
        if key_type == "premium":
            self.stats["premium_users"] += 1
            self.stats["active_users"] += 1
        self._save_json(self.stats_file, self.stats)
        
        # Save user data
        self._save_json(self.users_file, self.users)
        return True
    
    def user_exists(self, user_id):
        """Check if a user exists in the database"""
        return str(user_id) in self.users
    
    def get_user(self, user_id):
        """Get user data"""
        user_id = str(user_id)
        return self.users.get(user_id, None)
    
    def update_user(self, user_id, data):
        """Update user data"""
        user_id = str(user_id)
        if user_id in self.users:
            self.users[user_id].update(data)
            self._save_json(self.users_file, self.users)
            return True
            
    def delete_user(self, user_id):
        """Delete a user from the database"""
        user_id = str(user_id)
        if user_id in self.users:
            # Get user data before deletion for stats update
            user = self.users[user_id]
            
            # Remove user from database
            del self.users[user_id]
            
            # Update stats
            self.stats["total_users"] -= 1
            if user.get("premium", False):
                self.stats["premium_users"] -= 1
            if user.get("active", False):
                self.stats["active_users"] -= 1
            
            # Save changes
            self._save_json(self.users_file, self.users)
            self._save_json(self.stats_file, self.stats)
            return True
        return False
        return False
    
    def ban_user(self, user_id):
        """Ban a user"""
        user_id = str(user_id)
        if user_id in self.users and not self.users[user_id]["banned"]:
            self.users[user_id]["banned"] = True
            self.stats["banned_users"] += 1
            if self.users[user_id]["active"]:
                self.stats["active_users"] -= 1
                self.users[user_id]["active"] = False
            self._save_json(self.users_file, self.users)
            self._save_json(self.stats_file, self.stats)
            return True
        return False
    
    def unban_user(self, user_id):
        """Unban a user"""
        user_id = str(user_id)
        if user_id in self.users and self.users[user_id]["banned"]:
            self.users[user_id]["banned"] = False
            self.stats["banned_users"] -= 1
            self._save_json(self.users_file, self.users)
            self._save_json(self.stats_file, self.stats)
            return True
        return False
    
    def upgrade_user(self, user_id):
        """Upgrade a user to premium"""
        user_id = str(user_id)
        if user_id in self.users and not self.users[user_id]["premium"]:
            self.users[user_id]["premium"] = True
            self.users[user_id]["active"] = True  # Premium users are always active
            self.stats["premium_users"] += 1
            if not self.users[user_id]["active"]:
                self.stats["active_users"] += 1
            self._save_json(self.users_file, self.users)
            self._save_json(self.stats_file, self.stats)
            return True
        return False
    
    def add_media(self, user_id, file_id, file_path, file_size, media_type, caption=None, file_unique_id=None):
        """Add a media file to the database"""
        user_id = str(user_id)
        
        # Check if user exists and is not banned
        if user_id not in self.users or self.users[user_id]["banned"]:
            return None
        
        # Check if this file_id already exists for this user
        for media_id, media_data in self.media.items():
            if media_data["file_id"] == file_id and media_data["user_id"] == user_id:
                return media_id
                
        # Create duplicates directory if it doesn't exist
        duplicates_dir = os.path.join(MEDIA_DIR, "duplicates")
        os.makedirs(duplicates_dir, exist_ok=True)
        
        # Check if this file_unique_id already exists in the database (from any user)
        is_duplicate = False
        if file_unique_id:
            for media_id, media_data in self.media.items():
                if media_data.get("file_unique_id") == file_unique_id:
                    is_duplicate = True
                    break
                
        # Check if this is a duplicate media from another user
        duplicate_media_id = self.check_duplicate_media(file_id, user_id, file_unique_id)
        if duplicate_media_id:
            # Mark the media as a duplicate and record when it was detected
            self.media[duplicate_media_id]["has_duplicates"] = True
            
            # If this media doesn't have a duplicates list, create one
            if "duplicates" not in self.media[duplicate_media_id]:
                self.media[duplicate_media_id]["duplicates"] = []
                
            # Add this duplicate entry with timestamp for auto-deletion after 24 hours
            duplicate_entry = {
                "user_id": user_id,
                "detected_time": time.time(),
                "file_id": file_id
            }
            self.media[duplicate_media_id]["duplicates"].append(duplicate_entry)
            
            # Move the file to duplicates folder
            original_filename = os.path.basename(file_path)
            duplicate_file_path = os.path.join(duplicates_dir, f"{media_id}_{original_filename}")
            try:
                import shutil
                shutil.copy2(file_path, duplicate_file_path)
                # Update file path to point to duplicate location
                file_path = duplicate_file_path
            except Exception as e:
                logger.error(f"Error copying duplicate file: {str(e)}")
        
        # Generate a unique media ID
        media_id = f"media_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Add media to database
        self.media[media_id] = {
            "user_id": user_id,
            "file_id": file_id,
            "file_unique_id": file_unique_id,
            "file_path": file_path,
            "file_size": file_size,
            "media_type": media_type,
            "caption": caption,
            "upload_time": time.time(),
            "alias": self.users[user_id]["alias"],
            "premium": self.users[user_id]["premium"],
            "reported": False,
            "reports": [],
            "has_duplicates": False,
            "is_duplicate": is_duplicate
        }
        
        # Update user's media list
        self.users[user_id]["media_ids"].append(media_id)
        self.users[user_id]["uploads"] += 1
        self.users[user_id]["last_activity"] = time.time()
        
        # Check if user becomes active after 30 uploads
        if not self.users[user_id]["active"] and not self.users[user_id]["premium"] and self.users[user_id]["uploads"] >= 30:
            self.users[user_id]["active"] = True
            self.stats["active_users"] += 1
            # Reset activity timer
            self.users[user_id]["activity_timer"] = time.time() + 86400  # 24 hours from now
            
            # Store the actual expiration time separately (for internal use)
            # This will be used to track the real expiration time based on upload count
            if not "actual_expiration" in self.users[user_id]:
                self.users[user_id]["actual_expiration"] = self.users[user_id]["activity_timer"]
        
        # Check if user has uploaded multiples of 30 media and extend their actual expiration time
        # while still showing 24 hours to the user
        if self.users[user_id]["active"] and not self.users[user_id]["premium"] and self.users[user_id]["uploads"] % 30 == 0 and self.users[user_id]["uploads"] > 30:
            # For every 30 uploads, add 24 hours to the actual expiration time
            # But keep the displayed activity_timer at 24 hours from now
            self.users[user_id]["activity_timer"] = time.time() + 86400  # Always show 24 hours
            
            # Extend the actual expiration by 24 hours
            if "actual_expiration" in self.users[user_id]:
                self.users[user_id]["actual_expiration"] = max(self.users[user_id]["actual_expiration"], time.time() + 86400)
            else:
                self.users[user_id]["actual_expiration"] = time.time() + 86400 * 2  # 48 hours
        
        # Update stats
        self.stats["total_media_count"] += 1
        
        # Save changes
        self._save_json(self.media_file, self.media)
        self._save_json(self.users_file, self.users)
        self._save_json(self.stats_file, self.stats)
        
        return media_id
    
    def add_media_instant(self, user_id, file_id, file_path, file_size, media_type, caption=None, file_unique_id=None):
        """Add a media file to the database instantly without waiting for download
        This is used for forwarded media from inactive users to count towards activity immediately"""
        user_id = str(user_id)
        
        # Check if user exists and is not banned
        if user_id not in self.users or self.users[user_id]["banned"]:
            return None
        
        # Check if this file_id already exists for this user
        for media_id, media_data in self.media.items():
            if media_data["file_id"] == file_id and media_data["user_id"] == user_id:
                return media_id
        
        # Generate a unique media ID
        media_id = f"media_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Add media to database with placeholder path (will be updated later)
        self.media[media_id] = {
            "user_id": user_id,
            "file_id": file_id,
            "file_unique_id": file_unique_id,
            "file_path": file_path,  # This will be None initially
            "file_size": file_size,  # This will be 0 initially
            "media_type": media_type,
            "caption": caption,
            "upload_time": time.time(),
            "alias": self.users[user_id]["alias"],
            "premium": self.users[user_id]["premium"],
            "reported": False,
            "reports": [],
            "has_duplicates": False,
            "is_duplicate": False,
            "pending_download": True  # Mark as pending download
        }
        
        # Update user's media list
        self.users[user_id]["media_ids"].append(media_id)
        self.users[user_id]["uploads"] += 1
        self.users[user_id]["last_activity"] = time.time()
        
        # Check if user becomes active after 30 uploads
        if not self.users[user_id]["active"] and not self.users[user_id]["premium"] and self.users[user_id]["uploads"] >= 30:
            self.users[user_id]["active"] = True
            self.stats["active_users"] += 1
            # Reset activity timer
            self.users[user_id]["activity_timer"] = time.time() + 86400  # 24 hours from now
            
            # Store the actual expiration time separately (for internal use)
            # This will be used to track the real expiration time based on upload count
            if not "actual_expiration" in self.users[user_id]:
                self.users[user_id]["actual_expiration"] = self.users[user_id]["activity_timer"]
        
        # Check if user has uploaded multiples of 30 media and extend their actual expiration time
        # while still showing 24 hours to the user
        if self.users[user_id]["active"] and not self.users[user_id]["premium"] and self.users[user_id]["uploads"] % 30 == 0 and self.users[user_id]["uploads"] > 30:
            # For every 30 uploads, add 24 hours to the actual expiration time
            # But keep the displayed activity_timer at 24 hours from now
            self.users[user_id]["activity_timer"] = time.time() + 86400  # Always show 24 hours
            
            # Extend the actual expiration by 24 hours
            if "actual_expiration" in self.users[user_id]:
                self.users[user_id]["actual_expiration"] = max(self.users[user_id]["actual_expiration"], time.time() + 86400)
            else:
                self.users[user_id]["actual_expiration"] = time.time() + 86400 * 2  # 48 hours
        
        # Update stats
        self.stats["total_media_count"] += 1
        
        # Save changes
        self._save_json(self.media_file, self.media)
        self._save_json(self.users_file, self.users)
        self._save_json(self.stats_file, self.stats)
        
        return media_id
        
    def delete_media(self, media_id):
        """Delete a media file from the database"""
        if media_id in self.media:
            user_id = self.media[media_id]["user_id"]
            
            # Remove from user's media list
            if user_id in self.users and media_id in self.users[user_id]["media_ids"]:
                self.users[user_id]["media_ids"].remove(media_id)
                self.users[user_id]["uploads"] -= 1
                
                # Check if user becomes inactive after deletion
                if not self.users[user_id]["premium"] and self.users[user_id]["uploads"] < 30:
                    if self.users[user_id]["active"]:
                        self.users[user_id]["active"] = False
                        self.stats["active_users"] -= 1
            
            # Delete the file from disk if it exists
            file_path = self.media[media_id]["file_path"]
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {str(e)}")
            
            # Remove from media database
            del self.media[media_id]
            
            # Update stats
            self.stats["total_media_count"] -= 1
            
            # Save changes
            self._save_json(self.media_file, self.media)
            self._save_json(self.users_file, self.users)
            self._save_json(self.stats_file, self.stats)
            
            return True
        return False
    
    def get_media(self, media_id):
        """Get media data"""
        return self.media.get(media_id, None)
    
    def get_all_media(self):
        """Get all media data"""
        return self.media
    
    def get_user_media(self, user_id):
        """Get all media for a user"""
        user_id = str(user_id)
        if user_id in self.users:
            user_media = []
            for media_id in self.users[user_id]["media_ids"]:
                if media_id in self.media:
                    user_media.append(self.media[media_id])
            return user_media
        return []
    
    def check_duplicate_media(self, file_id, user_id, file_unique_id=None):
        """Check if this file_id or file_unique_id is a duplicate of an existing media from another user"""
        user_id = str(user_id)
        
        # Create duplicates directory if it doesn't exist
        duplicates_dir = os.path.join(MEDIA_DIR, "duplicates")
        os.makedirs(duplicates_dir, exist_ok=True)
        
        # Check all media to find if this file_id or file_unique_id matches any existing media from other users
        for media_id, media_data in self.media.items():
            # Skip media from the same user
            if media_data["user_id"] == user_id:
                continue
                
            # If file_id matches, it's a duplicate
            if media_data["file_id"] == file_id:
                return media_id
                
            # If file_unique_id matches and it's provided, it's a duplicate
            if file_unique_id and media_data.get("file_unique_id") == file_unique_id:
                return media_id
                
        return None
        
    def get_syncable_media(self, user_id):
        """Get media that can be synced to a user"""
        user_id = str(user_id)
        if user_id not in self.users:
            return []
        
        # Get all media IDs except those already synced to this user
        synced_media = set(self.users[user_id]["synced_media"])
        user_media = set(self.users[user_id]["media_ids"])
        
        # Get all media IDs
        all_media_ids = set(self.media.keys())
        
        # Media that can be synced = all media - user's own media - already synced media
        syncable_media_ids = all_media_ids - user_media - synced_media
        
        # Filter out media marked as duplicates
        non_duplicate_media = []
        for media_id in syncable_media_ids:
            # Skip media marked as duplicates
            if self.media[media_id].get("is_duplicate", False):
                continue
            non_duplicate_media.append(self.media[media_id])
        
        # Sort by upload time (newest first)
        non_duplicate_media.sort(key=lambda x: x["upload_time"], reverse=True)
        
        return non_duplicate_media
    
    def mark_media_synced(self, user_id, media_id):
        """Mark a media as synced to a user"""
        user_id = str(user_id)
        if user_id in self.users and media_id in self.media:
            if media_id not in self.users[user_id]["synced_media"]:
                self.users[user_id]["synced_media"].append(media_id)
                self._save_json(self.users_file, self.users)
                return True
        return False
    
    # Access key management
    def create_key(self, key_type="normal", uses=1):
        """Create a new access key"""
        # Generate a random key
        key = self._generate_key()
        
        # Add key to database
        self.keys[key] = {
            "type": key_type,
            "created": time.time(),
            "uses": 0,
            "max_uses": uses,
            "active": True,
            "users": []
        }
        
        # Update stats
        self.stats["keys_generated"] += 1
        
        # Save changes
        self._save_json(self.keys_file, self.keys)
        self._save_json(self.stats_file, self.stats)
        
        return key
    
    def get_key(self, key):
        """Get key data"""
        return self.keys.get(key, None)
    
    def get_key_type(self, key):
        """Get key type"""
        if key in self.keys:
            return self.keys[key]["type"]
        return None
        
    def cleanup_duplicate_media(self):
        """Clean up duplicate media entries and files older than 24 hours"""
        # 24 hours in seconds
        cleanup_threshold = 86400  # 24 hours in seconds
        current_time = time.time()
        
        # Get duplicates directory path
        duplicates_dir = os.path.join(MEDIA_DIR, "duplicates")
        
        # Iterate through all media entries
        for media_id, media_data in list(self.media.items()):
            # Check if this is a duplicate that needs to be cleaned up
            if media_data.get("is_duplicate", False):
                # Calculate age of the duplicate
                age = current_time - media_data["upload_time"]
                
                # If older than 24 hours, delete it
                if age >= cleanup_threshold:
                    # Delete the file if it exists
                    file_path = media_data.get("file_path")
                    if file_path and os.path.exists(file_path) and file_path.startswith(duplicates_dir):
                        try:
                            os.remove(file_path)
                            logger.info(f"Deleted duplicate file: {file_path}")
                        except Exception as e:
                            logger.error(f"Error deleting duplicate file {file_path}: {str(e)}")
                    
                    # Remove the media entry
                    del self.media[media_id]
                    continue
            
            # Check all media for duplicates
            if "has_duplicates" in media_data and media_data["has_duplicates"] and "duplicates" in media_data:
                # Filter out duplicates older than 24 hours
                expired_duplicates = []
                remaining_duplicates = []
                
                for duplicate in media_data["duplicates"]:
                    # Check if duplicate is older than 24 hours
                    if current_time - duplicate["detected_time"] > cleanup_threshold:
                        expired_duplicates.append(duplicate)
                        
                        # Try to delete the duplicate file if file_id exists
                        if "file_id" in duplicate:
                            # Find any media entries with this file_id
                            for dup_id, dup_data in list(self.media.items()):
                                if dup_data.get("file_id") == duplicate["file_id"] and dup_data.get("user_id") == duplicate["user_id"]:
                                    # Delete the file if it exists and is in duplicates directory
                                    dup_file_path = dup_data.get("file_path")
                                    if dup_file_path and os.path.exists(dup_file_path) and dup_file_path.startswith(duplicates_dir):
                                        try:
                                            os.remove(dup_file_path)
                                            logger.info(f"Deleted duplicate file: {dup_file_path}")
                                        except Exception as e:
                                            logger.error(f"Error deleting duplicate file {dup_file_path}: {str(e)}")
                                    
                                    # Remove the media entry
                                    del self.media[dup_id]
                    else:
                        remaining_duplicates.append(duplicate)
                
                # Update the duplicates list
                media_data["duplicates"] = remaining_duplicates
                
                # If no duplicates remain, update the has_duplicates flag
                if not remaining_duplicates:
                    media_data["has_duplicates"] = False
        
        # Save the changes
        self._save_json(self.media_file, self.media)
    
    def disable_key(self, key):
        """Disable an access key"""
        if key in self.keys:
            self.keys[key]["active"] = False
            self._save_json(self.keys_file, self.keys)
            return True
        return False
    
    def is_key_valid(self, key):
        """Check if a key is valid"""
        if key not in self.keys:
            return False
        
        key_data = self.keys[key]
        
        # Check if key is active
        if not key_data["active"]:
            return False
        
        # Check if key has reached max uses
        if key_data["uses"] >= key_data["max_uses"] and key_data["max_uses"] > 0:
            return False
        
        return True
    
    # Activity system
    def check_activity(self, user_id):
        """Check if a user is active and update activity status"""
        user_id = str(user_id)
        if user_id not in self.users:
            return False
        
        user = self.users[user_id]
        
        # Premium users are always active
        if user["premium"]:
            return True
        
        # Check if activity timer has expired
        current_time = time.time()
        
        # Use actual_expiration time if available, otherwise use activity_timer
        expiration_time = user.get("actual_expiration", user["activity_timer"])
        
        if current_time > expiration_time:
            # User is now inactive
            if user["active"]:
                user["active"] = False
                self.stats["active_users"] -= 1
                # Reset actual_expiration when user becomes inactive
                if "actual_expiration" in user:
                    del user["actual_expiration"]
                self._save_json(self.users_file, self.users)
                self._save_json(self.stats_file, self.stats)
            return False
        
        return user["active"]
    
    def reset_activity(self, user_id):
        """Reset a user's activity timer"""
        user_id = str(user_id)
        if user_id in self.users:
            # Reset the visible activity timer to 24 hours from now
            self.users[user_id]["activity_timer"] = time.time() + 86400  # 24 hours from now
            
            # If user has uploaded more than 30 media, calculate the actual expiration time
            # based on their upload count (30 uploads = 24 hours)
            if self.users[user_id]["uploads"] >= 30:
                # Calculate how many 24-hour periods they've earned
                periods = self.users[user_id]["uploads"] // 30
                # Set the actual expiration time accordingly
                self.users[user_id]["actual_expiration"] = time.time() + (86400 * periods)
            else:
                # If they haven't uploaded 30 media yet, remove actual_expiration if it exists
                if "actual_expiration" in self.users[user_id]:
                    del self.users[user_id]["actual_expiration"]
            
            self._save_json(self.users_file, self.users)
            return True
        return False
        
    def update_user_activity(self, user_id):
        """Update a user's last activity timestamp and reset activity timer"""
        user_id = str(user_id)
        if user_id in self.users:
            current_time = time.time()
            self.users[user_id]["last_activity"] = current_time
            
            # Always update the visible activity timer to 24 hours from now
            self.users[user_id]["activity_timer"] = current_time + 86400  # 24 hours from now
            
            # If there's an actual_expiration time, preserve it
            # This ensures we don't lose the extended time from multiple uploads
            if "actual_expiration" in self.users[user_id]:
                # Only update if the current actual_expiration is less than 24 hours from now
                # This prevents shortening the actual expiration time
                if self.users[user_id]["actual_expiration"] < current_time + 86400:
                    self.users[user_id]["actual_expiration"] = current_time + 86400
            
            # Set user as online
            self.users[user_id]["online"] = True
            self._save_json(self.users_file, self.users)
            return True
        return False
        
    def set_user_offline(self, user_id):
        """Set a user as offline"""
        user_id = str(user_id)
        if user_id in self.users:
            self.users[user_id]["online"] = False
            self._save_json(self.users_file, self.users)
            return True
        return False
        
    def get_online_users(self):
        """Get all online users"""
        return {uid: user for uid, user in self.users.items() 
                if user.get("online", False) and not user.get("banned", False)}
    
    def get_time_until_inactive(self, user_id):
        """Get time until a user becomes inactive"""
        user_id = str(user_id)
        if user_id in self.users:
            user = self.users[user_id]
            
            # Premium users never become inactive
            if user["premium"]:
                return float('inf')
            
            # Calculate time remaining
            current_time = time.time()
            
            # Always show the visible activity timer (24 hours) to the user
            # even if they have a longer actual_expiration time
            time_remaining = max(0, user["activity_timer"] - current_time)
            return time_remaining
        return 0
    
    # Community link methods
    def update_community_link(self, new_link, link_name=None):
        """Update the community link in the database"""
        self.stats["community_link"] = new_link
        if link_name:
            self.stats["community_link_name"] = link_name
        self._save_json(self.stats_file, self.stats)
        return True
    
    def get_community_link(self):
        """Get the current community link"""
        return self.stats.get("community_link", "https://t.me/SIN_CITY_C_BOT")
        
    def get_community_link_name(self):
        """Get the current community link name"""
        return self.stats.get("community_link_name", None)
        
    def update_pinned_message(self, message_text, message_id=None):
        """Update the pinned message in stats"""
        self.stats["pinned_message"] = {
            "text": message_text,
            "message_id": message_id,
            "updated_at": time.time()
        }
        self._save_json(self.stats_file, self.stats)
        return True
        
    def get_pinned_message(self):
        """Get the pinned message from stats"""
        return self.stats.get("pinned_message", None)
        
    def should_show_pinned_message(self, user_id):
        """Check if pinned message should be shown to the user
        Returns True if:
        1. User has never seen the pinned message, or
        2. It's been more than 24 hours since user last saw the pinned message
        """
        user_id = str(user_id)
        if not self.user_exists(user_id) or not self.get_pinned_message():
            return False
            
        user = self.get_user(user_id)
        last_pin_view = user.get("last_pin_view", 0)
        current_time = time.time()
        
        # Show if user hasn't seen it in the last 24 hours
        return (current_time - last_pin_view) >= 86400
        
    def update_user_pin_view(self, user_id):
        """Update the timestamp when user last saw the pinned message"""
        user_id = str(user_id)
        if not self.user_exists(user_id):
            return False
            
        self.users[user_id]["last_pin_view"] = time.time()
        self._save_json(self.users_file, self.users)
        return True
    
    # Helper methods
    def _generate_alias(self):
        """Generate a random alias using procedural generation with emojis"""
        import secrets
        
        # Emoji pool
        EMOJI_POOL = [
            "🌀", "💫", "🌌", "🌙", "🧬", "🔥", "🔮", "🎭", "🛡", "📡",
            "🧊", "🐚", "🕯", "🌿", "🌟", "⚡", "🌪️", "🗝️", "🌑", "🕳️"
        ]
        
        # First word options (nouns and adjectives)
        FIRST_WORDS = [
            "Nexus", "Cyber", "Shadow", "Ghost", "Zero", "Neuro", "Crypt", "Xeno", "Synth", "Rust",
            "Drone", "Hack", "Warp", "Void", "Static", "Quantum", "Iron", "Phantom", "Obsidian", "Cipher",
            "Lunar", "Nova", "Echo", "Crimson", "Twilight", "Oracle", "Voyager", "Specter", "Drift", "Glyph",
            "Mystic", "Astral", "Cosmic", "Digital", "Eternal", "Fusion", "Hyper", "Infinite", "Jade", "Kinetic"
        ]
        
        # Second word options (nouns)
        SECOND_WORDS = [
            "Vortex", "Lynx", "Phreak", "Droid", "Mancer", "Glitch", "Byte", "Core", "Vault", "Nexus",
            "Shard", "Wire", "Pulse", "Fang", "Haze", "Thorn", "Blade", "Veil", "Storm", "Raven",
            "Serpent", "Claw", "Shade", "Infit", "Realm", "Titan", "Vertex", "Whisper", "Zenith", "Abyss",
            "Beacon", "Cascade", "Destiny", "Echo", "Frontier", "Guardian", "Horizon", "Illusion", "Journey", "Knight"
        ]
        
        # Generate word parts
        emoji = secrets.choice(EMOJI_POOL)
        first_word = secrets.choice(FIRST_WORDS).lower()
        second_word = secrets.choice(SECOND_WORDS).lower()
        
        # Capitalize first letters
        first_word = first_word[0].upper() + first_word[1:]
        second_word = second_word[0].upper() + second_word[1:]
        
        # Create alias with emoji and two words
        alias = f"{emoji} {first_word} {second_word}"
        return alias
    
    def _generate_key(self):
        """Generate a random access key"""
        chars = string.ascii_uppercase + string.digits
        key = ''.join(random.choice(chars) for _ in range(8))
        return key
    
    # User management - Admin operations
    def ghost_user(self, user_id):
        """Make a user invisible in top users list"""
        user_id = str(user_id)
        if user_id in self.users and not self.users[user_id]["ghosted"]:
            self.users[user_id]["ghosted"] = True
            self._save_json(self.users_file, self.users)
            return True
        return False
    
    def unghost_user(self, user_id):
        """Make a user visible in top users list"""
        user_id = str(user_id)
        if user_id in self.users and self.users[user_id]["ghosted"]:
            self.users[user_id]["ghosted"] = False
            self._save_json(self.users_file, self.users)
            return True
        return False
    
    def promote_user(self, user_id):
        """Promote a user to admin"""
        user_id = str(user_id)
        if user_id in self.users and not self.users[user_id]["admin"]:
            self.users[user_id]["admin"] = True
            self._save_json(self.users_file, self.users)
            return True
        return False
    
    def demote_user(self, user_id):
        """Demote an admin to regular user"""
        user_id = str(user_id)
        if user_id in self.users and self.users[user_id]["admin"]:
            self.users[user_id]["admin"] = False
            self._save_json(self.users_file, self.users)
            return True
        return False
    
    def get_top_users(self, limit=5):
        """Get top users by upload count, excluding ghosted users"""
        # Filter out ghosted users
        visible_users = {uid: user for uid, user in self.users.items() if not user.get("ghosted", False)}
        
        # Sort by upload count (descending)
        sorted_users = sorted(visible_users.items(), key=lambda x: x[1]["uploads"], reverse=True)
        
        # Return top N users
        return sorted_users[:limit]
    
    # Statistics
    def get_stats(self):
        """Get bot statistics"""
        # Update uptime
        self.stats["uptime"] = time.time() - self.stats["start_time"]
        
        # Calculate database size
        db_size = 0
        for file_path in [self.users_file, self.keys_file, self.media_file, self.messages_file, self.stats_file]:
            if os.path.exists(file_path):
                db_size += os.path.getsize(file_path)
        
        self.stats["database_size"] = db_size
        
        # Calculate media directory size
        media_dir_size = 0
        if os.path.exists(MEDIA_DIR):
            for root, dirs, files in os.walk(MEDIA_DIR):
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        media_dir_size += os.path.getsize(file_path)
                    except OSError:
                        pass # Ignore files that can't be accessed
        
        self.stats["media_size"] = media_dir_size
        
        return self.stats

    def get_reported_media_count(self):
        """Get the count of reported media files"""
        count = 0
        for media_id, media_data in self.media.items():
            if media_data.get("reported", False) and media_data.get("reports", []):
                count += 1
        return count