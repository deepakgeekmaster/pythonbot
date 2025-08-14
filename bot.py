import os
import re
import json
import time
import logging
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserNotParticipant, ChatAdminRequired
from dotenv import load_dotenv
from asyncio import Queue

# Import custom modules
from database import Database, MEDIA_DIR
import utils

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Track bot start time for uptime calculation
BOT_START_TIME = time.time()

# Load environment variables from .env file
load_dotenv()

# Get API credentials from environment variables
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))  # Owner ID for admin commands
BOT_USERNAME = os.getenv("BOT_USERNAME")
OWNER_USERNAME = os.getenv("OWNER_USERNAME")

# Initialize database
db = Database()

# Initialize the MTProto client for handling large files
app = Client(
    "media_handler_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,  # Using bot token for hybrid mode
    workdir=os.getcwd()
)

# Constants
MAX_SYNC_NORMAL = 20  # Maximum media files a normal user can sync
REQUIRED_UPLOADS = 30  # Required uploads to become active
ACTIVITY_PERIOD = 86400  # 24 hours in seconds
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes

# Global media processing queues - one per user
user_media_queues = {}
# Flag to track if the media processor is running for each user
user_media_processors = {}

# Helper functions
# Custom filter for admin checks
async def is_admin_filter(_, __, message: Message):
    return is_admin(message.from_user.id)

def is_authorized(user_id):
    """Check if a user is authorized to use the bot"""
    user_id = str(user_id)
    if not db.user_exists(user_id):
        return False
    user = db.get_user(user_id)
    return user and not user["banned"]

def is_admin(user_id):
    """Check if a user is an admin"""
    # Convert user_id to int for comparison with OWNER_ID (which is an int)
    if str(user_id) == str(OWNER_ID) or int(str(user_id)) == OWNER_ID:
        return True
    
    user = db.get_user(str(user_id))
    return user and user["admin"]

def is_active(user_id):
    """Check if a user is active"""
    return db.check_activity(str(user_id))

def is_premium(user_id):
    """Check if a user is premium"""
    user_id = str(user_id)
    user = db.get_user(user_id)
    # Explicitly check if user exists, has premium field, and premium is True
    return user is not None and "premium" in user and user["premium"] is True

# Message handlers
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle the /start command with optional access key"""
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    username = message.from_user.username
    
    # Check if user is already registered
    if db.user_exists(str(user_id)):
        user = db.get_user(str(user_id))
        
        # Check if user is banned
        if user["banned"]:
            await message.reply("🚫 **You are banned from using this bot.**")
            return
        
        # Send welcome back message
        user_data = db.get_user(str(user_id))
        # Explicitly check premium status from database
        is_user_premium = False
        if user_data and "premium" in user_data:
            is_user_premium = user_data["premium"]
            
        welcome_msg = utils.get_welcome_message(message.from_user.first_name, is_user_premium)
        keyboard = utils.get_start_keyboard(str(user_id), is_admin(str(user_id)))
        await message.reply(welcome_msg, reply_markup=keyboard)
        
        # Show pinned message if it exists and user hasn't seen it in the last 24 hours
        pinned_message = db.get_pinned_message()
        if pinned_message and db.should_show_pinned_message(user_id):
            await message.reply(
                f"📌 **Pinned Message** 📌\n\n"
                f"{pinned_message['text']}"
            )
            # Update the timestamp when user last saw the pinned message
            db.update_user_pin_view(user_id)
        return
    
    # Check for access key
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) > 1:
        access_key = command_parts[1].strip().upper()
        
        # Validate access key
        if db.is_key_valid(access_key):
            # Register user
            db.add_user(str(user_id), username, user_name, access_key)
            user = db.get_user(str(user_id))
            
            # Send welcome message
            welcome_msg = utils.get_welcome_message(user_name, user["premium"])
            keyboard = utils.get_start_keyboard(str(user_id), is_admin(str(user_id)))
            await message.reply(welcome_msg, reply_markup=keyboard)
            
            # Send admin notification
            if OWNER_ID:
                await client.send_message(
                    OWNER_ID,
                    f"🆕 **New User Joined**\n\n"
                    f"👤 User: {user_name} (@{username if username else 'No username'})\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"🔑 Key: `{access_key}`\n"
                    f"🎭 Alias: {user['alias']}\n"
                    f"✨ Premium: {'Yes' if user['premium'] else 'No'}"
                )
        else:
            # Invalid key
            access_denied = utils.get_access_denied_message()
            keyboard = utils.get_access_denied_keyboard()
            await message.reply(access_denied, reply_markup=keyboard)
    else:
        # No key provided - show welcome message for new users
        welcome_msg = utils.get_new_user_welcome_message(user_name)
        keyboard = utils.get_access_denied_keyboard()
        await message.reply(welcome_msg, reply_markup=keyboard)

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle the /help command"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    # Check if user is admin
    admin_status = is_admin(str(user_id))
    
    # Basic help message
    help_text = (
        "✨ **Media Vault Help Center** ✨\n\n"
        "🚀 **User Commands:**\n"
        "🏠 /start - Launch the bot\n"
        "❓ /help - Display this help guide\n"
        "🧲 /syncmedia - Get new media from vault\n"
        "📊 /mystats - Check your activity stats\n"
        "🚨 /report - Report content issues (reply to message)\n"
        "🔗 /link - Access the community link\n"
        "📌 /showpin - View the pinned message\n"
        "🚪 /logout - Exit the bot and remove your data\n\n"
        "🌟 **Amazing Features:**\n"
        "📁 Upload media files up to 2GB in size\n"
        "🔒 Your identity is secured with a unique alias\n"
        "🔍 Smart duplicate detection system\n"
        "💎 Premium users enjoy unlimited access\n\n"
    )
    
    # Add admin commands if user is admin
    if admin_status:
        help_text += (
            "⚙️ **Admin Commands:**\n"
            "🔑 /getkey [uses] [premium] - Generate access key\n"
            "🚫 /ban <user_id> - Ban a user\n"
            "✅ /unban <user_id> - Unban a user\n"
            "⭐ /upgrade <user_id> - Upgrade user to premium\n"
            "📌 /pin <msg> - Pin a message\n"
            "🗑️ /delete <media_id> - Delete media\n"
            "⏱️ /reset <user_id> - Reset user's activity timer\n"
            "📢 /broadcast <msg> - Send message to all users\n"
            "🔍 /search <alias> - Search users by alias name\n"
            "👻 /ghost <user_id> - Make user invisible\n"
            "👁️ /unghost <user_id> - Make user visible\n"
            "👑 /admin <user_id> - Promote user to admin\n"
            "👤 /demote <user_id> - Demote admin to user\n"
            "📊 /status - View bot statistics\n"
            "🔒 /disablekey <key> - Disable an access key\n"
        )
    
    await message.reply(help_text)

@app.on_message(filters.command("report"))
async def report_command(client: Client, message: Message):
    """Handle the /report command to report inappropriate content"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    # Check if message is a reply
    if not message.reply_to_message:
        await message.reply(
            "🚨 **Report Error** 🚨\n\n"
            "📌 You must reply to a media message you want to report.\n"
            "💡 Example: Reply to a media message with /report\n"
            "🔍 This helps us identify the specific content to review."
        )
        return
    
    # Check if replied message has media
    replied_msg = message.reply_to_message
    if not replied_msg.media:
        await message.reply(
            "🚨 **Report Error** 🚨\n\n"
            "📂 The message you replied to doesn't contain any media.\n"
            "🖼️ You can only report media content (photos, videos, etc).\n"
            "⚠️ Please try again with a message containing media."
        )
        return
    
    # Get media ID from database
    media_type = replied_msg.media.value
    file_id = getattr(replied_msg, media_type).file_id
    
    # Find media in database
    media_id = None
    for mid, media_data in db.media.items():
        if media_data["file_id"] == file_id:
            media_id = mid
            break
    
    if not media_id:
        await message.reply(
            "🚨 **Report Error** 🚨\n\n"
            "This media is not in our database.\n"
            "You can only report media that was shared through this bot."
        )
        return
    
    # Add report to database
    db.media[media_id]["reported"] = True
    reporter_info = {
        "user_id": str(user_id),
        "time": time.time(),
        "alias": db.get_user(user_id)["alias"]
    }
    
    if "reports" not in db.media[media_id]:
        db.media[media_id]["reports"] = []
    
    db.media[media_id]["reports"].append(reporter_info)
    db._save_json(db.media_file, db.media)
    
    # Send confirmation to user
    report_msg = utils.get_report_message(media_id)
    await message.reply(report_msg)
    
    # Notify admin
    if OWNER_ID:
        admin_report = utils.get_admin_report_message(
            media_id,
            user_id,
            db.get_user(str(user_id))["alias"]
        )
        keyboard = utils.get_report_keyboard(media_id, user_id)
        await client.send_message(OWNER_ID, admin_report, reply_markup=keyboard)

@app.on_message(filters.command("mystats"))
async def mystats_command(client: Client, message: Message):
    """Handle the /mystats command"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    # Get user data
    user = db.get_user(str(user_id))
    
    # Get time until inactive
    time_remaining = db.get_time_until_inactive(str(user_id))
    
    # Generate stats message
    stats_msg = utils.get_stats_message(user, time_remaining)
    
    await message.reply(stats_msg)

@app.on_message(filters.command("syncmedia"))
async def syncmedia_command(client: Client, message: Message):
    """Handle the /syncmedia command with support for concurrent operations"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    # Send an immediate acknowledgment to the user
    ack_msg = await message.reply("🔄 Processing your sync request...")
    
    # Create a task to process the sync request asynchronously
    # This allows the bot to handle other commands while processing sync requests
    asyncio.create_task(process_sync_request(client, message, user_id, ack_msg))

