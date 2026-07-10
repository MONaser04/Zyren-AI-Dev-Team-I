import os
from dotenv import load_dotenv
load_dotenv()

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
src_path = PROJECT_ROOT / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.orchestrator.runner import run_workflow

# تأكد من وضع مفاتيح الـ API الخاصة بك في ملف .env
# مثلاً: OPENAI_API_KEY أو أي موديل تستخدمه عبر LiteLLM

def main():
    task = "Write a Python function that calculates the Fibonacci sequence up to N, along with a comprehensive pytest suite."
    
    print("Starting AI Dev-Team Workflow...")
    
    # تشغيل النظام (سيبدأ Orchestrator بتوجيه المهمة للـ Coder والـ Tester والـ Critic)
    result = run_workflow(
        task_description=task,
        language="python",
        max_iterations=3
    )
    
    print(f"\nSuccess: {result.success}")
    print(f"Iterations took: {result.iterations}")
    print(f"Events recorded: {result.events_count}")
    
    if result.success:
        print("\nFinal Code Produced:")
        for filename, content in result.final_code.items():
            print(f"\n--- {filename} ---")
            print(content)
    else:
        print(f"\nFailed with error: {result.error}")

if __name__ == "__main__":
    main()
