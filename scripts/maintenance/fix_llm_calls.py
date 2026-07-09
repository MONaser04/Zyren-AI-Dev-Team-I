import os
import glob
import re

files_to_check = glob.glob('src/agents/*.py') + ['src/orchestrator/semantic_router.py']

for filepath in files_to_check:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    if 'prompt=prompt,' in content:
        # We replace `prompt=prompt,` with `messages=[{"role": "user", "content": prompt}],`
        new_content = content.replace('prompt=prompt,', 'messages=[{"role": "user", "content": prompt}],')
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Patched {filepath}")