async def process_sync_request(client: Client, message: Message, user_id, ack_msg):
    """Process sync media request asynchronously to allow concurrent operations"""
    try:
        # Check if user is active or premium
        user = db.get_user(str(user_id))
        if not user["active"] and not user["premium"]:
            await ack_msg.edit_text(
                "❌ **You are not active**\n\n"
                f"You need to upload {REQUIRED_UPLOADS} media files to become active.\n"
                f"Current uploads: {user['uploads']}"
            )
            return
        
        # Initialize sync_attempts counter if it doesn't exist
        if "sync_attempts" not in user:
            user["sync_attempts"] = 0
        
        # Check if user already has a pending sync operation
        if "pending_sync" in user and user["pending_sync"]:
            # Generate a unique operation ID for this request
            operation_id = f"sync_{int(time.time() * 1000)}"
            
            # Increment consecutive sync attempts counter
            user["sync_attempts"] += 1
            db.update_user(str(user_id), user)
            
            # If user has used sync command less than 5 times in a row, automatically replace previous sync
            if user["sync_attempts"] < 5:
                # Clear previous pending sync
                user["pending_sync"] = []
                if "sync_operation_id" in user:
                    del user["sync_operation_id"]
                if "sync_request_time" in user:
                    del user["sync_request_time"]
                db.update_user(str(user_id), user)
                
                # Inform user and prompt to use /syncmedia again
                await ack_msg.edit_text(
                    "✅ **Previous sync operation automatically cleared**\n\n"
                    "Please use /syncmedia command again to start a new sync operation."
                )
                return
            
            # If user has used sync command 5 or more times in a row, show only replace button
            await ack_msg.edit_text(
                f"⚠️ **You already have a pending sync operation**\n\n"
                f"Operation ID: {operation_id}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🟩CLICK ON REPLACE PREVIOUS SYNC🟩", callback_data="replace_sync")]
                ])
            )
            return
    
        # Get syncable media
        syncable_media = db.get_syncable_media(user_id)
        
        # Filter out duplicate media
        filtered_media = []
        processed_file_unique_ids = set()  # Track file_unique_ids we've already processed
        
        # First pass: identify original media (non-duplicates)
        original_media = {}
        for media in syncable_media:
            # Find the media entry
            media_id = None
            for mid, mdata in db.media.items():
                if mdata["file_id"] == media["file_id"] and mdata["user_id"] == media["user_id"]:
                    media_id = mid
                    break
            
            # Skip if we can't find the media entry
            if not media_id:
                continue
                
            # Check if this is a duplicate
            if not db.media[media_id].get("is_duplicate", False):
                # This is an original media, store it by file_unique_id if available, otherwise by file_id
                file_unique_id = db.media[media_id].get("file_unique_id")
                if file_unique_id:
                    if file_unique_id not in original_media:
                        original_media[file_unique_id] = media
                else:
                    # Fallback to file_id if file_unique_id is not available
                    if media["file_id"] not in original_media:
                        original_media[media["file_id"]] = media
        
        # Second pass: add only original media or first instance of each file_unique_id
        for media in syncable_media:
            # Find the media entry to get file_unique_id
            media_id = None
            for mid, mdata in db.media.items():
                if mdata["file_id"] == media["file_id"] and mdata["user_id"] == media["user_id"]:
                    media_id = mid
                    break
            
            # Skip if we can't find the media entry
            if not media_id:
                continue
                
            # Get file_unique_id if available
            file_unique_id = db.media[media_id].get("file_unique_id")
            
            # Skip if we've already processed this file_unique_id or if it's marked as a duplicate
            if (file_unique_id and file_unique_id in processed_file_unique_ids) or db.media[media_id].get("is_duplicate", False):
                continue
                
            # If we have an original version of this file_unique_id, use that instead
            if file_unique_id and file_unique_id in original_media:
                if original_media[file_unique_id] != media:  # Don't add twice if it's the same media
                    filtered_media.append(original_media[file_unique_id])
                    processed_file_unique_ids.add(file_unique_id)
                    continue
            # Fallback to file_id if file_unique_id is not available
            elif not file_unique_id and media["file_id"] in original_media:
                if original_media[media["file_id"]] != media:  # Don't add twice if it's the same media
                    filtered_media.append(original_media[media["file_id"]])
                    if file_unique_id:
                        processed_file_unique_ids.add(file_unique_id)
                    continue
            
            # Add this file_unique_id to our processed set
            if file_unique_id:
                processed_file_unique_ids.add(file_unique_id)
            
            # Add to filtered media
            filtered_media.append(media)
        
        # Update syncable media with filtered list
        syncable_media = filtered_media
        
        # Check if there's any media to sync after filtering
        if not syncable_media:
            await ack_msg.edit_text("📭 **No new media available to sync**")
            return
        
        # Check if normal user has reached sync limit
        if not user["premium"] and len(user["synced_media"]) >= MAX_SYNC_NORMAL:
            # Get total available media count
            total_available_media = len(syncable_media) + MAX_SYNC_NORMAL
            sync_limit_msg = utils.get_sync_limit_message(total_available_media)
            keyboard = utils.get_premium_promo_keyboard()
            await ack_msg.edit_text(sync_limit_msg, reply_markup=keyboard)
            return
        
        # Calculate how many media files to sync
        if user["premium"]:
            # Premium users can sync all available media
            media_to_sync = syncable_media
        else:
            # Normal users can sync up to MAX_SYNC_NORMAL total
            remaining = MAX_SYNC_NORMAL - len(user["synced_media"])
            media_to_sync = syncable_media[:remaining]
        
        # Generate a unique operation ID for this sync request
        operation_id = f"sync_{user_id}_{int(time.time() * 1000)}"
        
        # Send confirmation message with accept/reject buttons
        # For normal users, show both total available and actual sync count
        if not user["premium"] and len(syncable_media) > len(media_to_sync):
            total_available = len(syncable_media)
            confirmation_msg = utils.get_sync_confirmation_message(len(media_to_sync))
            # Add information about total available media
            confirmation_msg = confirmation_msg.replace(
                f"🚨 {len(media_to_sync)} MEDIA FILES 🚨 queued for sync!", 
                f"🚨 {len(media_to_sync)} MEDIA FILES 🚨 queued for sync!\n📊 Total available: {total_available} (Limited to {MAX_SYNC_NORMAL} for standard users)"
            )
        else:
            confirmation_msg = utils.get_sync_confirmation_message(len(media_to_sync))
        
        confirmation_msg += f"\n\n🆔 Operation ID: {operation_id}"
        keyboard = utils.get_sync_confirmation_keyboard()
        await ack_msg.edit_text(confirmation_msg, reply_markup=keyboard)
        
        # Store media_to_sync in user data for later use when confirmed
        user["pending_sync"] = media_to_sync
        user["sync_operation_id"] = operation_id
        user["sync_request_time"] = time.time()
        db.update_user(str(user_id), user)
    except Exception as e:
        logger.error(f"Error processing sync request: {str(e)}")
        await ack_msg.edit_text(f"❌ Error processing your sync request: {str(e)}\nPlease try again later.")



@app.on_message(filters.command("top"))
async def top_command(client: Client, message: Message):
    """Handle the /top command to show top 5 contributors"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    # Get top 5 users by upload count
    top_users = db.get_top_users(limit=5)
    
    # Generate and send top users message
    top_users_msg = utils.get_top_users_message(top_users)
    await message.reply(top_users_msg)

@app.on_message(filters.command("link"))
async def link_command(client: Client, message: Message):
    """Handle the /link command to show community link"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    # Show the current link
    link_msg = utils.get_link_message()
    await message.reply(link_msg)

@app.on_message(filters.command("set_link"))
async def set_link_command(client: Client, message: Message):
    """Handle the /set_link command to set community link with custom name"""
    user_id = message.from_user.id
    
    # Check if user is authorized and is admin
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
        
    if not is_admin(str(user_id)):
        await message.reply("🚫 **Access Denied**\n\nOnly admins can update the community link.")
        return
    
    # Check command format
    command_parts = message.text.split(maxsplit=2)
    
    # Check if command has the right format
    if len(command_parts) < 3:
        await message.reply(
            "⚠️ **Invalid Format** ⚠️\n\n"
            "Please use the format:\n"
            "`/set_link [url] [name]`\n\n"
            "Example:\n"
            "`/set_link https://t.me/mychannel My Channel`"
        )
        return
        
    new_link = command_parts[1].strip()
    link_name = command_parts[2].strip()
    
    # Validate link format
    if not new_link.startswith("http"):
        new_link = "https://" + new_link
    
    # Update the link in the database with both URL and name
    db.update_community_link(new_link, link_name)
    
    await message.reply(
        f"✅ **Community Link Updated** ✅\n\n"
        f"The community link has been updated to:\n"
        f"URL: {new_link}\n"
        f"Name: {link_name}\n\n"
        f"Users will see it as: [{link_name}]({new_link})"
    )
    
    # For regular users or admins without a new link, show the current link
    link_msg = utils.get_link_message()
    await message.reply(link_msg)

