#!/usr/bin/env python3
"""Fix DM and system messages to use correct flags."""
import re
from pathlib import Path

COG_DIR = Path("islabot/cogs")

def fix_dm_messages(content: str) -> str:
    """Fix DM messages to use is_dm=True."""
    # Pattern: await member.send(embed=...) or await user.send(embed=...)
    # These should use is_dm=True
    content = re.sub(
        r'await (member|user)\.send\(embed=([^)]+)\)',
        lambda m: f'await {m.group(1)}.send(embed={m.group(2).replace("is_dm=False", "is_dm=True").replace("is_system=False", "is_system=False") if "create_embed" in m.group(2) else m.group(2)})',
        content
    )
    
    # If embed is created with create_embed but doesn't have is_dm=True, add it
    # This is a bit complex, so we'll handle it case by case
    return content

def fix_system_messages(content: str) -> str:
    """Fix system messages (welcome/onboarding) to use is_system=True."""
    # Welcome messages sent to channels should be system messages
    # Look for patterns like welcome channel sends, onboarding messages
    # This is context-dependent, so we'll mark them for manual review
    
    # Pattern: channel.send with welcome/onboarding content
    if "welcome" in content.lower() or "onboarding" in content.lower():
        # Mark for manual review - these need is_system=True
        pass
    
    return content

def process_file(filepath: Path) -> bool:
    """Process a file. Returns True if changed."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # Fix DM messages
        # Find all member.send(embed=create_embed(...)) patterns
        # and ensure they have is_dm=True
        def fix_dm_embed(match):
            embed_call = match.group(1)
            # Check if is_dm is already set
            if 'is_dm=True' in embed_call:
                return match.group(0)
            # Add is_dm=True if not present
            if 'is_dm=' in embed_call:
                embed_call = re.sub(r'is_dm=False', 'is_dm=True', embed_call)
            else:
                # Add is_dm=True before the closing parenthesis
                embed_call = embed_call.rstrip(')') + ', is_dm=True)'
            return f'await {match.group(2)}.send(embed={embed_call}'
        
        content = re.sub(
            r'await (member|user)\.send\(embed=(create_embed\([^)]+)\)',
            fix_dm_embed,
            content
        )
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error: {filepath.name}: {e}")
        return False

def main():
    """Process files with DM sends."""
    # Files that likely have DM sends
    dm_files = [
        'onboarding.py',
        'discipline_group.py',
        'announce_and_remind.py',
        'voice_tracker.py',
        'vacation_watch.py',
        'casino_royalty.py',
        'casino_bigwin_dm.py',
        'events.py',
    ]
    
    fixed = []
    for filename in dm_files:
        filepath = COG_DIR / filename
        if filepath.exists() and process_file(filepath):
            fixed.append(filename)
            print(f"Fixed DM messages in {filename}")
    
    print(f"\nFixed {len(fixed)} files with DM messages")
    print("\n[NOTE] System messages (welcome/onboarding) need manual review")
    print("  Look for channel.send() calls and ensure they use is_system=True")

if __name__ == "__main__":
    main()

