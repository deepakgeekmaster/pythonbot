import re
import time
import math
from datetime import datetime, timedelta
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Regular expressions for cleaning captions and messages
USERNAME_PATTERN = re.compile(r'@[\w_]+')
URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')
TELEGRAM_LINK_PATTERN = re.compile(r't\.me/\S+')

def clean_caption(caption):
    """Remove usernames and links from captions"""
    if not caption:
        return caption
    
    # Remove usernames
    caption = USERNAME_PATTERN.sub('', caption)
    
    # Remove URLs
    caption = URL_PATTERN.sub('', caption)
    
    # Remove Telegram links
    caption = TELEGRAM_LINK_PATTERN.sub('', caption)
    
    # Clean up extra whitespace
    caption = re.sub(r'\s+', ' ', caption).strip()
    
    return caption

def format_time_remaining(seconds):
    """Format seconds into a human-readable time string"""
    if seconds == float('inf'):
        return "∞ (Premium User)"
    
    if seconds <= 0:
        return "Expired"
    
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def format_uptime(start_time):
    """Format uptime from start timestamp"""
    uptime_seconds = time.time() - start_time
    days, remainder = divmod(int(uptime_seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

# This function is redundant as we already have format_uptime above
# Keeping it for backward compatibility but using the other implementation
def format_uptime(seconds):
    """Format seconds into a human-readable uptime string"""
    if isinstance(seconds, (int, float)):
        # If seconds is provided directly
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        
        return " ".join(parts)
    else:
        # If start_time is provided
        return format_uptime(time.time() - seconds)

# Keyboard generators
def get_start_keyboard(user_id, is_admin=False):
    """Generate keyboard for start command"""
    keyboard = [
        [InlineKeyboardButton("😶‍🌫️ Contact Admin", url=f"https://t.me/eternity_targid")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data=f"admin")])
    
    return InlineKeyboardMarkup(keyboard)

def get_access_denied_keyboard():
    """Generate keyboard for access denied message"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Contact Admin", url=f"https://t.me/eternity_targid")]
    ])

def get_premium_promo_keyboard():
    """Generate keyboard for premium promotion"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔱 Get Premium Access", url=f"https://t.me/eternity_targid")]
    ])

def get_admin_keyboard():
    """Generate keyboard for admin panel"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Generate Key", callback_data=f"genkey")],
        [InlineKeyboardButton("📊 Status", callback_data=f"status")],
        [InlineKeyboardButton("📣 Broadcast", callback_data=f"broadcast")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"back_to_start")]
    ])

def get_report_keyboard(media_id, reporter_id):
    """Generate keyboard for report handling"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Remove Content", callback_data=f"remove_{media_id}")],
        [InlineKeyboardButton("🚫 Ban Uploader", callback_data=f"ban_{media_id.split('_')[0]}")],
        [InlineKeyboardButton("❌ Dismiss Report", callback_data=f"dismiss_{media_id}")]
    ])

# Message templates
def get_welcome_message(user_name, is_premium=False):
    """Generate welcome message"""
    if is_premium:
        return (
            f"👋 **Welcome to the Media Vault, {user_name}!** \n\n"
            f"💎 You have **PREMIUM** access! 💎\n\n"
            f"🔐 /start <key> – Register using an access key\n"
            f"🧲 /syncmedia – Get new media from vault\n"
            f"📊 /mystats – See your stats and progress\n"
            f"🏆 /top – View top contributors\n"
            f"📌 /pin – Pin a message (admins only)\n"
            f"🚨 /report – Report inappropriate media\n\n"
            f"❓ Need access? Message @eternity_targid\n"
            f"🔗 Bot: @ETERNAL_SIN_BOT\n\n"
            f"🎉 Enjoy your premium experience! 🎉"
        )
    else:
        return (
            f"👋 **Welcome to the Media Vault, {user_name}!** \n\n"
            f"Here's what you can do:\n\n"
            f"🔐 /start <key> – Register using an access key\n"
            f"🧲 /syncmedia – Get new media from vault\n"
            f"📊 /mystats – See your stats and progress\n"
            f"🏆 /top – View top contributors\n"
            f"🚨 /report – Report inappropriate media\n\n"
            f"❓ Need access? Message @eternity_targid\n"
            f"🔗 Bot: @ETERNAL_SIN_BOT\n\n"
            f"💎 **Want unlimited access?** 💎\n"
            f"💬 Contact @eternity_targid for premium benefits:\n"
            f"   • 🔄 Unlimited synced media\n"
            f"   • ⏰ No activity requirements\n"
            f"   • 🔔 Priority support\n"
            f"   • 🌟 Exclusive premium content"
        )

