#!/usr/bin/env python3
"""
Fast bulk conversion of all messages to embeds.
Preserves all information, formatting, and context.
"""
import re
from pathlib import Path

COG_DIR = Path("islabot/cogs")
EXCLUDED = {'__init__.py', 'moderation.py', 'config_group.py', 'consent.py'}

def add_import(content: str) -> str:
    """Add embed_utils import if missing."""
    if "from utils.embed_utils import create_embed" in content:
        return content
    
    lines = content.split('\n')
    insert_idx = 0
    
    # Find last import
    for i, line in enumerate(lines):
        if line.strip().startswith(('from ', 'import ')):
            insert_idx = i + 1
    
    lines.insert(insert_idx, 'from utils.embed_utils import create_embed')
    return '\n'.join(lines)

def convert_message_sends(content: str) -> str:
    """Convert all message sends to embeds."""
    
    # Pattern 1: "Server only." / "Guild only." - warning
    content = re.sub(
        r'await interaction\.response\.send_message\("(Server|Guild) only\."',
        r'embed = create_embed("\1 only.", color="warning", is_dm=False, is_system=False)\n            await interaction.response.send_message(embed=embed',
        content
    )
    content = re.sub(
        r'await interaction\.followup\.send\("(Server|Guild) only\."',
        r'embed = create_embed("\1 only.", color="warning", is_dm=False, is_system=False)\n            await interaction.followup.send(embed=embed',
        content
    )
    
    # Pattern 2: f-string messages - preserve the f-string
    content = re.sub(
        r'await interaction\.followup\.send\((f"[^"]+"), ephemeral=True\)',
        r'embed = create_embed(\1, color="info", is_dm=False, is_system=False)\n            await interaction.followup.send(embed=embed, ephemeral=True)',
        content
    )
    content = re.sub(
        r'await interaction\.response\.send_message\((f"[^"]+"), ephemeral=True\)',
        r'embed = create_embed(\1, color="info", is_dm=False, is_system=False)\n            await interaction.response.send_message(embed=embed, ephemeral=True)',
        content
    )
    
    # Pattern 3: Plain string messages
    content = re.sub(
        r'await interaction\.followup\.send\("([^"]+)", ephemeral=True\)',
        r'embed = create_embed("\1", color="info", is_dm=False, is_system=False)\n            await interaction.followup.send(embed=embed, ephemeral=True)',
        content
    )
    content = re.sub(
        r'await interaction\.response\.send_message\("([^"]+)", ephemeral=True\)',
        r'embed = create_embed("\1", color="info", is_dm=False, is_system=False)\n            await interaction.response.send_message(embed=embed, ephemeral=True)',
        content
    )
    
    # Pattern 4: Multi-line strings (handle carefully)
    # This is more complex and may need manual review
    
    return content

def process_file(filepath: Path) -> bool:
    """Process a single file. Returns True if changed."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()
        
        content = add_import(original)
        content = convert_message_sends(content)
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"[ERROR] Error processing {filepath.name}: {e}")
        return False

def main():
    """Process all cog files."""
    converted = []
    for filepath in sorted(COG_DIR.glob("*.py")):
        if filepath.name in EXCLUDED:
            continue
        
        if process_file(filepath):
            converted.append(filepath.name)
            print(f"[OK] Converted {filepath.name}")
    
    print(f"\nConverted {len(converted)} files: {', '.join(converted)}")
    print("\n[NOTE] Review files for:")
    print("  - DM messages (member.send) - should use is_dm=True")
    print("  - System messages (welcome/onboarding) - should use is_system=True")
    print("  - Appropriate colors (success/error/warning/info)")
    print("  - Multi-line strings may need manual adjustment")

if __name__ == "__main__":
    main()

