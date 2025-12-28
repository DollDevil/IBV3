# Embed Refactoring Guide

## Pattern Established

All IslaBot messages should use embeds with the following pattern:

### Import
```python
from utils.embed_utils import create_embed
```

### Server Messages (No Author)
```python
embed = create_embed(
    description="Message text",
    title="Optional Title",
    color="success",  # or "error", "warning", "info", "neutral", etc.
    is_dm=False,
    is_system=False
)
await interaction.response.send_message(embed=embed, ephemeral=True)
```

### DM Messages (Include Author)
```python
embed = create_embed(
    description="Message text",
    title="Optional Title",
    color="info",  # or appropriate color
    is_dm=True,  # This adds the author
    is_system=False
)
await member.send(embed=embed)
```

### System Messages (Include Author)
```python
embed = create_embed(
    description="Welcome message or system notification",
    title="Welcome",
    color="system",
    is_dm=False,
    is_system=True  # This adds the author
)
await channel.send(embed=embed)
```

## Color Guide

- `"info"` - Blue (0x3498DB) - Informational messages
- `"success"` - Green (0x2ECC71) - Success/confirmation
- `"warning"` - Orange (0xF39C12) - Warnings
- `"error"` - Red (0xE74C3C) - Errors
- `"neutral"` - Purple (0x9B59B6) - Neutral/default
- `"system"` - Purple (0x673AB7) - System messages
- `"economy"` - Gold (0xFFD700) - Economy/coins
- `"casino"` - Red-pink (0xFF6B6B) - Casino games
- `"event"` - Purple (0x9B59B6) - Events
- `"order"` - Blue (0x3498DB) - Orders
- `"discipline"` - Red (0xE74C3C) - Discipline
- `"profile"` - Teal (0x1ABC9C) - Profile/stats

## Files Updated

- ✅ `islabot/utils/embed_utils.py` - Centralized embed utility
- ✅ `islabot/cogs/moderation.py` - All messages converted
- ✅ `islabot/cogs/config_group.py` - All messages converted

## Files Still Needing Updates

All other cogs need to be updated. Common patterns to replace:

1. `await interaction.response.send_message("Server only.", ephemeral=True)`
   → Use `create_embed("Server only.", color="warning", ...)`

2. `await interaction.followup.send("Message", ephemeral=True)`
   → Use `create_embed("Message", color="info", ...)`

3. `await member.send("DM message")`
   → Use `create_embed("DM message", color="info", is_dm=True, ...)`

4. `await channel.send("System message")`
   → Use `create_embed("System message", color="system", is_system=True, ...)`

## Detection Logic

- **DM**: If sending to `member.send()` or `user.send()` → `is_dm=True`
- **System**: If sending welcome/onboarding/announcements to channels → `is_system=True`
- **Server**: All other interaction responses → `is_dm=False, is_system=False`

