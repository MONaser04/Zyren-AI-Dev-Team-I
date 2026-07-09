import os
import glob
import re

agent_files = glob.glob('src/agents/*.py')
for filepath in agent_files:
    if filepath.endswith('base.py') or filepath.endswith('__init__.py') or filepath.endswith('coder.py') or filepath.endswith('critic.py') or filepath.endswith('tester.py'):
        continue
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Extract role from `role: str = "..."` or `role = "..."`
    role_match = re.search(r'role:\s*str\s*=\s*"([^"]+)"', content)
    if not role_match:
        role_match = re.search(r'role\s*=\s*"([^"]+)"', content)
    
    if role_match:
        role = role_match.group(1)
        
        # Replace the __init__ signature and body
        pattern = r'def __init__\(self, llm_client: LLMClient(?:[^,]*)?(?:, model: str = "[^"]+")?\):\s+self\.llm_client = llm_client\s+self\.model = model'
        replacement = f'''def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "{role}-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="{role}", llm_client=llm_client)
        self.model = model'''
        
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Patched {filepath}")
        else:
            print(f"Could not patch {filepath} (pattern not found)")