def get_new_user_welcome_message(user_name):
    """Generate welcome message for first-time users"""
    return (
        f"✨ **Welcome to Media Vault, {user_name}!** ✨\n\n"
        f"🌟 **Exclusive Media Sharing Network** 🌟\n\n"
        f"📱 Share and discover premium media content\n"
        f"🔒 Private, secure, and exclusive community\n"
        f"🚀 Active members get access to unique content\n\n"
        f"🔑 **To Get Started:**\n"
        f"Use the direct join link provided with your access key\n"
        f"or enter your access key manually:\n"
        f"👉 /start YOUR_ACCESS_KEY\n\n"
        f"🎁 **Don't have an access key?**\n"
        f"Contact @eternity_targid to join our exclusive network\n\n"
        f"🌐 **Join our growing community today!**\n"
        f"💫 Thousands of media files waiting for you\n"
        f"🏆 Become a top contributor and earn rewards\n"
    )

async def handle_unauthorized_access(message):
    """Handle unauthorized access for commands other than /start"""
    access_denied = get_access_denied_message()
    keyboard = get_access_denied_keyboard()
    await message.reply(access_denied, reply_markup=keyboard)
        

def get_access_denied_message():
    """Generate access denied message"""
    return (
        "🚫 **Access Denied** 🚫\n\n"
        "⛔ You don't have access to this exclusive Media Vault network.\n\n"
        "🔐 **How to Join:**\n"
        "1️⃣ Obtain a valid access key\n"
        "2️⃣ Use the join link provided with your key\n\n"
        "❌ **Invalid Key?** The key you provided is either invalid, expired, or has reached its maximum uses.\n\n"
        "💬 Contact @eternity_targid to request a new access key\n"
        "🔒 This is a private network with controlled access\n"
        "✨ Join our exclusive community today! ✨"
    )

def get_activation_message():
    """Generate activation message"""
    return (
        "🎉 **Congratulations!** 🎉\n\n"
        "✅ **Upload Completed!** Now You Can Enjoy Our Media! ✅\n\n"
        "🚀 **What You Can Do Now:**\n"
        "🧲 Use /syncmedia to receive 20 media files from other users\n"
        "📊 Check your stats with /mystats\n"
        "🏆 View top contributors with /top\n"
        "🚨 Report inappropriate content with /report\n\n"
        "⏱️ Remember to stay active by uploading 30 files every 24 hours\n\n"
        "💎 **Want unlimited access?** 💎\n"
        "💬 Contact @eternity_targid for premium benefits\n"
        "🔑 Enjoy exclusive content and features!\n\n"
        "✨ You are now ACTIVE! Use /syncmedia to start receiving media! ✨"
    )

def get_inactivity_message():
    """Generate inactivity message"""
    return (
        "⚠️ **Account Inactive** ⚠️\n\n"
        "⏱️ Your 24-hour activity period has expired\n\n"
        "📋 **To Regain Active Status:**\n"
        "1️⃣ Upload 30 media files\n"
        "2️⃣ Your status will automatically update\n\n"
        "❗ While inactive, you cannot:\n"
        "   🧲 Use /syncmedia\n"
        "   📥 Receive new content from others\n\n"
        "✨ **Never worry about activity again!** ✨\n"
        "💎 Upgrade to premium for permanent active status\n"
        "🔔 Contact @eternity_targid for details\n"
        "🌟 Join our elite members today! 🌟"
    )

def get_sync_limit_message(total_available_media):
    """Generate sync limit message with total available media count"""
    return (
        "🔴 **SYNCHRONIZATION STOPPED** 🔴\n\n"
        "📊 **You've reached your maximum limit of 20 synced media files**\n"
        f"📈 **TOTAL AVAILABLE MEDIA: {total_available_media}** 📈\n"
        "⚠️ All media (including premium user uploads) is counted in this total\n"
        "⏱️ This limit resets when your activity period renews\n\n"
        "💎 **GET PREMIUM ACCESS** 💎\n"
        "🌟 Premium members enjoy:\n"
        "   🔄 Unlimited media syncing\n"
        "   🚀 Priority access to new content\n"
        "   ⏰ No activity requirements\n"
        "   🔔 Priority support\n\n"
        "💬 **Contact @eternity_targid to upgrade now!**"
    )

