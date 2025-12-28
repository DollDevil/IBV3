"""
Centralized embed utility for IslaBot.
Handles DM, server, and system messages with appropriate styling.
"""
from __future__ import annotations
import discord
import random

# Constants
ISLA_ICON = "https://i.imgur.com/5nsuuCV.png"
STYLE1_NEUTRAL = "https://i.imgur.com/9oUjOQQ.png"

# Embed colors for different message types
COLORS = {
    "info": 0x3498DB,        # Blue - informational messages
    "success": 0x2ECC71,     # Green - success/confirmation
    "warning": 0xF39C12,     # Orange - warnings
    "error": 0xE74C3C,       # Red - errors
    "neutral": 0x9B59B6,     # Purple - neutral/default
    "system": 0x673AB7,      # Purple - system messages
    "economy": 0xFFD700,     # Gold - economy/coins
    "casino": 0xFF6B6B,      # Red-pink - casino games
    "event": 0x9B59B6,       # Purple - events
    "order": 0x3498DB,       # Blue - orders
    "discipline": 0xE74C3C,  # Red - discipline
    "profile": 0x1ABC9C,     # Teal - profile/stats
}

STYLE_1 = {
    "confident_smirk": [
        "https://i.imgur.com/5nsuuCV.png",
        "https://i.imgur.com/8qQkq0p.png",
        "https://i.imgur.com/8AsaLI5.png",
        "https://i.imgur.com/sGDoIDA.png",
        "https://i.imgur.com/qC0MOZN.png",
        "https://i.imgur.com/rcgIEtj.png",
    ],
    "bothered": ["https://i.imgur.com/k7AexFe.png"],
    "laughing": [
        "https://i.imgur.com/eoNSHQ1.png",
        "https://i.imgur.com/TS1KMQe.png",
        "https://i.imgur.com/zcb1ztK.png",
        "https://i.imgur.com/lpMQlWO.png",
    ],
    "displeased": [
        "https://i.imgur.com/9g4g7iV.png",
        "https://i.imgur.com/h68lq5E.png",
        "https://i.imgur.com/0pFNbQc.png",
        "https://i.imgur.com/8Ay5met.png",
        "https://i.imgur.com/ZQQIji3.png",
        "https://i.imgur.com/KmAneUM.png",
        "https://i.imgur.com/9oUjOQQ.png",
    ],
    "pleased": [
        "https://i.imgur.com/sCjhY7W.png",
        "https://i.imgur.com/0BM3E8t.png",
        "https://i.imgur.com/qTvUqq6.png",
        "https://i.imgur.com/JAXB48Q.png",
        "https://i.imgur.com/W3uzVdO.png",
    ],
    "soft_smirk": [
        "https://i.imgur.com/qC0MOZN.png",
        "https://i.imgur.com/rcgIEtj.png",
        "https://i.imgur.com/8qQkq0p.png",
    ],
    "neutral": ["https://i.imgur.com/9oUjOQQ.png"],
}


def create_embed(
    description: str,
    title: str | None = None,
    color: str | int = "neutral",
    thumbnail: str | None = None,
    emotion: str = "neutral",
    is_dm: bool = False,
    is_system: bool = False,
    fields: list[dict] | None = None,
    footer: str | None = None,
) -> discord.Embed:
    """
    Create a standardized IslaBot embed.
    
    Args:
        description: The embed description
        title: Optional embed title
        color: Color name (from COLORS) or hex int
        thumbnail: Custom thumbnail URL (overrides emotion-based selection)
        emotion: Emotion for thumbnail selection (neutral, pleased, displeased, etc.)
        is_dm: Whether this is a DM message (includes author)
        is_system: Whether this is a system message (includes author)
        fields: List of field dicts with 'name', 'value', and optional 'inline'
        footer: Optional footer text
    
    Returns:
        discord.Embed with appropriate styling
    """
    # Get color
    if isinstance(color, str):
        embed_color = COLORS.get(color, COLORS["neutral"])
    else:
        embed_color = color
    
    # Create embed
    embed = discord.Embed(
        title=title,
        description=description,
        color=embed_color
    )
    
    # Add author for DM or system messages
    if is_dm or is_system:
        embed.set_author(name="Isla", icon_url=ISLA_ICON)
    
    # Set thumbnail
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    elif emotion in STYLE_1:
        urls = STYLE_1[emotion]
        embed.set_thumbnail(url=random.choice(urls))
    else:
        embed.set_thumbnail(url=STYLE1_NEUTRAL)
    
    # Add fields
    if fields:
        for field in fields:
            embed.add_field(
                name=field.get("name", ""),
                value=field.get("value", ""),
                inline=field.get("inline", False)
            )
    
    # Add footer
    if footer:
        embed.set_footer(text=footer)
    
    return embed


def isla_embed(
    desc: str,
    title: str | None = None,
    color: str | int = "neutral",
    thumb: str | None = None,
    is_dm: bool = False,
    is_system: bool = False,
) -> discord.Embed:
    """
    Backward compatibility wrapper for create_embed.
    Creates an embed with Isla branding.
    """
    return create_embed(
        description=desc,
        title=title,
        color=color,
        thumbnail=thumb,
        is_dm=is_dm,
        is_system=is_system,
    )


def info_embed(title: str, desc: str, thumb: str | None = None, is_dm: bool = False, is_system: bool = False) -> discord.Embed:
    """Create an info embed (blue color)."""
    return create_embed(
        description=desc,
        title=title,
        color="info",
        thumbnail=thumb,
        is_dm=is_dm,
        is_system=is_system,
    )


def success_embed(desc: str, title: str | None = None, is_dm: bool = False, is_system: bool = False) -> discord.Embed:
    """Create a success embed (green color)."""
    return create_embed(
        description=desc,
        title=title,
        color="success",
        is_dm=is_dm,
        is_system=is_system,
    )


def error_embed(desc: str, title: str | None = None, is_dm: bool = False, is_system: bool = False) -> discord.Embed:
    """Create an error embed (red color)."""
    return create_embed(
        description=desc,
        title=title,
        color="error",
        is_dm=is_dm,
        is_system=is_system,
    )


def warning_embed(desc: str, title: str | None = None, is_dm: bool = False, is_system: bool = False) -> discord.Embed:
    """Create a warning embed (orange color)."""
    return create_embed(
        description=desc,
        title=title,
        color="warning",
        is_dm=is_dm,
        is_system=is_system,
    )

