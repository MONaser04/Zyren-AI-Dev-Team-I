import json
import os
from pathlib import Path
from typing import List

# Path to the persistent memory file
MEMORY_FILE = Path(os.getcwd()) / "memory.json"

class MemoryManager:
    """Manages persistent memory facts (User Profile & Preferences) in memory.json."""
    
    @staticmethod
    def load_memory() -> List[str]:
        """Loads all persistent memory facts."""
        if not MEMORY_FILE.exists():
            return []
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("facts", [])
        except Exception:
            return []

    @staticmethod
    def update_facts(new_facts: List[str], facts_to_remove: List[str] = None) -> None:
        """Updates persistent memory by removing old facts and appending new ones."""
        facts = MemoryManager.load_memory()
        
        if facts_to_remove:
            facts = [f for f in facts if f not in facts_to_remove]
        
        if new_facts:
            # Add only unique facts
            for fact in new_facts:
                if fact not in facts:
                    facts.append(fact)
                
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({"facts": facts}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to write memory: {e}")