@app.on_message(filters.command("logout"))
async def logout_command(client: Client, message: Message):
    """Handle the /logout command to exit the bot"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    # Create confirmation keyboard
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Log Me Out", callback_data="confirm_logout")],
        [InlineKeyboardButton("❌ No, Stay Logged In", callback_data="cancel_logout")]
    ])
    
    # Send confirmation message
    await message.reply(
        "⚠️ **Logout Confirmation** ⚠️\n\n"
        "Are you sure you want to log out?\n\n"
        "This will:\n"
        "• Remove your user data from our database\n"
        "• Require a new access key to use the bot again\n"
        "• Delete your sync history\n\n"
        "Please confirm your choice:",
        reply_markup=keyboard
    )

@app.on_message(filters.command("admin"))
async def admin_command(client: Client, message: Message):
    """Handle the /admin command to promote a user to admin"""
    user_id = message.from_user.id
    
    # Check if user is admin
    if not is_admin(user_id):
        await message.reply("🚫 This command is only available to admins.")
        return
    
    # Check command format
    command_parts = message.text.split()
    if len(command_parts) != 2:
        await message.reply(
            "❌ **Invalid command format**\n\n"
            "👉 Use: /admin <user_id>\n"
            "Example: /admin 123456789"
        )
        return
    
    # Get target user ID
    target_user_id = command_parts[1]
    
    # Check if user exists
    if not db.user_exists(target_user_id):
        await message.reply(f"❌ User {target_user_id} does not exist.")
        return
    
    # Promote user to admin
    success = db.promote_user(target_user_id)
    
    # Send confirmation message
    admin_msg = utils.get_admin_message(target_user_id, success)
    await message.reply(admin_msg)

@app.on_message(filters.command("demote"))
async def demote_command(client: Client, message: Message):
    """Handle the /demote command to demote an admin to regular user"""
    user_id = message.from_user.id
    
    # Check if user is admin
    if not is_admin(user_id):
        await message.reply("🚫 This command is only available to admins.")
        return
    
    # Check command format
    command_parts = message.text.split()
    if len(command_parts) != 2:
        await message.reply(
            "❌ **Invalid command format**\n\n"
            "👉 Use: /demote <user_id>\n"
            "Example: /demote 123456789"
        )
        return
    
    # Get target user ID
    target_user_id = command_parts[1]
    
    # Check if user exists
    if not db.user_exists(target_user_id):
        await message.reply(f"❌ User {target_user_id} does not exist.")
        return
    
    # Demote admin to regular user
    success = db.demote_user(target_user_id)
    
    # Send confirmation message
    demote_msg = utils.get_demote_message(target_user_id, success)
    await message.reply(demote_msg)

@app.on_message(filters.command("ghost"))
async def ghost_command(client: Client, message: Message):
    """Handle the /ghost command to hide a user from top users list"""
    user_id = message.from_user.id
    
    # Check if user is admin
    if not is_admin(user_id):
        await message.reply("🚫 This command is only available to admins.")
        return
    
    # Check command format
    command_parts = message.text.split()
    if len(command_parts) != 2:
        await message.reply(
            "❌ **Invalid command format**\n\n"
            "👉 Use: /ghost <user_id>\n"
            "Example: /ghost 123456789"
        )
        return
    
    # Get target user ID
    target_user_id = command_parts[1]
    
    # Check if user exists
    if not db.user_exists(target_user_id):
        await message.reply(f"❌ User {target_user_id} does not exist.")
        return
    
    # Ghost user
    success = db.ghost_user(target_user_id)
    
    # Send confirmation message
    ghost_msg = utils.get_ghost_message(target_user_id, success)
    await message.reply(ghost_msg)

@app.on_message(filters.command("unghost"))
async def unghost_command(client: Client, message: Message):
    """Handle the /unghost command to make a user visible in top users list"""
    user_id = message.from_user.id
    
    # Check if user is admin
    if not is_admin(user_id):
        await message.reply("🚫 This command is only available to admins.")
        return
    
    # Check command format
    command_parts = message.text.split()
    if len(command_parts) != 2:
        await message.reply(
            "❌ **Invalid command format**\n\n"
            "👉 Use: /unghost <user_id>\n"
            "Example: /unghost 123456789"
        )
        return
    
    # Get target user ID
    target_user_id = command_parts[1]
    
    # Check if user exists
    if not db.user_exists(target_user_id):
        await message.reply(f"❌ User {target_user_id} does not exist.")
        return
    
    # Unghost user
    success = db.unghost_user(target_user_id)
    
    # Send confirmation message
    unghost_msg = utils.get_unghost_message(target_user_id, success)
    await message.reply(unghost_msg)

@app.on_message(filters.command("pin"))
async def pin_command(client: Client, message: Message):
    """Handle the /pin command to pin a message and store it for all users"""
    user_id = message.from_user.id
    
    # Check if user is admin
    if not is_admin(user_id):
        await message.reply("🚫 This command is only available to admins.")
        return
    
    # Check if message is a reply
    if message.reply_to_message:
        # Pin the replied message and store it in database
        try:
            # Try to pin the message
            await message.reply_to_message.pin(disable_notification=False)
            # Store the pinned message in database
            pin_text = message.reply_to_message.text or message.reply_to_message.caption or "[Media Message]"
            db.update_pinned_message(pin_text, message.reply_to_message.id)
            await message.reply(utils.get_pin_message(True))
        except ChatAdminRequired:
            # Specific error for admin permission issues
            logger.error("Bot doesn't have pin message permission")
            await message.reply("❌ Failed to pin message. Make sure the bot has pin message permissions.")
        except Exception as e:
            # General error handling
            logger.error(f"Error pinning message: {str(e)}")
            # Store the pinned message in database anyway
            pin_text = message.reply_to_message.text or message.reply_to_message.caption or "[Media Message]"
            db.update_pinned_message(pin_text, message.reply_to_message.id)
            await message.reply("✅ Message saved to database but couldn't be pinned. Using internal pin function instead.")
    else:
        # Check if there's a message to pin
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) > 1:
            # Send and pin a new message with the provided text
            pin_text = command_parts[1]
            try:
                pin_msg = await message.reply(pin_text)
                await pin_msg.pin(disable_notification=False)
                # Store the pinned message in database
                db.update_pinned_message(pin_text, pin_msg.id)
                await message.reply(utils.get_pin_message(True))
            except ChatAdminRequired:
                # Specific error for admin permission issues
                logger.error("Bot doesn't have pin message permission")
                # Store the pinned message in database anyway
                db.update_pinned_message(pin_text, pin_msg.id)
                await message.reply("✅ Message saved to database but couldn't be pinned. Using internal pin function instead.")
            except Exception as e:
                logger.error(f"Error pinning message: {str(e)}")
                # Store the pinned message in database anyway
                db.update_pinned_message(pin_text, pin_msg.id)
                await message.reply("✅ Message saved to database but couldn't be pinned. Using internal pin function instead.")
        else:
            # If no message provided, show the current pinned message if it exists
            pinned_message = db.get_pinned_message()
            if pinned_message:
                await message.reply(
                    f"📌 **Current Pinned Message** 📌\n\n"
                    f"{pinned_message['text']}\n\n"
                    f"To set a new pinned message:\n"
                    f"👉 Use: /pin <message> to pin a new message\n"
                    f"👉 Or reply to a message with /pin to pin it"
                )
            else:
                # No message to pin
                await message.reply(
                    "❌ **No pinned message found**\n\n"
                    "👉 Use: /pin <message> to pin a new message\n"
                    "👉 Or reply to a message with /pin to pin it"
                )

@app.on_message(filters.command("image"))
async def image_command(client: Client, message: Message):
    """Handle the /image command for admins to upload an image"""
    user_id = message.from_user.id
    
    # Check if user is admin
    if not is_admin(user_id):
        await message.reply("🚫 This command is only available to admins.")
        return
    
    # Check if message has a photo
    if message.photo:
        # Process the photo
        photo = message.photo
        file_id = photo.file_id
        file_size = photo.file_size
        
        # Download the photo
        download_path = os.path.join(MEDIA_DIR, f"admin_image_{int(time.time())}.jpg")
        await client.download_media(message, file_name=download_path)
        
        # Add to database
        media_id = db.add_media(
            user_id=str(user_id),
            file_id=file_id,
            file_path=download_path,
            file_size=file_size,
            media_type="photo",
            caption=message.caption
        )
        
        await message.reply(f"✅ Image uploaded successfully! Media ID: {media_id}")
    else:
        # No photo attached
        await message.reply(
            "❌ **No image attached**\n\n"
            "👉 Use: /image with an image attachment\n"
            "You can also add a caption to the image"
        )
        return
    


# Admin commands
@app.on_message(filters.command("getkey") & filters.create(is_admin_filter))
async def getkey_command(client: Client, message: Message):
    """Generate a new access key"""
    # Parse command arguments
    command_parts = message.text.split()
    
    # Default values
    uses = 1
    key_type = "normal"
    
    # Parse uses if provided
    if len(command_parts) > 1 and command_parts[1].isdigit():
        uses = int(command_parts[1])
    
    # Parse key type if provided
    if len(command_parts) > 2 and command_parts[2].lower() == "premium":
        key_type = "premium"
    
    # Generate key
    key = db.create_key(key_type, uses)
    
    # Create custom join link with key embedded
    bot_username = (await app.get_me()).username
    join_link = f"https://t.me/{bot_username}?start={key}"
    
    await message.reply(
        f"🔑 **New Access Key Generated** 🔑\n\n"
        f"🔐 Key: `{key}`\n"
        f"📋 Type: {key_type.upper()}\n"
        f"🔢 Max Uses: {uses}\n\n"
        f"📱 **Join Link:**\n`{join_link}`\n\n"
        f"⏱️ Key valid for 24 hours\n"
        f"🌟 Share with trusted users only"
    )

@app.on_message(filters.command("ban") & filters.create(is_admin_filter))
async def ban_command(client: Client, message: Message):
    """Ban a user"""
    # Parse command arguments
    command_parts = message.text.split()
    
    if len(command_parts) < 2:
        await message.reply("🚫 **Ban Error** 🚫\n\n📝 Please provide a user ID to ban.\n💡 Example: /ban 123456789")
        return
    
    try:
        user_id = int(command_parts[1])
    except ValueError:
        await message.reply("🚫 **Ban Error** 🚫\n\n⚠️ Invalid user ID format.\n📋 Please provide a numeric ID.\n💡 Example: /ban 123456789")
        return
    
    # Ban user
    if db.ban_user(user_id):
        await message.reply(f"🚫 **User Banned** 🚫\n\n✅ User {user_id} has been successfully banned.\n🔒 This user can no longer access the Media Vault.")
    else:
        await message.reply(f"⚠️ **Ban Failed** ⚠️\n\n❌ Could not ban user {user_id}.\n📋 Possible reasons:\n• User may not exist\n• User is already banned")

@app.on_message(filters.command("unban") & filters.create(is_admin_filter))
async def unban_command(client: Client, message: Message):
    """Unban a user"""
    # Parse command arguments
    command_parts = message.text.split()
    
    if len(command_parts) < 2:
        await message.reply("🔓 **Unban Error** 🔓\n\n📝 Please provide a user ID to unban.\n💡 Example: /unban 123456789")
        return
    
    try:
        user_id = int(command_parts[1])
    except ValueError:
        await message.reply("🔓 **Unban Error** 🔓\n\n⚠️ Invalid user ID format.\n📋 Please provide a numeric ID.\n💡 Example: /unban 123456789")
        return
    
    # Unban user
    if db.unban_user(user_id):
        await message.reply(f"🔓 **User Unbanned** 🔓\n\n✅ User {user_id} has been successfully unbanned.\n🔑 This user can now access the Media Vault again.")
    else:
        await message.reply(f"⚠️ **Unban Failed** ⚠️\n\n❌ Could not unban user {user_id}.\n📋 Possible reasons:\n• User may not exist\n• User is not currently banned")

@app.on_message(filters.command("upgrade") & filters.create(is_admin_filter))
async def upgrade_command(client: Client, message: Message):
    """Upgrade a user to premium"""
    # Parse command arguments
    command_parts = message.text.split()
    
    if len(command_parts) < 2:
        await message.reply("💎 **Upgrade Error** 💎\n\n📝 Please provide a user ID to upgrade to premium.\n💡 Example: /upgrade 123456789")
        return
    
    try:
        user_id = int(command_parts[1])
    except ValueError:
        await message.reply("💎 **Upgrade Error** 💎\n\n⚠️ Invalid user ID format.\n📋 Please provide a numeric ID.\n💡 Example: /upgrade 123456789")
        return
    
    # Upgrade user
    if db.upgrade_user(user_id):
        await message.reply(f"💎 **User Upgraded** 💎\n\n✅ User {user_id} has been successfully upgraded to premium.\n🌟 They now have access to all premium features.\n📱 User has been notified of their new status.")
        
        # Notify user
        try:
            user = db.get_user(str(user_id))
            await client.send_message(
                user_id,
                "🎉 **Congratulations!** 🎉\n\n"
                "💎 You have been upgraded to **PREMIUM** status! 💎\n\n"
                "✨ Your Premium Benefits:\n"
                "• 🌟 Always active status\n"
                "• 🔄 Unlimited media sync\n"
                "• 📊 Premium badge on your uploads\n"
                "• ⏰ No activity requirements\n"
                "• 🔔 Priority support\n"
                "• 🚀 Faster download speeds\n\n"
                "🎁 Enjoy your premium experience in the Media Vault!"
            )
        except Exception as e:
            logger.error(f"Error notifying user {user_id} about upgrade: {str(e)}")
    else:
        await message.reply(f"⚠️ **Upgrade Failed** ⚠️\n\n❌ Could not upgrade user {user_id}.\n📋 Possible reasons:\n• User may not exist\n• User is already a premium member")

@app.on_message(filters.command("reset") & filters.create(is_admin_filter))
async def reset_command(client: Client, message: Message):
    """Reset a user's activity timer"""
    # Parse command arguments
    command_parts = message.text.split()
    
    if len(command_parts) < 2:
        await message.reply("⏱️ **Reset Error** ⏱️\n\n📝 Please provide a user ID to reset activity timer.\n💡 Example: /reset 123456789")
        return
    
    try:
        user_id = int(command_parts[1])
    except ValueError:
        await message.reply("⏱️ **Reset Error** ⏱️\n\n⚠️ Invalid user ID format.\n📋 Please provide a numeric ID.\n💡 Example: /reset 123456789")
        return
    
    # Reset activity
    if db.reset_activity(user_id):
        # Make user active if they have enough uploads
        user = db.get_user(str(user_id))
        if user["uploads"] >= REQUIRED_UPLOADS and not user["active"] and not user["premium"]:
            db.update_user(str(user_id), {"active": True})
            db.stats["active_users"] += 1
            db._save_json(db.stats_file, db.stats)
        
        await message.reply(f"⏱️ **Activity Reset** ⏱️\n\n✅ User {user_id}'s activity timer has been successfully reset.\n🔄 Their account status has been refreshed.\n🌟 They can now continue using the Media Vault.")
    else:
        await message.reply(f"⚠️ **Reset Failed** ⚠️\n\n❌ Could not reset user {user_id}'s activity timer.\n📋 Possible reason:\n• User may not exist in the database")

