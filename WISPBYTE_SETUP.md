# Wispbyte Setup Guide for IslaBot V3

## 1. Linking GitHub Repository

### Option A: Connect via Wispbyte Dashboard
1. Log into your Wispbyte dashboard
2. Go to your bot/service settings
3. Find "Source" or "Repository" section
4. Click "Connect GitHub" or "Link Repository"
5. Authorize Wispbyte to access your GitHub account
6. Select your repository: `DollDevil/IslaBotV3`
7. Choose the branch (usually `main` or `master`)

### Option B: Manual Git URL
If Wispbyte asks for a Git URL, use:
```
https://github.com/DollDevil/IslaBotV3.git
```

**Repository URL:** `https://github.com/DollDevil/IslaBotV3`

---

## 2. Wispbyte Startup Configuration Fields

### **Start Command / Entry Point**
```
python -m islabot.bot
```

### **Working Directory** (if required)
```
/ (root of repository)
```
or leave blank if it auto-detects

### **Python Version**
```
3.10
```
or `3.11` / `3.12` (Python 3.10+ required)

### **Requirements File Path**
```
islabot/requirements.txt
```
or if Wispbyte requires root-level, you may need to copy it (see below)

### **Environment Variables** (if using instead of config.yml)
If Wispbyte supports environment variables, you can optionally set:
- `DISCORD_BOT_TOKEN` = Your bot token
- (But the bot currently uses `config.yml`, so you'll need to upload that file)

---

## 3. Required Files Setup

### **config.yml**
⚠️ **IMPORTANT:** Your `config.yml` is in `.gitignore` (for security), so it won't be in GitHub.

**You have two options:**

#### Option 1: Upload config.yml via Wispbyte File Manager
1. After deploying, use Wispbyte's file manager/editor
2. Navigate to `islabot/` directory
3. Create/upload `config.yml` with your configuration
4. Make sure it contains your bot token and all settings

#### Option 2: Use Wispbyte Environment Variables (if supported)
If Wispbyte supports environment variables, you may need to modify the bot to read from env vars. Currently, the bot reads from `config.yml`.

### **personality.json** (Optional)
- This file is optional - the bot will use fallback defaults if missing
- If you want custom personality responses, create this file in `islabot/` directory

---

## 4. File Structure on Wispbyte

After deployment, your file structure should look like:
```
/
├── islabot/
│   ├── bot.py
│   ├── config.yml          ← You need to upload this manually
│   ├── requirements.txt
│   ├── islabot.sqlite3     ← Created automatically on first run
│   ├── cogs/
│   ├── core/
│   ├── utils/
│   └── data/
├── README.md
└── .gitignore
```

---

## 5. Step-by-Step Deployment Checklist

1. ✅ **Link GitHub Repository**
   - Repository: `DollDevil/IslaBotV3`
   - Branch: `main`

2. ✅ **Set Start Command**
   - Command: `python -m islabot.bot`

3. ✅ **Set Python Version**
   - Version: `3.10` or higher

4. ✅ **Set Requirements Path** (if required)
   - Path: `islabot/requirements.txt`

5. ✅ **Upload config.yml**
   - Use Wispbyte file manager
   - Upload to `islabot/config.yml`
   - Make sure it has your bot token and all configuration

6. ✅ **Deploy/Start the Bot**
   - Click "Deploy" or "Start" in Wispbyte
   - Check logs for any errors

---

## 6. Verification

After deployment, check the logs for:
- ✅ "Bot is ready" or similar success message
- ✅ Database migration messages
- ✅ No import errors
- ✅ Bot appears online in Discord

If you see errors:
- Check that `config.yml` exists in `islabot/` directory
- Verify bot token is correct
- Check Python version is 3.10+
- Verify all dependencies installed correctly

---

## 7. Troubleshooting

### Bot won't start
- Check logs for error messages
- Verify `config.yml` is in `islabot/` directory
- Check bot token is valid

### Import errors
- Verify requirements.txt path is correct
- Check that all files were deployed from GitHub

### Database errors
- Database is created automatically on first run
- Make sure Wispbyte has write permissions in the `islabot/` directory

---

## Quick Reference

| Field | Value |
|-------|-------|
| **Repository** | `https://github.com/DollDevil/IslaBotV3` |
| **Start Command** | `python -m islabot.bot` |
| **Python Version** | `3.10` or higher |
| **Requirements Path** | `islabot/requirements.txt` |
| **Config File** | `islabot/config.yml` (upload manually) |

---

**Note:** Make sure your `config.yml` contains your actual bot token and all necessary configuration before starting the bot!

