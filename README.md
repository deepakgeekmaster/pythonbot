# Telegram Large Media Handler Bot

This is a basic test model for a Telegram bot that can handle large adult media files (up to 2GB) by bypassing the standard Bot API's 20MB download limit. It uses the MTProto API via the Pyrogram library.

## Features

- Handles adult media files up to 2GB
- Prevents duplicate uploads from the same user
- Provides download progress and statistics
- Basic command handling (/start, /help, /status)
- Hybrid mode: Uses both Bot API and MTProto API

## Setup Instructions

### 1. Get API Credentials

1. Visit [my.telegram.org/apps](https://my.telegram.org/apps)
2. Log in with your Telegram account
3. Click on "API Development Tools"
4. Create a new application
5. Save your API ID and API Hash

### 2. Install Requirements

```bash
pip install pyrogram tgcrypto python-dotenv
```

### 3. Configure Environment Variables

1. Copy the example.env file to .env:
   ```bash
   copy example.env .env
   ```

2. Edit the .env file and add your API credentials:
   ```
   BOT_TOKEN=your_bot_token_here
   OWNER_ID=your_telegram_id_here
   BOT_USERNAME=your_bot_username_without_@
   OWNER_USERNAME=your_username_without_@
   API_ID=your_api_id_here
   API_HASH=your_api_hash_here
   ```

### 4. Run the Bot

```bash
python bot.py
```

Since we're using hybrid mode with a bot token, you won't need to authenticate with your phone number. The bot will start directly using the bot token for authentication.

## Usage

1. Start a chat with your account that's running the bot
2. Send any adult media file (photo, video, document) up to 2GB
3. The bot will download and save the file to the `media` directory

## Notes

- This is a basic test model to verify the large file handling capability
- The bot runs in hybrid mode, using both Bot API and MTProto API
- Bot API is used for command handling and basic interactions
- MTProto API is used for handling large files (up to 2GB)
- Additional features from the full specification will be added later

## Future Enhancements

- Access key system
- Premium user features
- Media synchronization
- Activity tracking
- Admin controls
- And more as specified in the full feature list