@app.on_message(filters.command("status") & filters.create(is_admin_filter))
async def status_command(client: Client, message: Message):
    """Show bot status"""
    # Get stats
    stats = db.get_stats()
    
    # Count files in media directory
    media_count = len([f for f in os.listdir(MEDIA_DIR) if os.path.isfile(os.path.join(MEDIA_DIR, f))])
    
    # Calculate total size of media directory
    total_size = sum(os.path.getsize(os.path.join(MEDIA_DIR, f)) for f in os.listdir(MEDIA_DIR) if os.path.isfile(os.path.join(MEDIA_DIR, f)))
    
    # Calculate uptime
    uptime_seconds = time.time() - BOT_START_TIME
    
    # Get reported media count
    reported_count = db.get_reported_media_count()
    
    # Get active keys count
    active_keys = 0
    for key, key_data in db.keys.items():
        if not key_data.get("disabled", False) and (key_data.get("max_uses", 0) == 0 or key_data.get("uses", 0) < key_data.get("max_uses", 0)):
            active_keys += 1
    
    await message.reply(
        f"📊 **Media Vault Status** 📊\n\n"
        f"🤖 Bot Username: @{BOT_USERNAME}\n"
        f"👤 Owner: @{OWNER_USERNAME}\n\n"
        f"⏱️ Uptime: {utils.format_uptime(uptime_seconds)}\n"
        f"👥 Total Users: {stats['total_users']}\n"
        f"💎 Premium Users: {stats['premium_users']}\n"
        f"✅ Active Users: {stats['active_users']}\n"
        f"🚫 Banned Users: {stats['banned_users']}\n\n"
        f"📁 Media Stats:\n"
        f"   • 🗃️ Total Files: {stats['total_media_count']}\n"
        f"   • 🚨 Reported Content: {reported_count}\n"
        f"   • 💾 Media Storage: {utils.format_size(total_size)}\n"
        f"   • 📊 Database Size: {utils.format_size(stats['database_size'])}\n\n"
        f"🔑 Access Keys:\n"
        f"   • 🔢 Total Generated: {stats['keys_generated']}\n"
        f"   • ✅ Currently Active: {active_keys}\n\n"
        f"🔧 System: Hybrid Mode (MTProto + Bot API)\n"
        f"🔄 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🌟 Media Vault Network - Premium Media Sharing"
    )

@app.on_message(filters.command("disablekey") & filters.create(is_admin_filter))
async def disablekey_command(client: Client, message: Message):
    """Disable an access key"""
    # Parse command arguments
    command_parts = message.text.split()
    
    if len(command_parts) < 2:
        await message.reply("🔒 **Disable Key Error** 🔒\n\n📝 Please provide a key to disable.\n💡 Example: /disablekey ABC123DEF456")
        return
    
    key = command_parts[1].strip().upper()
    
    # Disable key
    if db.disable_key(key):
        await message.reply(f"🔒 **Key Disabled** 🔒\n\n✅ Key {key} has been successfully disabled.\n🚫 This key can no longer be used for registration.\n🔐 Any existing users will not be affected.")
    else:
        await message.reply(f"⚠️ **Disable Failed** ⚠️\n\n❌ Could not disable key {key}.\n📋 Possible reasons:\n• Key may not exist in the database\n• Key may already be disabled")

@app.on_message(filters.command("broadcast") & filters.create(is_admin_filter))
async def broadcast_command(client: Client, message: Message):
    """Broadcast a message to all users"""
    # Get broadcast message
    broadcast_text = message.text.replace("/broadcast", "", 1).strip()
    
    if not broadcast_text:
        await message.reply("📣 **Broadcast Error** 📣\n\n📝 Please provide a message to broadcast.\n💡 Example: /broadcast Hello everyone! Important update...")
        return
    
    # Add broadcast header
    broadcast_text = f"📣 **MEDIA VAULT ANNOUNCEMENT** 📣\n\n{broadcast_text}\n\n🔔 From: Media Vault Administration"
    
    # Send confirmation
    await message.reply(f"📣 **Broadcast Initiated** 📣\n\n🔄 Broadcasting message to all users...\n⏳ This may take some time depending on the number of users.\n📱 Users will receive a notification.")
    
    # Send to all users
    success_count = 0
    fail_count = 0
    
    for user_id in db.users:
        # Skip banned users
        if db.users[user_id]["banned"]:
            continue
        
        try:
            await client.send_message(int(user_id), broadcast_text)
            success_count += 1
            # Add delay to avoid flood limits
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error sending broadcast to user {user_id}: {str(e)}")
            fail_count += 1
    
    await message.reply(
        f"📣 **Broadcast Complete** 📣\n\n"
        f"✅ Successfully delivered to: {success_count} users\n"
        f"❌ Failed to deliver to: {fail_count} users\n\n"
        f"📊 Success rate: {success_count/(success_count+fail_count)*100:.1f}%\n"
        f"⏱️ Completed at: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🔔 Users have been notified of your announcement."
    )

