#!/usr/bin/env python3
"""
Automated script to convert all plain text messages to embeds.
Preserves all information and context.
"""
import re
import os
from pathlib import Path

# Patterns to identify and convert
PATTERNS = [
    # Server-only messages (warning color)
    (r'await interaction\.response\.send_message\("Server only\."', 
     'embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)\n            await interaction.response.send_message(embed=embed'),
    
    (r'await interaction\.followup\.send\("Server only\."', 
     'embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)\n            await interaction.followup.send(embed=embed'),
    
    (r'await interaction\.response\.send_message\("Guild only\."', 
     'embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)\n            await interaction.response.send_message(embed=embed'),
    
    (r'await interaction\.followup\.send\("Guild only\."', 
     'embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)\n            await interaction.followup.send(embed=embed'),
    
    # Generic followup sends with f-strings or plain strings
    (r'await interaction\.followup\.send\(f"([^"]+)"', 
     r'embed = create_embed(f"\1", color="info", is_dm=False, is_system=False)\n            await interaction.followup.send(embed=embed'),
    
    (r'await interaction\.followup\.send\("([^"]+)"', 
     r'embed = create_embed("\1", color="info", is_dm=False, is_system=False)\n            await interaction.followup.send(embed=embed'),
    
    # Response sends
    (r'await interaction\.response\.send_message\(f"([^"]+)"', 
     r'embed = create_embed(f"\1", color="info", is_dm=False, is_system=False)\n            await interaction.response.send_message(embed=embed'),
    
    (r'await interaction\.response\.send_message\("([^"]+)"', 
     r'embed = create_embed("\1", color="info", is_dm=False, is_system=False)\n            await interaction.response.send_message(embed=embed'),
]

# Files to process
COG_DIR = Path("islabot/cogs")

def needs_import(content: str) -> bool:
    """Check if file needs the embed_utils import."""
    return "from utils.embed_utils import create_embed" not in content

def add_import(content: str) -> str:
    """Add the embed_utils import if needed."""
    if needs_import(content):
        # Find the last import statement
        lines = content.split('\n')
        last_import_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('from ') or line.strip().startswith('import '):
                last_import_idx = i
        
        if last_import_idx >= 0:
            lines.insert(last_import_idx + 1, 'from utils.embed_utils import create_embed')
        else:
            # No imports found, add at top after __future__
            if lines[0].startswith('from __future__'):
                lines.insert(1, 'from utils.embed_utils import create_embed')
            else:
                lines.insert(0, 'from utils.embed_utils import create_embed')
        
        return '\n'.join(lines)
    return content

def convert_file(filepath: Path) -> tuple[bool, str]:
    """
    Convert a single file.
    Returns (changed, message)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        content = add_import(content)
        
        # Apply conversions
        changes_made = False
        for pattern, replacement in PATTERNS:
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                changes_made = True
                content = new_content
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, f"Converted {filepath.name}"
        
        return False, f"No changes needed in {filepath.name}"
    
    except Exception as e:
        return False, f"Error processing {filepath.name}: {e}"

def main():
    """Process all cog files."""
    converted = []
    errors = []
    skipped = []
    
    for filepath in sorted(COG_DIR.glob("*.py")):
        if filepath.name in ['__init__.py', 'moderation.py', 'config_group.py']:
            skipped.append(filepath.name)
            continue
        
        changed, message = convert_file(filepath)
        if changed:
            converted.append(filepath.name)
            print(f"✓ {message}")
        elif "Error" in message:
            errors.append(message)
            print(f"✗ {message}")
        else:
            print(f"○ {message}")
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Converted: {len(converted)} files")
    print(f"  Skipped: {len(skipped)} files (already done or excluded)")
    print(f"  Errors: {len(errors)} files")
    print(f"{'='*60}")
    
    if converted:
        print(f"\nConverted files: {', '.join(converted)}")
    if errors:
        print(f"\nErrors: {', '.join(errors)}")

if __name__ == "__main__":
    main()

