# Bot Invite URL - CRITICAL FOR SLASH COMMANDS

## The Problem
If slash commands don't show up in Discord, it's almost always because the bot invite URL is missing the `applications.commands` scope.

## How to Fix

### Step 1: Get Your Bot's Client ID
1. Go to https://discord.com/developers/applications
2. Select your bot application
3. Go to the "General Information" tab
4. Copy the "Application ID" (this is your Client ID)

### Step 2: Generate the Correct Invite URL

Replace `YOUR_CLIENT_ID` with your actual Client ID:

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot%20applications.commands
```

**OR use the Discord Developer Portal:**
1. Go to your bot's page
2. Click "OAuth2" → "URL Generator"
3. Select these scopes:
   - ✅ `bot`
   - ✅ `applications.commands` (THIS IS CRITICAL!)
4. Select permissions your bot needs (Administrator, Send Messages, etc.)
5. Copy the generated URL

### Step 3: Re-invite the Bot
1. Use the new invite URL to re-invite the bot to your server
2. Make sure you have permission to manage the server
3. The bot will be added with slash command permissions

### Step 4: Wait and Test
1. Wait 1-2 minutes for Discord to update
2. Restart your Discord client (Ctrl+R or Cmd+R)
3. Type `/` in a channel - you should see the bot's commands

## Quick Check
After restarting the bot, check the console output. You should see:
- "✓ Synced X commands to guild [YOUR_GUILD_ID]"
- A list of command names

If you see "0 commands" or errors, the issue is in the code.
If you see commands synced but they don't appear in Discord, it's the invite URL.

## Common Issues

### "Commands synced but don't appear"
- ✅ Re-invite with `applications.commands` scope
- ✅ Wait 1-2 minutes
- ✅ Restart Discord client

### "0 commands synced"
- ❌ Commands aren't being registered (code issue)
- Check console for errors during startup
- Verify cogs are loading properly

### "Forbidden error during sync"
- ❌ Bot doesn't have access to the guild
- ❌ Bot was removed and needs to be re-invited
- ❌ Guild ID in config.yml is incorrect