@app.on_message(filters.command("delete") & filters.create(is_admin_filter))
async def delete_command(client: Client, message: Message):
    """Delete a media file"""
    # Parse command arguments
    command_parts = message.text.split()
    
    if len(command_parts) < 2:
        await message.reply("🗑️ **Delete Error** 🗑️\n\n📝 Please provide a media ID to delete.\n💡 Example: /delete 123456789_987654")
        return
    
    media_id = command_parts[1].strip()
    
    # Delete media
    if db.delete_media(media_id):
        await message.reply(f"🗑️ **Media Deleted** 🗑️\n\n✅ Media {media_id} has been successfully deleted.\n🧹 The file has been removed from the Media Vault.\n📊 Media count has been updated.")
    else:
        await message.reply(f"⚠️ **Delete Failed** ⚠️\n\n❌ Could not delete media {media_id}.\n📋 Possible reasons:\n• Media ID may not exist\n• Media file may have already been removed")

# Media processing worker function for a specific user
async def media_processor_worker(user_id):
    """Worker function to process media from the queue for a specific user"""
    str_user_id = str(user_id)
    user_media_processors[str_user_id] = True
    
    # Track uploads for this user
    user_uploads = {
        "client": None,
        "count": 0,
        "last_time": time.time()
    }
    
    try:
        while True:
            # Check if queue exists for this user
            if str_user_id not in user_media_queues or user_media_queues[str_user_id].empty():
                # No more items in queue, exit the worker
                break
                
            # Get the next media item from the user's queue
            media_item = await user_media_queues[str_user_id].get()
            
            try:
                # Process the media item
                client = media_item["client"]
                message = media_item["message"]
                progress_msg = media_item["progress_msg"]
                
                # Store client for notifications
                user_uploads["client"] = client
                
                # Process the media
                await process_media_item(client, message, user_id, progress_msg)
                
                # Track this upload
                user_uploads["count"] += 1
                user_uploads["last_time"] = time.time()
                
                # Wait for 2 seconds before processing the next item
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error processing media from queue for user {user_id}: {str(e)}")
            finally:
                # Mark the task as done
                user_media_queues[str_user_id].task_done()
    except Exception as e:
        logger.error(f"Media processor worker error for user {user_id}: {str(e)}")
    finally:
        # Send completion notification if there were uploads
        if user_uploads["count"] > 0 and user_uploads["client"] is not None:
            try:
                await user_uploads["client"].send_message(
                    int(user_id),
                    f"Your Media Sharing Completed Enjoy Media"
                )
            except Exception as notify_error:
                logger.error(f"Error sending completion notification to user {user_id}: {str(notify_error)}")
        
        # Mark processor as not running
        user_media_processors[str_user_id] = False

@app.on_message(filters.command("search") & filters.create(is_admin_filter))
async def search_command(client: Client, message: Message):
    """Search for users by their alias name"""
    # Parse command arguments
    search_query = message.text.replace("/search", "", 1).strip()
    
    if not search_query:
        await message.reply(
            "🔍 **Search Error** 🔍\n\n"
            "📝 Please provide an alias name to search for.\n"
            "💡 Example: /search Drone Echo"
        )
        return
    
    # Search for users with matching alias
    found_users = []
    for user_id, user_data in db.users.items():
        if search_query.lower() in user_data["alias"].lower():
            found_users.append((user_id, user_data))
    
    if not found_users:
        await message.reply(
            f"🔍 **Search Results** 🔍\n\n"
            f"❌ No users found with alias containing '{search_query}'."
        )
        return
    
    # Format search results
    results_message = f"🔍 **Search Results for '{search_query}'** 🔍\n\n"
    
    for user_id, user_data in found_users:
        username = user_data.get("username", "No username")
        first_name = user_data.get("first_name", "Unknown")
        alias = user_data.get("alias", "No alias")
        premium = "Yes" if user_data.get("premium", False) else "No"
        
        results_message += (
            f"🆕 **User Information** \n\n"
            f"👤 User: {first_name} (@{username})\n"
            f"🆔 ID: {user_id}\n"
            f"🔑 Key: {user_data.get('access_key', 'Unknown')}\n"
            f"🎭 Alias: {alias}\n"
            f"✨ Premium: {premium}\n\n"
        )
    
    await message.reply(results_message)

@app.on_message(filters.command("showpin"))
async def showpin_command(client: Client, message: Message):
    """Handle the /showpin command to show the pinned message"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    # Get the pinned message from database
    pinned_message = db.get_pinned_message()
    
    if pinned_message:
        await message.reply(
            f"📌 **Pinned Message** 📌\n\n"
            f"{pinned_message['text']}"
        )
        # Update the timestamp when user last saw the pinned message
        db.update_user_pin_view(user_id)
    else:
        await message.reply("📌 No pinned message found.")

# Handle unknown commands
@app.on_message(filters.private & filters.command([]) & ~filters.command(["start", "help", "mystats", "syncmedia", "admin", "top", "link", "logout", "report", "getkey", "broadcast", "pin", "ban", "unban", "ghost", "unghost", "search", "showpin"]))
async def unknown_command(client: Client, message: Message):
    """Handle unknown commands by directing users to /help"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    await message.reply(
        "❓ **Unknown Command** ❓\n\n"
        "The command you entered is not recognized.\n"
        "Please type /help to see a list of available commands."
    )

