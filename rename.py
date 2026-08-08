import os
import re

directories_to_scan = ['.']
extensions = {'.py', '.md', '.toml', '.yaml', '.yml', '.json', '.example', '.txt'}

# Prevent touching .git or .venv
exclude_dirs = {'.git', '.venv', '__pycache__', 'artifacts', 'reports'}

replacements = [
    (r"Zyren", r"Zyren"),
    (r"Zyren", r"Zyren"),
    (r"Zyren", r"Zyren"),
    (r"zyren", r"zyren"),
    (r"zyren", r"zyren"),
    (r"A Multi-Agent SDLC Engine — self-hosted Zyren team with grounded verification", r"A Multi-Agent SDLC Engine — self-hosted Zyren team with grounded verification"),
]

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for file in files:
        if any(file.endswith(ext) for ext in extensions) or file in ['.env.example', 'Makefile']:
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            new_content = content
            for old, new in replacements:
                # We do regex replace with case sensitivity as defined in the replacements
                new_content = re.sub(old, new, new_content)
            
            # Special case for headers in README and reports
            new_content = new_content.replace("# 🤖 Zyren: Autonomous AI Dev-Team", "# 🤖 Zyren: Autonomous AI Dev-Team: Autonomous Zyren")
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {filepath}")
