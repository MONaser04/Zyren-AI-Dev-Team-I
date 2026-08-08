import os
import re

exclude_dirs = {'.git', '.venv', '__pycache__', 'artifacts', 'reports'}
extensions = {'.py', '.md', '.toml', '.yaml', '.yml', '.json', '.example', '.txt', ''}

# We want to replace standalone "Zyren AI Dev-Team" with "Zyren AI Dev-Team AI Dev-Team"
# But avoid touching "# 🤖 Zyren: Autonomous AI Dev-Team"

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for file in files:
        if any(file.endswith(ext) for ext in extensions) or file in ['Makefile', 'LICENSE', 'Dockerfile.eval']:
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            orig_content = content
            
            # Temporarily protect the correct long header
            protected = content.replace("Zyren: Autonomous AI Dev-Team", "Zyren: Autonomous AI Dev-Team")
            
            # Now replace Zyren AI Dev-Team with Zyren AI Dev-Team AI Dev-Team
            protected = protected.replace("Zyren AI Dev-Team", "Zyren AI Dev-Team AI Dev-Team")
            protected = protected.replace("zyren-ai-dev-team", "zyren-ai-dev-team-ai-dev-team")
            
            # Unprotect
            new_content = protected.replace("Zyren: Autonomous AI Dev-Team", "Zyren: Autonomous AI Dev-Team")
            
            if new_content != orig_content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {filepath}")