def get_sync_confirmation_message(media_count):
    """Generate sync confirmation message with media count"""
    return (
        "📡✨ MESSAGE SYNC INITIATED! ✨📡\n\n"
        "📂📨 Media Files Available:\n"
        f"🚨 {media_count} MEDIA FILES 🚨 queued for sync!\n\n"
        "⚠️🔍 IMPORTANT SYNC NOTES 🔍⚠️\n\n"
        "🟪⏳ Sync Etiquette\n"
        "• Do NOT interrupt an active sync — let it hit 💯% completion!\n\n"
        "🟪🔐 One-Time Precision Sync\n"
        "• Chat history is synced once to ensure pure accuracy!\n\n"
        "🟪📊 Dual Message Streams\n"
        "1️⃣ 🕰 Pre-Join Archive — Full backlogged content\n"
        "2️⃣ 🌐 Live Flow — Real-time message delivery\n\n"
        "🟪⚙️ Smart Delivery System\n"
        "• Gradual rollout ⏱️ (30–60s intervals) for max stability\n\n"
        "🆙⚡️ SYSTEM UPGRADE IN EFFECT ⚡️🆙\n"
        "• Enjoy the new v2 Sync Engine!\n"
        "• 🔁 Some past messages may reappear during transition\n\n"
        "📲 MEDIA ACCESS REQUEST\n"
        "🖼📹 Tap [✅ CONFIRM] to enable media attachments!\n\n"
        "🎟🎟🎟 SYNC IN PROGRESS… STAY TUNED 🎟🎟🎟"
    )

def get_sync_confirmation_keyboard():
    """Generate keyboard for sync confirmation"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ CONFIRM", callback_data=f"confirm_sync"),
         InlineKeyboardButton("❌ REJECT", callback_data=f"reject_sync")]
    ])

def get_premium_promo_keyboard():
    """Generate keyboard for premium promotion"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧲 Sync Media", callback_data="/syncmedia")],
        [InlineKeyboardButton("🔱 Upgrade to Premium", url="https://t.me/eternity_targid")]
    ])

def get_stats_message(user_data, time_remaining):
    """Generate stats message"""
    status = "💎 Premium" if user_data["premium"] else ("✅ Active" if user_data["active"] else "❌ Inactive")
    time_str = format_time_remaining(time_remaining)
    
    return (
        f"📊 **Your Personal Stats** 📊\n\n"
        f"🔒 **Alias:** {user_data['alias']}\n"
        f"📅 **Joined:** {datetime.fromtimestamp(user_data['join_date']).strftime('%Y-%m-%d')}\n"
        f"📤 **Uploads:** {user_data['uploads']}\n"
        f"🧲 **Synced:** {len(user_data['synced_media'])}\n"
        f"⭐ **Status:** {status}\n"
        f"⏳ **Time until inactive:** {time_str}\n\n"
        f"{'🌟 You have premium status and will never become inactive! 🌟' if user_data['premium'] else '⚠️ Remember to upload 30 media files every 24 hours to stay active! 🔔'}"
    )

def get_download_progress_message(current, total, file_name=None):
    """Generate download progress message"""
    percent = current * 100 / total
    progress_bar = generate_progress_bar(percent)
    
    message = f"📥 **Downloading{'...' if not file_name else f': {file_name}'}** 🔽\n\n"
    message += f"{progress_bar} {percent:.1f}% 📊\n"
    message += f"📊 {format_size(current)} / {format_size(total)}\n"
    
    return message

def get_upload_progress_message(current, total, file_name=None):
    """Generate upload progress message"""
    percent = current * 100 / total
    progress_bar = generate_progress_bar(percent)
    
    message = f"📤 **Uploading{'...' if not file_name else f': {file_name}'}** 🔼\n\n"
    message += f"{progress_bar} {percent:.1f}% 📊\n"
    message += f"📦 {format_size(current)} / {format_size(total)}\n"
    
    return message

def get_download_complete_message(file_size, download_time, file_name=None):
    """Generate download complete message"""
    # If file_name is None, it means we're handling a sync completion message
    # where file_size is actually the count of synced files
    if file_name is None:
        # This is a sync completion message
        synced_count = file_size  # In this context, file_size is actually the count of synced files
        return (
            f"✅ **Sync Completed Successfully!** 🎉\n\n"
            f"📦 **Files Synced:** {synced_count}\n"
            f"⏱️ **Total Time:** {download_time:.2f} seconds\n"
            f"🔄 All media has been synced to your account\n"
            f"🔔 Enjoy your media! 🔔"
        )
    else:
        # This is a file download completion message
        speed = file_size / download_time if download_time > 0 else 0
        
        return (
            f"✅ **File successfully saved!** 🎉\n\n"
            f"📦 **Size:** {format_size(file_size)}\n"
            f"⏱️ **Download time:** {download_time:.2f} seconds\n"
            f"🚀 **Average speed:** {format_size(speed)}/s\n"
            f"💾 **Saved as:** {file_name}\n"
            f"🔔 Enjoy your media! 🔔"
        )

