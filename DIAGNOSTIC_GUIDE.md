# Bot Connection & Command Sync Diagnostic Guide

## Quick Checklist

### 1. Verify Bot is Running
Check Railway logs for:
- ✅ "Bot is ready! Logged in as [Bot Name]"
- ✅ "Connected to X guild(s)"
- ✅ "✓ Synced X commands to guild [ID]"

### 2. Verify Bot is in Your Server
- Go to your Discord server
- Check Server Settings → Members
- Confirm the bot appears in the member list
- Bot should show as "Online" (green dot)

### 3. Verify Invite URL Has Correct Scopes
**This is the #1 cause of commands not appearing!**

Your invite URL MUST include `applications.commands` scope.

**Correct Format:**
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot%20applications.commands
```

**How to Check:**
1. Go to https://discord.com/developers/applications
2. Select your bot application
3. Go to "OAuth2" → "URL Generator"
4. Under "Scopes", check:
   - ✅ `bot`
   - ✅ `applications.commands` ← **CRITICAL!**
5. Copy the generated URL

**If your current invite is missing `applications.commands`:**
1. Remove the bot from your server (optional, but recommended)
2. Use the NEW invite URL with `applications.commands`
3. Re-invite the bot
4. Wait 1-2 minutes
5. Restart Discord (Ctrl+R or Cmd+R)

### 4. Check Railway Logs for Sync Status

After bot starts, look for:

**✅ Good Signs:**
```
✓ Synced 92 commands to guild [YOUR_GUILD_ID]
  - balance
  - daily
  - profile
  ... and 89 more
```

**❌ Bad Signs:**
```
✗ Error: Missing permissions for guild [ID]
  The bot needs 'applications.commands' scope in the invite URL!
```

```
⚠ Warning: Bot is not in guild [ID]
  The bot must be invited to the server before commands can sync.
```

### 5. Verify Code → GitHub → Railway Flow

**Step 1: Code is in GitHub**
```bash
git log --oneline -5  # Check recent commits
git status            # Should be clean
```

**Step 2: Railway is Deployed**
- Check Railway dashboard
- Verify latest deployment succeeded
- Check deployment logs match GitHub commit

**Step 3: Bot is Running**
- Railway service should show "Active"
- Logs should show bot connected
- No crash errors

### 6. Test Command Sync

**Method 1: Check Logs**
Look for this in Railway logs:
```
Commands in tree before sync: 92
✓ Synced 92 commands to guild [ID]
```

**Method 2: Use Discord API (Advanced)**
```bash
# Get your bot token and guild ID, then:
curl -H "Authorization: Bot YOUR_BOT_TOKEN" \
  "https://discord.com/api/v10/applications/YOUR_APP_ID/guilds/YOUR_GUILD_ID/commands"
```

This should return a JSON array of commands if synced correctly.

### 7. Common Issues & Solutions

#### Issue: "Commands synced but don't appear in Discord"
**Solution:**
1. Re-invite with `applications.commands` scope
2. Wait 2-3 minutes
3. Restart Discord completely
4. Try typing `/` in a channel

#### Issue: "Bot is not in guild"
**Solution:**
1. Invite the bot to your server
2. Make sure you have "Manage Server" permission
3. Check bot appears in member list

#### Issue: "0 commands synced"
**Solution:**
- This is a code issue
- Check Railway logs for command registration errors
- Verify all cogs loaded successfully

#### Issue: "Forbidden error during sync"
**Solution:**
- Bot invite URL missing `applications.commands` scope
- Bot doesn't have permission in the server
- Re-invite with correct scopes

### 8. Force Re-sync Commands

If commands still don't appear after fixing invite URL:

1. **Restart the bot** (Railway will auto-restart on deploy)
2. **Wait 2-3 minutes** for Discord to update
3. **Restart Discord client** completely (not just reload)
4. **Try typing `/`** in a channel

### 9. Verify Bot Permissions

The bot needs these permissions in your server:
- ✅ Send Messages
- ✅ Use Application Commands (automatic with `applications.commands` scope)
- ✅ Read Message History
- ✅ View Channels

Check: Server Settings → Integrations → [Your Bot] → Permissions

## Still Not Working?

1. **Check Railway logs** - Look for errors during sync
2. **Verify bot token** - Make sure it's correct in Railway environment variables
3. **Check guild ID** - Verify it matches your server ID
4. **Test with a simple command** - Try `/ping` if it exists
5. **Check Discord status** - Sometimes Discord has API issues

## Quick Test

After fixing invite URL and restarting:
1. Type `/` in any channel
2. You should see your bot's commands appear
3. If you see other bots' commands but not yours, the sync didn't work
4. If you see nothing, Discord might need more time (wait 5 minutes)

