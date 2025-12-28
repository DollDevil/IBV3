#!/usr/bin/env python3
"""Fix invalid 'return embed = create_embed' syntax."""
import re
from pathlib import Path

COG_DIR = Path("islabot/cogs")

def fix_file(filepath: Path) -> bool:
    """Fix return statements. Returns True if changed."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # Fix: return embed = create_embed(...) -> embed = create_embed(...); return await ...
        # Pattern: return embed = create_embed(...) followed by await interaction.followup.send
        content = re.sub(
            r'return embed = create_embed\(([^)]+)\)\s*\n\s*await interaction\.followup\.send\(embed=embed',
            r'embed = create_embed(\1)\n            return await interaction.followup.send(embed=embed',
            content
        )
        content = re.sub(
            r'return embed = create_embed\(([^)]+)\)\s*\n\s*await interaction\.response\.send_message\(embed=embed',
            r'embed = create_embed(\1)\n            return await interaction.response.send_message(embed=embed',
            content
        )
        
        # Fix standalone return embed = create_embed (no await on next line)
        content = re.sub(
            r'return embed = create_embed\(([^)]+)\)',
            r'embed = create_embed(\1)\n            return await interaction.response.send_message(embed=embed, ephemeral=True)',
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
    fixed = []
    for filepath in sorted(COG_DIR.glob("*.py")):
        if fix_file(filepath):
            fixed.append(filepath.name)
            print(f"Fixed {filepath.name}")
    
    print(f"\nFixed {len(fixed)} files")

if __name__ == "__main__":
    main()