def get_duplicate_message(file_name):
    """Generate duplicate file message"""
    return (
        f"⚠️ **Duplicate Detected** ⚠️\n\n"
        f"This file has already been uploaded to the system.\n"
        f"📂 **File:** {file_name}\n\n"
        f"💾 Each file is only stored once to save space.\n"
        f"🔍 Try uploading different content! 🔍"
    )

def get_report_message(media_id):
    """Generate report confirmation message"""
    return (
        f"🚨 **Report Submitted** 🚨\n\n"
        f"🙏 Thank you for helping keep our community safe!\n"
        f"👮 An admin will review this content shortly.\n\n"
        f"📂 **Media ID:** {media_id}\n"
        f"✅ Your report has been logged successfully.\n"
        f"🛡️ We value your contribution to our safe environment! 🛡️"
    )

def get_admin_report_message(media_id, reporter_id, reporter_alias):
    """Generate admin report notification"""
    return (
        f"🚨 **Content Reported** 🚨\n\n"
        f"📂 **Media ID:** {media_id}\n"
        f"👤 **Reported by:** {reporter_alias} (ID: {reporter_id})\n\n"
        f"⚠️ Please review this content and take appropriate action.\n"
        f"🛡️ Thank you for maintaining our community standards! 🛡️"
    )

def get_top_users_message(top_users):
    """Generate top users message"""
    message = "🏆 **Top 5 Contributors** 🏆\n\n"
    
    if not top_users:
        message += "No users have uploaded content yet.\n"
        return message
    
    for i, (user_id, user) in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"
        message += f"{medal} **#{i}** {user['alias']} - {user['uploads']} uploads\n"
    
    message += "\n💎 Want to see your name here? Keep uploading!"
    return message

def get_link_message(link_url=None, link_name=None):
    """Generate community link message"""
    # If no link is provided, use the default
    if not link_url:
        from bot import db
        link_url = db.get_community_link()
        # If no custom name is provided, try to get it from the database
        if not link_name:
            link_name = db.get_community_link_name()
    
    # Extract the link text (everything after the last /) if no custom name provided
    if not link_name:
        link_name = link_url.split('/')[-1].replace('_', ' ')
    
    return (
        "🔗 **Community Link** 🔗\n\n"
        "Join our exclusive community channel for updates, discussions, and premium content!\n\n"
        f"👉 [{link_name}]({link_url})\n\n"
        "🌟 Benefits of joining:\n"
        "• Early access to new features\n"
        "• Direct communication with admins\n"
        "• Exclusive content and announcements\n"
        "• Connect with other members\n\n"
        "See you there! 🚀"
    )

def get_logout_message():
    """Generate logout message"""
    return (
        "🚪 **Logged Out Successfully** 🚪\n\n"
        "✅ You have been logged out of the Media Vault Bot.\n"
        "✅ Your user data has been removed from our database.\n\n"
        "If you wish to use the bot again, you will need to:\n"
        "1️⃣ Use the /start command\n"
        "2️⃣ Provide a valid access key\n\n"
        "Thank you for using Media Vault! 👋"
    )

def get_ghost_message(user_id, success=True):
    """Generate ghost user message"""
    if success:
        return f"👻 User {user_id} has been ghosted and will not appear in the top users list."
    else:
        return f"❌ Failed to ghost user {user_id}. User may not exist or is already ghosted."

def get_unghost_message(user_id, success=True):
    """Generate unghost user message"""
    if success:
        return f"👁️ User {user_id} has been unghosted and will now appear in the top users list."
    else:
        return f"❌ Failed to unghost user {user_id}. User may not exist or is not ghosted."

def get_admin_message(user_id, success=True):
    """Generate admin promotion message"""
    if success:
        return f"👑 User {user_id} has been promoted to admin status."
    else:
        return f"❌ Failed to promote user {user_id}. User may not exist or is already an admin."

def get_demote_message(user_id, success=True):
    """Generate admin demotion message"""
    if success:
        return f"👤 User {user_id} has been demoted from admin status."
    else:
        return f"❌ Failed to demote user {user_id}. User may not exist or is not an admin."

def get_pin_message(success=True):
    """Generate pin message confirmation"""
    if success:
        return "📌 Message has been pinned successfully."
    else:
        return "❌ Failed to pin message. Make sure the bot has pin message permissions."

def generate_progress_bar(percent, length=10):
    """Generate a progress bar"""
    filled_length = int(length * percent // 100)
    empty_length = length - filled_length
    
    # Using emoji for better visibility
    bar = '🟩' * filled_length + '⬜' * empty_length
    return bar