# Anonymous chat message handling
@app.on_message(filters.private & filters.text & ~filters.via_bot & ~filters.forwarded)
async def handle_text_message(client: Client, message: Message):
    """Handle private text messages for anonymous chat"""
    user_id = message.from_user.id
    
    # Check if user is authorized
    if not is_authorized(str(user_id)):
        await utils.handle_unauthorized_access(message)
        return
    
    # Update user activity (marks them as online)
    db.update_user_activity(str(user_id))
    
    # Get user data
    user = db.get_user(str(user_id))
    
    # Check if user is active or premium
    if not user["active"] and not user["premium"]:
        await message.reply(
            "❌ **Media Not Shared** ❌\n\n"
            "You are currently inactive. Your media will be stored but not shared with other users.\n"
            "To become active again, please upload media regularly or upgrade to premium.\n"
            "You can still receive broadcast messages from admins."
        )
    
    # Filter content for NSFW and links
    text = message.text
    
    # Check for any links or usernames in text messages
    contains_link = any(word.startswith(('http://', 'https://', 'www.')) or 't.me' in word for word in text.split())
    contains_username = '@' in text
    
    if contains_link or contains_username:
        await message.reply(
            "⚠️ **Message Not Sent** ⚠️\n\n"
            "Your message contains a link or username, which is not allowed in text messages.\n"
            "Links are only allowed in media captions."
        )
        return
    
    # Enhanced NSFW word filter
    nsfw_words = ['porn', 'sex', 'xxx', 'nude', 'naked', 'fuck', 'dick', 'pussy', 'ass', 'boobs', 'tits', 'anal', 'cum', 'blowjob', 'bdsm', 'hentai', 'fetish', 'orgasm', 'masturbate', 'dildo', 'vibrator', 'escort', 'hooker', 'whore', 'slut']
    if any(word.lower() in text.lower() for word in nsfw_words):
        await message.reply(
            "⚠️ **Message Not Sent** ⚠️\n\n"
            "Your message contains inappropriate content that is not allowed in the anonymous chat.\n"
            "Please keep conversations appropriate."
        )
        return
    
    # If user is inactive and not premium, don't share their messages with others
    if not user["active"] and not user["premium"]:
        return
        
    # Get all users with active plans or premium, not just online users
    active_users = {uid: user for uid, user in db.users.items() 
                   if (user.get("active", False) or user.get("premium", False)) and not user.get("banned", False)}
    
    # Broadcast message to all active users except sender
    sent_count = 0
    for active_id, active_user in active_users.items():
        if active_id != str(user_id):  # Don't send to self
            try:
                await client.send_message(
                    int(active_id),
                    f"👤 **{user['alias']}** says:\n\n{text}"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Error sending message to user {active_id}: {str(e)}")
    
    # Don't send confirmation to sender
    pass

# Function to share user's media with active users when they become active
async def share_user_media_with_active_users(client: Client, user_id):
    """Share all media from a user who just became active with other active users"""
    str_user_id = str(user_id)
    user = db.get_user(str_user_id)
    
    # Get all active users except the current user
    active_users = {uid: user_data for uid, user_data in db.users.items() 
                   if (user_data.get("active", False) or user_data.get("premium", False)) 
                   and not user_data.get("banned", False) and uid != str_user_id}
    
    # Get all media from this user
    user_media_ids = user.get("media_ids", [])
    
    # Share each media with active users
    for media_id in user_media_ids:
        if media_id in db.media:
            media_data = db.media[media_id]
            file_id = media_data.get("file_id")
            media_type = media_data.get("media_type")
            
            # Only share if we have the necessary data
            if file_id and media_type:
                # Prepare caption with only the alias name with embedded bot link
                new_caption = f"Shared by: <a href=\"https://telegram.me/SIN_CITY_C_BOT\">{user['alias']}</a>"
                
                # Import ParseMode enum
                from pyrogram import enums
                
                # Share with each active user
                for active_id, active_user in active_users.items():
                    try:
                        # Check if user has synced media limit (for non-premium users)
                        if not active_user.get("premium", False):
                            # Get count of synced media for this user
                            synced_media_count = len(active_user.get("synced_media", []))
                            
                            # If user has reached the limit of 30 media items, skip
                            if synced_media_count >= 30:
                                continue
                        
                        # Send media to active user
                        await client.send_cached_media(
                            chat_id=int(active_id),
                            file_id=file_id,
                            caption=new_caption,
                            parse_mode=enums.ParseMode.HTML
                        )
                        
                        # Add this media to user's synced media list for tracking limits
                        if not active_user.get("premium", False):
                            # Mark media as synced for this user
                            db.mark_media_synced(active_id, media_id)
                    except Exception as e:
                        logger.error(f"Error sharing media {media_id} with user {active_id}: {str(e)}")

# Media handling for anonymous chat
@app.on_message(filters.private & (filters.video | filters.document | filters.photo | filters.animation))
async def handle_media(client: Client, message: Message):
    """Handle incoming media files up to 2GB with concurrent processing support"""
    user_id = message.from_user.id
    str_user_id = str(user_id)
    
    # Check if user is authorized
    if not is_authorized(str_user_id):
        await utils.handle_unauthorized_access(message)
        return
    
    # Update user activity (marks them as online)
    db.update_user_activity(str_user_id)
    
    # Get user data
    user = db.get_user(str_user_id)
    
    # Check if this is a forwarded message
    is_forwarded = message.forward_date is not None
    
    # Don't show any processing message to users
    # Media will be processed in background silently
    # Use a dummy message object instead of sending an empty message
    progress_msg = None
    
    # Create a queue for this user if it doesn't exist
    if str_user_id not in user_media_queues:
        user_media_queues[str_user_id] = Queue()
    
    # Add media to user's queue
    await user_media_queues[str_user_id].put({
        "client": client,
        "message": message,
        "progress_msg": progress_msg
    })
    
    # Start a processor for this user if not already running
    if str_user_id not in user_media_processors or not user_media_processors[str_user_id]:
        asyncio.create_task(media_processor_worker(user_id))
    
    # Count media in queue as installed so user doesn't have to wait
    # This is done by immediately marking the media as processed for the user
    # The actual download will happen in the background
    
    # If user is inactive and not premium, but the message is forwarded, count it towards activity
    # but don't share with others until they become active
    if not user["active"] and not user["premium"]:
        # If it's not a forwarded message, return immediately
        if not is_forwarded:
            return
        
        # For forwarded media from inactive users, immediately count it towards activity
        # without waiting for download to complete
        # Get media type and file_id
        media_type = message.media.value
        file_id = getattr(message, media_type).file_id
        
        # Get file_unique_id based on media type
        if media_type == "photo":
            # For photos, use the biggest size's file_unique_id
            file_unique_id = message.photo.file_unique_id
        else:
            # For videos/documents/audio, use their own file_unique_id
            file_unique_id = getattr(message, media_type).file_unique_id
        
        # Clean caption
        caption = utils.clean_caption(message.caption)
        
        # Add to database immediately without waiting for download
        # This will count towards user's activity requirement
        media_id = db.add_media_instant(str(user_id), file_id, None, 0, media_type, caption, file_unique_id)
        
        # Check if user became active after this media count
        user = db.get_user(str(user_id))
        if user["uploads"] >= REQUIRED_UPLOADS and not user["premium"] and user["active"]:
            # User just became active
            # Now share all their previously forwarded media with active users
            await share_user_media_with_active_users(client, user_id)
            # Send activation message to user
            await message.reply(utils.get_activation_message())
        
        # Still add to queue for actual download in background
        # but return after to prevent immediate sharing
        
        # Return after the media is added to the queue to prevent sharing until they're active
        # The media will be processed in the background by the media_processor_worker
        return

    # Check caption for NSFW content and links if present, or if it's a forwarded message
    if message.caption or is_forwarded:
        if message.caption:
            caption = message.caption
            
            # Check for t.me links and usernames, but allow other links in all media
            contains_tme_link = any('t.me' in word for word in caption.split())
            contains_username = '@' in caption
            
            if contains_tme_link or contains_username:
                # For forwarded media, remove links instead of blocking
                if is_forwarded:
                    # Continue processing but remove the caption
                    message.caption = None
                else:
                    await message.reply(
                        "⚠️ **Media Not Sent** ⚠️\n\n"
                        "Your media caption contains a t.me link or username, which is not allowed in the anonymous chat.\n"
                        "Please send media without t.me links or usernames in the caption. Regular links are allowed."
                    )
                    return
            
            # Enhanced NSFW word filter
            nsfw_words = ['porn', 'sex', 'xxx', 'nude', 'naked', 'fuck', 'dick', 'pussy', 'ass', 'boobs', 'tits', 'anal', 'cum', 'blowjob', 'bdsm', 'hentai', 'fetish', 'orgasm', 'masturbate', 'dildo', 'vibrator', 'escort', 'hooker', 'whore', 'slut']
            if any(word.lower() in caption.lower() for word in nsfw_words):
                # For forwarded media, remove NSFW content instead of blocking
                if is_forwarded:
                    # Continue processing but remove the caption
                    message.caption = None
                else:
                    await message.reply(
                        "⚠️ **Media Not Sent** ⚠️\n\n"
                        "Your media caption contains inappropriate content that is not allowed in the anonymous chat.\n"
                        "Please keep conversations appropriate."
                    )
                    return
        
        # Get all users with active plans or premium, not just online users
        active_users = {uid: user for uid, user in db.users.items() 
                       if (user.get("active", False) or user.get("premium", False)) and not user.get("banned", False)}
        
        # Don't send acknowledgment to the user
        pass
        
        # Broadcast media to all active users except sender
        sent_count = 0
        for active_id, active_user in active_users.items():
            if active_id != str(user_id):  # Don't send to self
                try:
                    # Check if user has synced media limit (for non-premium users)
                    # Premium users have no limit
                    if not active_user.get("premium", False):
                        # Get count of synced media for this user
                        synced_media_count = len(active_user.get("synced_media", []))
                        
                        # If user has reached the limit of 30 media items, skip and send notification
                        if synced_media_count >= 30:
                            try:
                                # Only send the notification once per user
                                if not active_user.get("limit_notified", False):
                                    await client.send_message(
                                        int(active_id),
                                        "You missed this media. Upgrade to premium so you can't miss out!"
                                    )
                                    # Mark user as notified
                                    db.update_user(active_id, {"limit_notified": True})
                            except Exception as notify_error:
                                logger.error(f"Error sending limit notification: {str(notify_error)}")
                            continue
                    
                    # Forward the media with modified caption
                    if message.media:
                        # Get the appropriate media object based on media type
                        media_type = message.media.value
                        media_obj = getattr(message, media_type)
                        
                        # Prepare caption with only the alias name with embedded bot link
                        new_caption = f"Shared by: <a href=\"https://telegram.me/SIN_CITY_C_BOT\">{user['alias']}</a>"
                        # Don't append the original caption as per user's request
                        
                        # Import ParseMode enum
                        from pyrogram import enums
                        
                        # Send media with new caption
                        await client.send_cached_media(
                            chat_id=int(active_id),
                            file_id=media_obj.file_id,
                            caption=new_caption,
                            parse_mode=enums.ParseMode.HTML
                        )
                        sent_count += 1
                        
                        # Add this media to user's synced media list for tracking limits
                        # First, we need to get the media_id for this file_id
                        media_id = None
                        for mid, mdata in db.media.items():
                            if mdata.get("file_id") == media_obj.file_id:
                                media_id = mid
                                break
                        
                        if media_id and not active_user.get("premium", False):
                            # Mark media as synced for this user
                            db.mark_media_synced(active_id, media_id)
                except Exception as e:
                    logger.error(f"Error sending media to user {active_id}: {str(e)}")
        
        # Don't confirm to sender
        pass

async def process_media_item(client: Client, message: Message, user_id, progress_msg):
    """Process a single media item from the queue"""
    try:
        # Determine media type
        media_type = message.media.value
        file_id = getattr(message, media_type).file_id
        file_name = getattr(getattr(message, media_type), "file_name", None)
        
        # Get file_unique_id based on media type
        if media_type == "photo":
            # For photos, use the biggest size's file_unique_id
            file_unique_id = message.photo.file_unique_id
        else:
            # For videos/documents/audio, use their own file_unique_id
            file_unique_id = getattr(message, media_type).file_unique_id
        
        # Clean caption
        caption = utils.clean_caption(message.caption)
        
        # Check if we've already processed this file from this user
        for media_id, media_data in db.media.items():
            if media_data["file_id"] == file_id and media_data["user_id"] == str(user_id):
                # Delete the progress message silently if it exists
                if progress_msg is not None:
                    try:
                        await progress_msg.delete()
                    except Exception:
                        pass
                return
        
        # Check file size (if available)
        file_size = getattr(getattr(message, media_type), "file_size", 0)
        size_mb = file_size / (1024 * 1024) if file_size else 0
        
        # Check if file exceeds maximum size
        if file_size > MAX_FILE_SIZE:
            if progress_msg is not None:
                try:
                    await progress_msg.delete()
                except Exception:
                    pass
            await client.send_message(user_id, f"⚠️ **File Too Large** ⚠️\n\nYour file exceeds the maximum size limit of 2GB.\nPlease upload a smaller file.")
            return
        
        # Log the incoming file
        logger.info(f"Processing media from user {user_id}: {size_mb:.2f} MB, type: {media_type}")
        
        # Don't update progress message - we want to hide the download progress from the user
        # Just delete the initial message if it exists
        if progress_msg is not None:
            try:
                await progress_msg.delete()
            except Exception:
                pass
        start_time = asyncio.get_event_loop().time()
        
        # Generate a unique timestamp to prevent conflicts with concurrent uploads
        timestamp = int(start_time * 1000)  # Millisecond precision
        
        # Custom file name with user ID and unique timestamp to prevent conflicts
        custom_file_name = f"{user_id}_{timestamp}"
        if file_name:
            # Keep original extension if available
            ext = os.path.splitext(file_name)[1]
            if ext:
                custom_file_name += ext
        
        # Create a unique temp file path to avoid conflicts
        temp_file_path = os.path.join(MEDIA_DIR, f"{custom_file_name}.temp")
        final_file_path = os.path.join(MEDIA_DIR, custom_file_name)
        
        # Define progress callback - but don't show progress to user
        async def progress_callback(current, total):
            # We're not showing progress to the user anymore, but we'll keep the callback
            # for internal tracking purposes
            pass
        
        # Download the file without progress updates
        # Use a try-except block with multiple retries for file operations
        max_retries = 3
        retry_count = 0
        download_success = False
        
        # Import file lock mechanism
        from file_lock import media_operation_lock
        
        # Generate a unique operation ID for this download
        operation_id = f"download_{user_id}_{int(start_time * 1000)}"
        
        while retry_count < max_retries and not download_success:
            try:
                # First download to temp file
                download_path = await message.download(
                    file_name=temp_file_path,
                    progress=progress_callback
                )
                
                # Use file lock when renaming to prevent concurrent access issues
                with media_operation_lock(operation_id, "rename"):
                    # Rename temp file to final file
                    if os.path.exists(temp_file_path):
                        # If the final file already exists (unlikely but possible), remove it first
                        if os.path.exists(final_file_path):
                            os.remove(final_file_path)
                        
                        os.rename(temp_file_path, final_file_path)
                        download_path = final_file_path
                        download_success = True
                
            except Exception as e:
                retry_count += 1
                logger.error(f"Download attempt {retry_count} failed: {str(e)}")
                await asyncio.sleep(1)  # Wait before retrying
                
                # If this was the last retry and it failed, raise the exception
                if retry_count >= max_retries:
                    raise
        
        # Calculate download time
        download_time = asyncio.get_event_loop().time() - start_time
        download_speed = file_size / download_time if download_time > 0 else 0
        
        # Check if this media was already added instantly for forwarded media
        existing_media_id = None
        for mid, mdata in db.media.items():
            if mdata.get("file_id") == file_id and mdata.get("user_id") == str(user_id) and mdata.get("pending_download", False):
                existing_media_id = mid
                break
        
        if existing_media_id:
            # Update the existing media entry with the downloaded file path and size
            db.media[existing_media_id]["file_path"] = download_path
            db.media[existing_media_id]["file_size"] = file_size
            db.media[existing_media_id]["pending_download"] = False
            db._save_json(db.media_file, db.media)
            media_id = existing_media_id
        else:
            # Add to database as a new entry
            media_id = db.add_media(str(user_id), file_id, download_path, file_size, media_type, caption, file_unique_id)
        
        # Check if user became active
        user = db.get_user(str(user_id))
        if user["uploads"] >= REQUIRED_UPLOADS and not user["premium"] and not user["active"]:
            # User just became active
            # Now share all their previously forwarded media with active users
            await share_user_media_with_active_users(client, user_id)
            # Send activation message
            await client.send_message(user_id, utils.get_activation_message())
        elif user["uploads"] % REQUIRED_UPLOADS == 0 and not user["premium"] and user["active"]:
            # User has uploaded another 30 media files, but don't send notification
            pass
        
        # Don't send completion message - progress message already deleted
        
        # Send admin notification for large files
        if size_mb > 100 and OWNER_ID:
            await client.send_message(
                OWNER_ID,
                f"📥 **Large File Uploaded** 📥\n\n"
                f"👤 User: {user['alias']} (ID: {user_id})\n"
                f"📁 Size: {utils.format_size(file_size)}\n"
                f"🔢 Media ID: {media_id}\n"
                f"📂 Saved as: {os.path.basename(download_path)}"
            )
        
    except Exception as e:
        error_str = str(e)
        logger.error(f"Error handling media: {error_str}")
        
        # Check if it's a WinError 32 (file access error)
        if "WinError 32" in error_str and "process cannot access the file" in error_str:
            # Don't show the specific error to the user, just a generic message
            await client.send_message(user_id, "❌ Your media is currently being processed. Please try again in a few moments.")
        else:
            # For other errors, show a generic message without the specific error details
            await client.send_message(user_id, "❌ Error processing your media. Please try again later.")
        
        # Clean up any temp files if they exist
        try:
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                # Use file lock for cleanup to prevent concurrent access issues
                from file_lock import media_operation_lock
                with media_operation_lock(f"cleanup_{user_id}_{int(time.time() * 1000)}", "cleanup"):
                    os.remove(temp_file_path)
        except Exception as cleanup_error:
            logger.error(f"Error cleaning up temp file: {str(cleanup_error)}")

# Callback query handler
@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    """Handle callback queries from inline keyboards"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    # Check if user is authorized
    if not is_authorized(str(user_id)) and data != "help":
        await callback_query.answer("You are not authorized to use this bot.", show_alert=True)
        return
    
    # Handle different callback types
    if data == "help":
        # Show help message
        await callback_query.message.delete()
        await help_command(client, callback_query.message)
    
    elif data == "mystats":
        # Show user stats
        await callback_query.message.delete()
        await mystats_command(client, callback_query.message)
    
    elif data == "syncmedia":
        # Start media sync
        await callback_query.message.delete()
        await syncmedia_command(client, callback_query.message)
    
    elif data == "admin" and is_admin(str(user_id)):
        # Show admin panel
        keyboard = utils.get_admin_keyboard()
        await callback_query.message.edit_text(
            "⚙️ **Admin Panel**\n\nSelect an option:",
            reply_markup=keyboard
        )
    
    elif data == "back_to_start":
        # Go back to start menu
        user_data = db.get_user(str(user_id))
        # Explicitly check premium status from database
        is_user_premium = False
        if user_data and "premium" in user_data:
            is_user_premium = user_data["premium"]
        
        welcome_msg = utils.get_welcome_message(
            callback_query.from_user.first_name,
            is_user_premium
        )
        keyboard = utils.get_start_keyboard(str(user_id), is_admin(str(user_id)))
        await callback_query.message.edit_text(welcome_msg, reply_markup=keyboard)
    
    elif data == "genkey" and is_admin(str(user_id)):
        # Generate key dialog
        await callback_query.message.edit_text(
            "🔑 **Generate Key**\n\n"
            "Use the command:\n"
            "`/getkey [uses] [premium]`\n\n"
            "Examples:\n"
            "`/getkey` - Generate normal key with 1 use\n"
            "`/getkey 5` - Generate normal key with 5 uses\n"
            "`/getkey 1 premium` - Generate premium key with 1 use"
        )
    
    elif data == "status" and is_admin(str(user_id)):
        # Show status
        await callback_query.message.delete()
        await status_command(client, callback_query.message)
    
    elif data == "broadcast" and is_admin(str(user_id)):
        # Broadcast dialog
        await callback_query.message.edit_text(
            "📣 **Broadcast Message**\n\n"
            "Use the command:\n"
            "`/broadcast Your message here`\n\n"
            "This will send your message to all users."
        )
    
    elif data.startswith("delete_") and is_admin(str(user_id)):
        # Delete media
        media_id = data.replace("delete_", "")
        if db.delete_media(media_id):
            await callback_query.message.edit_text(f"✅ Media {media_id} has been deleted.")
        else:
            await callback_query.message.edit_text(f"❌ Could not delete media {media_id}.")
    
    elif data.startswith("ban_") and is_admin(str(user_id)):
        # Ban user
        user_to_ban = data.replace("ban_", "")
        if db.ban_user(user_to_ban):
            await callback_query.message.edit_text(f"✅ User {user_to_ban} has been banned.")
        else:
            await callback_query.message.edit_text(f"❌ Could not ban user {user_to_ban}.")
    
    elif data.startswith("dismiss_") and is_admin(str(user_id)):
        # Dismiss report
        report_id = data.replace("dismiss_", "")
        await callback_query.message.edit_text(f"✅ Report for media {report_id} has been dismissed.")
    
    elif data.startswith("remove_") and is_admin(str(user_id)):
        # Remove reported media
        media_id = data.replace("remove_", "")
        if db.delete_media(media_id):
            await callback_query.message.edit_text(
                f"🗑️ **Media Removed** 🗑️\n\n"
                f"The reported content (ID: {media_id}) has been deleted from the system."
            )
        else:
            await callback_query.message.edit_text(
                f"❌ **Error** ❌\n\n"
                f"Could not delete media {media_id}. It may have been already removed."
            )
    
    elif data == "confirm_logout":
        # User confirmed logout
        # Delete user from database
        if db.delete_user(str(user_id)):
            # Send logout message
            logout_msg = utils.get_logout_message()
            await callback_query.message.edit_text(logout_msg)
        else:
            # Error message
            await callback_query.message.edit_text(
                "❌ **Error** ❌\n\n"
                "There was a problem processing your logout request.\n"
                "Please try again later or contact support."
            )
    
    elif data == "cancel_logout":
        # User cancelled logout
        # Send cancellation message
        await callback_query.message.edit_text(
            "✅ **Logout Cancelled** ✅\n\n"
            "You will remain logged in to the Media Vault Bot.\n"
            "Your data and access remain unchanged.\n\n"
            "Thank you for continuing to use our service! 🙏"
        )
        
    elif data == "confirm_sync":
        # User confirmed media sync
        user = db.get_user(str(user_id))
        
        # Check if there's a pending sync operation
        if "pending_sync" not in user or not user["pending_sync"]:
            await callback_query.message.edit_text("❌ No pending media sync found.")
            return
        
        # Check if this is the latest sync operation
        if "sync_operation_id" in user and "sync_request_time" in user:
            # Get the operation ID from the message
            message_text = callback_query.message.text
            operation_id_match = re.search(r"Operation ID: (sync_[\d_]+)", message_text)
            
            if operation_id_match:
                message_operation_id = operation_id_match.group(1)
                # Check if the operation ID in the message matches the latest one in user data
                if message_operation_id != user["sync_operation_id"]:
                    # This is an expired sync operation
                    await callback_query.message.edit_text(
                        "⚠️ **Sync Operation Expired** ⚠️\n\n"
                        "This sync request has expired because a newer request was made.\n"
                        "Please use the latest sync confirmation message or send /syncmedia again."
                    )
                    await callback_query.answer("This sync operation has expired.")
                    return
        
        # Send initial progress message
        progress_msg = await callback_query.message.edit_text(
            "🔄 **Sync Request Confirmed**\n\n"
            "⏳ Your media sync is being processed...\n"
            "⌛ You can continue using other commands while this processes."
        )
        
        # Create a task to process the sync asynchronously
        # This allows the bot to handle other commands while syncing media
        asyncio.create_task(process_confirmed_sync(client, user_id, user, progress_msg))
        
        # Acknowledge the callback query to remove the loading indicator
        await callback_query.answer("Sync started! You can use other commands while it processes.")
    
    elif data == "reject_sync":
        # User rejected media sync
        user = db.get_user(str(user_id))
        
        # Check if there's a pending sync operation
        if "pending_sync" not in user or not user["pending_sync"]:
            await callback_query.message.edit_text("❌ No pending media sync found.")
            return
        
        # Check if this is the latest sync operation
        if "sync_operation_id" in user and "sync_request_time" in user:
            # Get the operation ID from the message
            message_text = callback_query.message.text
            operation_id_match = re.search(r"Operation ID: (sync_[\d_]+)", message_text)
            
            if operation_id_match:
                message_operation_id = operation_id_match.group(1)
                # Check if the operation ID in the message matches the latest one in user data
                if message_operation_id != user["sync_operation_id"]:
                    # This is an expired sync operation
                    await callback_query.message.edit_text(
                        "⚠️ **Sync Operation Expired** ⚠️\n\n"
                        "This sync request has expired because a newer request was made.\n"
                        "Please use the latest sync confirmation message or send /syncmedia again."
                    )
                    await callback_query.answer("This sync operation has expired.")
                    return
        
        # Clear pending sync data
        user["pending_sync"] = []
        if "sync_operation_id" in user:
            del user["sync_operation_id"]
        if "sync_request_time" in user:
            del user["sync_request_time"]
        db.update_user(str(user_id), user)
        
        # Get current time in a readable format
        current_time = time.strftime("%H:%M:%S")
        
        # Reset sync attempts counter when user rejects sync
        if "sync_attempts" in user:
            user["sync_attempts"] = 0
            db.update_user(str(user_id), user)
        
        await callback_query.message.edit_text(
            "🚫 **SYNC OPERATION TERMINATED** 🚫\n\n"
            "⛔ Your media synchronization has been cancelled ⛔\n\n"
            "📱 **Status Details:**\n"
            "   • 🔄 Operation: Media Sync\n"
            "   • ⏹️ Result: Cancelled by User\n"
            "   • 📂 Files Synced: 0\n"
            "   • 🕒 Time: " + current_time + "\n\n"
            "💎 **Premium Tip:** Use /syncmedia to try again when you're ready!\n\n"
            "✨ Media Vault - Exclusive Content Network ✨"
        )
        
        # Acknowledge the callback query
        await callback_query.answer()
    
    elif data == "replace_sync":
        # User wants to replace previous sync with a new one
        user = db.get_user(str(user_id))
        
        # Clear previous pending sync
        user["pending_sync"] = []
        if "sync_operation_id" in user:
            del user["sync_operation_id"]
        if "sync_request_time" in user:
            del user["sync_request_time"]
        
        # Reset sync attempts counter
        user["sync_attempts"] = 0
        db.update_user(str(user_id), user)
        
        # Inform user to start a new sync
        await callback_query.message.edit_text(
            "✅ **Previous sync operation cleared**\n\n"
            "Please use /syncmedia command again to start a new sync operation."
        )
        
        # Acknowledge the callback query
        await callback_query.answer()


async def process_confirmed_sync(client, user_id, user, progress_msg):
    """Process confirmed sync asynchronously, with chunking, retry & FloodWait handling, and full-resume semantics."""
    try:
        if not user["active"] and not user["premium"]:
            await progress_msg.edit_text(
                "❌ **Sync Failed** ❌\n\n"
                "You are currently inactive. Upload media regularly or upgrade to premium."
            )
            return

        # Keep the pending list as the source of truth for resuming
        if "pending_sync" not in user or not user["pending_sync"]:
            await progress_msg.edit_text("❌ No pending media sync found.")
            return

        pending = list(user["pending_sync"])
        total = len(pending)
        sent = 0
        started_at = time.time()

        def _persist_remaining():
            user["pending_sync"] = pending
            db.update_user(str(user_id), user)

        base_delay = 0.2

        idx = 0
        while idx < len(pending):
            media = pending[idx]
            # Minimal caption
            try:
                orig_user = db.get_user(media.get("user_id", "")) if media.get("user_id") else None
                alias = (orig_user or {}).get("alias", "Anonymous")
                caption = f"Shared by: <a href=\"https://telegram.me/{BOT_USERNAME}\">{alias}</a>"
            except Exception:
                caption = None

            max_retries = 5
            attempt = 0
            while True:
                try:
                    from pyrogram import enums
                    if media["media_type"] == "photo":
                        await client.send_photo(user_id, media["file_id"], caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif media["media_type"] == "video":
                        await client.send_video(user_id, media["file_id"], caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif media["media_type"] == "document":
                        await client.send_document(user_id, media["file_id"], caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif media["media_type"] == "audio":
                        await client.send_audio(user_id, media["file_id"], caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif media["media_type"] == "voice":
                        await client.send_voice(user_id, media["file_id"], caption=caption, parse_mode=enums.ParseMode.HTML)
                    else:
                        await client.send_cached_media(user_id, media["file_id"], caption=caption, parse_mode=enums.ParseMode.HTML)
                    break
                except Exception as e:
                    from pyrogram.errors import FloodWait
                    if isinstance(e, FloodWait):
                        await asyncio.sleep(e.value + 1)
                        continue
                    attempt += 1
                    if attempt >= max_retries:
                        # Move to end to retry later
                        pending.append(pending.pop(idx))
                        _persist_remaining()
                        await asyncio.sleep(1)
                        break
                    await asyncio.sleep(1)

            # Success: remove and mark synced; if moved to end, skip popping here
            if idx < len(pending) and pending[idx] is media:
                if not user.get("premium", False):
                    media_id = None
                    for mid, mdata in db.media.items():
                        if mdata.get("file_id") == media.get("file_id") and mdata.get("user_id") == media.get("user_id"):
                            media_id = mid
                            break
                    if media_id:
                        db.mark_media_synced(str(user_id), media_id)
                pending.pop(idx)
                sent += 1
            else:
                idx += 1

            if sent % 50 == 0 or sent == total:
                _persist_remaining()
                try:
                    await progress_msg.edit_text(f"🧲 Syncing… {sent}/{total}")
                except Exception:
                    pass
            await asyncio.sleep(base_delay)

        _persist_remaining()  # should be empty now
        elapsed = int(time.time() - started_at)
        try:
            await progress_msg.edit_text(
                f"✅ **Sync Completed Successfully!** 🎉\n\n"
                f"📦 **Files Synced:** {sent}\n"
                f"⏱️ Time: {elapsed}s"
            )
        except Exception:
            pass
        user["sync_attempts"] = 0
        db.update_user(str(user_id), user)
    except Exception as e:
        try:
            await progress_msg.edit_text(f"❌ Sync error: {e}")
        except Exception:
            pass

async def check_activity_task():
    """Periodically check user activity and update status"""
    while True:
        try:
            # Check all users
            for user_id, user_data in db.users.items():
                # Skip premium users (they are always active)
                if user_data.get("premium", False):
                    continue
                
                # Check if user is active and should be set to inactive
                if user_data.get("active", False) and not db.check_activity(user_id):
                    # Set user as inactive
                    db.set_user_offline(user_id)
                    logger.info(f"User {user_id} set to inactive due to inactivity")
            
            # Save changes
            db._save_json(db.users_file, db.users)
            db._save_json(db.stats_file, db.stats)
        except Exception as e:
            logger.error(f"Error in check_activity_task: {str(e)}")
        
        # Wait for 5 minutes before next check
        await asyncio.sleep(300)

# Duplicate media cleanup task
async def cleanup_duplicates_task():
    """Periodically clean up duplicate media older than 24 hours"""
    while True:
        try:
            # Run cleanup every hour
            db.cleanup_duplicate_media()
            logger.info("Cleaned up duplicate media older than 24 hours")
        except Exception as e:
            logger.error(f"Error in cleanup_duplicates_task: {str(e)}")
        
        # Wait for 1 hour before next cleanup
        await asyncio.sleep(3600)

# Online status checker task
async def check_online_status_task():
    """Periodically check user online status and set inactive users to offline"""
    while True:
        try:
            # Check all users
            for user_id, user_data in db.users.items():
                # Skip banned users
                if user_data["banned"]:
                    continue
                
                # Check if user is marked as online but hasn't been active recently
                if "online" in user_data and user_data["online"]:
                    # If last activity was more than 5 minutes ago, set user offline
                    current_time = time.time()
                    if current_time - user_data["last_activity"] > 300:  # 5 minutes = 300 seconds
                        logger.info(f"Setting user {user_id} offline due to inactivity")
                        db.set_user_offline(user_id)
        except Exception as e:
            logger.error(f"Error in online status checker task: {str(e)}")
            
        # Check every minute
        await asyncio.sleep(60)

# Start the bot
if __name__ == "__main__":
    logger.info("Starting SIN CITY Media Bot in hybrid mode...")
    app.start()
    
    # Start activity checker task
    app.loop.create_task(check_activity_task())
    
    # Start online status checker task
    app.loop.create_task(check_online_status_task())
    
    # Start duplicate media cleanup task
    app.loop.create_task(cleanup_duplicates_task())
    logger.info("Duplicate media cleanup task scheduled")
    
    # Keep the bot running
    
async def resume_pending_downloads_task():
    """Scan DB for pending downloads and re-queue them for processing after restarts or heavy loads."""
    await asyncio.sleep(0.5)
    try:
        pending = []
        for mid, m in db.media.items():
            if m.get("pending_download", False) and m.get("user_id"):
                pending.append((m["user_id"], m["file_id"]))
        # Re-queue by creating dummy messages is hard offline;
        # Best-effort: notify owner in logs and rely on future uploads.
        if pending:
            logging.info(f"Found {len(pending)} pending downloads to resume.")
    except Exception as e:
        logging.error(f"Error in resume_pending_downloads_task: {e}")

    # Start resume task
    app.loop.create_task(resume_pending_downloads_task())

    idle()
    
    # Stop the bot
    app.stop()