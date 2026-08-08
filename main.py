"""
AI Dev-Team — Interactive & CLI Main Entry Point
=================================================
Run this file to interact directly with your AI Software Agency.

Usage:
    python main.py                          # Interactive terminal prompt
    python main.py "Write a FastAPI CRUD"    # One-liner execution
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

# Enable INFO logging so the user can see Router model selections
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)

# Automatically add src directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from dotenv import load_dotenv

load_dotenv()

# Ensure stdout and stderr handle UTF-8 on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from orchestrator.runner import run_workflow


def get_liaison() -> "LiaisonAgent":
    from gateway.model_registry import get_registry
    from resilience import CircuitBreakerRegistry
    from gateway.smart_gateway import SmartGateway
    from agents.liaison import LiaisonAgent
    from gateway.llm_client import LLMClient
    import asyncio

    registry = get_registry()
    
    # 🔄 Dynamically discover all 100+ models from registered providers (Nvidia NIM, etc.)
    try:
        print("🔄 Discovering models from cloud providers... Please wait.")
        asyncio.run(registry.discover_all())
    except Exception as e:
        print(f"⚠️ Warning: Model discovery failed ({e}). Only default models are available.")

    circuit_breakers = CircuitBreakerRegistry()
    gateway = SmartGateway(registry, circuit_breakers)
    llm_client = LLMClient(smart_gateway=gateway)
    
    return LiaisonAgent(
        registry=registry,
        gateway=gateway,
        circuit_breakers=circuit_breakers,
        llm_client=llm_client
    )

def run_single_task(task_description: str, session_messages: list = None, liaison=None) -> None:
    """Execute a single software engineering task or handle chat/system command."""
    if session_messages is None:
        session_messages = []

    print("\n" + "-" * 65)
    print("🤖 Liaison is thinking...")
    
    # 1. Ask LiaisonAgent first
    try:
        if liaison is None:
            liaison = get_liaison()
        result = liaison.run(task_description, session_messages=session_messages)
    except Exception as e:
        print(f"\n❌ Liaison Error: {e}")
        return

    intent_category = result.data.get("intent_category") if result.data else None

    # 2. Conversational or System Commands are handled internally by Liaison/Executor
    if result.success and intent_category in ["conversational", "system_command"]:
        print(f"\n💬 Liaison: {result.message}")
        print("-" * 65)
        session_messages.append({"role": "user", "content": task_description})
        session_messages.append({"role": "assistant", "content": result.message})
        return
    elif not result.success:
        print(f"\n⚠️ {result.message}")
        print("-" * 65)
        return

    # 3. Handle Research Tasks
    if intent_category == "research":
        print("\n" + "=" * 65)
        print(f"🔬 Research Execution Mode")
        print(f"📋 Topic: {task_description}")
        print("=" * 65 + "\n")
        try:
            from gateway.model_registry import get_registry
            from resilience import CircuitBreakerRegistry
            from gateway.smart_gateway import SmartGateway
            from gateway.llm_client import LLMClient
            from agents.researcher import ResearcherAgent

            registry = get_registry()
            circuit_breakers = CircuitBreakerRegistry()
            gateway = SmartGateway(registry, circuit_breakers)
            llm_client = LLMClient(smart_gateway=gateway)
            researcher = ResearcherAgent(llm_client=llm_client)

            all_models = registry.list_all()
            active_models = registry.get_active_models()
            models_desc = "\n".join([
                f"- {m.display_name} (ID: {m.model_id}, Tier: {m.tier.value}, Provider: {m.provider}, Status: {m.status.value})"
                for m in all_models
            ]) if all_models else "- None currently registered"
            
            research_context = (
                "User inquiry from interactive loop.\n"
                f"System Model Registry Status (Total Models: {len(all_models)} | Active: {len(active_models)}):\n"
                f"Use this list to answer questions about models IN THIS PROJECT:\n"
                f"{models_desc}"
            )

            print("🤖 Researcher is digging into this...")
            notes = researcher.run(topic=task_description, context=research_context)
            print("\n✅ Research Complete:\n")
            for finding in notes.findings:
                print(f"- {finding}")
            print("\n💡 Conclusions / Recommendations:")
            for rec in notes.recommendations:
                print(f"- {rec}")
            print("\nSources:")
            for source in notes.sources:
                print(f"- {source}")
            print("-" * 65)
            session_messages.append({"role": "user", "content": task_description})
            session_messages.append({"role": "assistant", "content": f"[RESEARCH NOTES]\nFindings: {notes.findings}\nConclusions: {notes.recommendations}\nSources: {notes.sources}"})
            return
        except Exception as e:
            print(f"\n❌ Research Error: {e}")
            return

    # 4. Handle Coding Tasks
    import os
    import time
    import json as _json

    start_time = time.monotonic()

    if intent_category == "fast_code":
        # ⚡ Direct execution: 1 LLM call instead of 4+
        print("\n" + "=" * 65)
        print(f"⚡ Fast Execution Mode")
        print(f"📋 Task: {task_description}")
        print("=" * 65 + "\n")

        try:
            from gateway.model_registry import get_registry
            from resilience import CircuitBreakerRegistry
            from gateway.smart_gateway import SmartGateway
            from gateway.llm_client import LLMClient

            registry = get_registry()
            circuit_breakers = CircuitBreakerRegistry()
            gateway = SmartGateway(registry, circuit_breakers)
            llm_client = LLMClient(smart_gateway=gateway)

            fast_prompt = (
                "You are an expert coder. Generate the requested code.\n"
                "You MUST respond with ONLY a valid JSON object (no markdown, no backticks).\n"
                "Schema:\n"
                '{\n'
                '  "files": [\n'
                '    {"path": "filename.py", "content": "full file content here"}\n'
                '  ]\n'
                '}\n\n'
                f"Task: {task_description}"
            )

            raw_response = llm_client.complete_text(
                model="frontier",
                messages=[{"role": "user", "content": fast_prompt}],
                temperature=0.0,
                max_tokens=4096,
            )

            # Parse JSON from response
            import re
            json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if json_match:
                data = _json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in model response")

            files = data.get("files", [])
            if not files:
                raise ValueError("No files in response")

            elapsed = time.monotonic() - start_time
            print(f"\n" + "=" * 65)
            print(f"✅ TASK COMPLETED SUCCESSFULLY! ({elapsed:.1f}s)")
            print("=" * 65)

            files_written = []
            print("\n💻 Generated Code Files & Disk Operations:")
            for f in files:
                filename = f.get("path", "output.py")
                content = f.get("content", "")
                file_path = os.path.abspath(filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                try:
                    with open(file_path, "w", encoding="utf-8") as fh:
                        fh.write(content)
                    print(f"\n✅ Successfully written to disk: {file_path}")
                    files_written.append(file_path)
                except Exception as write_err:
                    print(f"\n❌ Failed to write {file_path}: {write_err}")

                print(f"--- 📄 Preview ---")
                preview_lines = content.splitlines()[:10]
                print("\n".join(preview_lines))
                if len(content.splitlines()) > 10:
                    print(f"... (and {len(content.splitlines()) - 10} more lines)")

            # Inject into session memory
            session_messages.append({"role": "user", "content": task_description})
            files_list = "\n".join(f"  - {fp}" for fp in files_written)
            pipeline_summary = (
                f"[SYSTEM CONTEXT — Fast Execution Result]\n"
                f"Task: {task_description}\n"
                f"Status: SUCCESS (completed in {elapsed:.1f}s)\n"
                f"Mode: Direct fast execution (single LLM call)\n"
                f"Files created/updated and saved to disk:\n{files_list}"
            )
            session_messages.append({"role": "assistant", "content": pipeline_summary})
            return

        except Exception as fast_err:
            print(f"\n⚠️ Fast execution failed ({fast_err}), falling back to full pipeline...")

    # ── Full pipeline for complex tasks (or fast-path fallback) ──
    print("\n" + "=" * 65)
    print(f"🚀 Running AI Dev-Team Pipeline")
    print(f"📋 Task: {task_description}")
    print("=" * 65 + "\n")

    try:
        result_workflow = run_workflow(
            task_description=task_description,
            max_iterations=5,
        )

        elapsed = time.monotonic() - start_time
        print("\n" + "=" * 65)
        if result_workflow.success:
            print(f"✅ TASK COMPLETED SUCCESSFULLY! ({elapsed:.1f}s)")
        else:
            print(f"⚠️ TASK FINISHED WITH ISSUES ({elapsed:.1f}s)")
        print("=" * 65)

        # Print outputs and write files to disk
        files_written = []
        if result_workflow.final_code:
            print("\n💻 Generated Code Files & Disk Operations:")
            for filename, content in result_workflow.final_code.items():
                file_path = os.path.abspath(filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"\n✅ Successfully written to disk: {file_path}")
                    files_written.append(file_path)
                except Exception as write_err:
                    print(f"\n❌ Failed to write {file_path}: {write_err}")

                print(f"--- 📄 Preview ---")
                preview_lines = content.splitlines()[:10]
                print("\n".join(preview_lines))
                if len(content.splitlines()) > 10:
                    print(f"... (and {len(content.splitlines()) - 10} more lines)")
        
        if result_workflow.error:
            print(f"\n❌ Error Details: {result_workflow.error}")
            
        if result_workflow.explanation:
            print(f"\n💬 Agent Reply:\n{result_workflow.explanation}")

        # Inject pipeline results into session memory
        session_messages.append({"role": "user", "content": task_description})
        if files_written:
            files_list = "\n".join(f"  - {fp}" for fp in files_written)
            pipeline_summary = (
                f"[SYSTEM CONTEXT — Pipeline Result]\n"
                f"Task: {task_description}\n"
                f"Status: {'SUCCESS' if result_workflow.success else 'FINISHED WITH ISSUES'}\n"
                f"Completed in: {elapsed:.1f}s\n"
                f"Files created/updated and saved to disk:\n{files_list}\n"
                f"Workflow ID: {result_workflow.workflow_id}"
            )
        else:
            pipeline_summary = (
                f"[SYSTEM CONTEXT — Pipeline Result]\n"
                f"Task: {task_description}\n"
                f"Status: {'SUCCESS' if result_workflow.success else 'FAILED'}\n"
                f"No files were generated."
            )
            if result_workflow.error:
                pipeline_summary += f"\nError: {result_workflow.error}"
        session_messages.append({"role": "assistant", "content": pipeline_summary})

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Error during execution: {e}")
        session_messages.append({"role": "user", "content": task_description})
        session_messages.append({"role": "assistant", "content": f"[SYSTEM CONTEXT] Pipeline crashed with error: {e}"})


def interactive_loop() -> None:
    """Interactive loop for chatting/submitting tasks to the AI Dev-Team."""
    print("=" * 65)
    print("🤖 Welcome to AI Dev-Team Autonomous Agency!")
    print("Type your coding request below (or 'exit' / 'q' to quit).")
    print("=" * 65)

    session_messages = []
    # Create liaison ONCE and reuse it for the entire session
    try:
        liaison = get_liaison()
    except Exception as e:
        print(f"❌ Failed to initialize Liaison: {e}")
        liaison = None

    while True:
        try:
            print("\n" + "-" * 65)
            user_input = input("💬 Prompt: > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("👋 Goodbye!")
                break
                
            if user_input.lower() == "calibrate":
                print("⏳ Running calibration queue synchronously. This will process all pending model evaluations...")
                import asyncio
                from gateway.routing.calibration_engine import CalibrationEngine
                
                async def run_sync_calibration():
                    engine = CalibrationEngine._instance
                    if not engine:
                        print("❌ Calibration Engine not found.")
                        return
                        
                    if not engine._worker_task or engine._worker_task.done():
                        engine._worker_task = asyncio.create_task(engine._worker_loop())
                        
                    all_models = engine.registry.list_all()
                    print(f"📥 Enqueueing all {len(all_models)} models for evaluation...")
                    for model in all_models:
                        engine.enqueue(model.model_id)
                        
                    while not engine.queue.empty():
                        print(f"⏳ Waiting for calibration tasks to complete... {engine.queue.qsize()} remaining.")
                        await asyncio.sleep(10)
                        
                    print("✅ All pending calibration tasks completed!")
                    
                asyncio.run(run_sync_calibration())
                continue

            # Intercept voice chat commands
            voice_triggers = ["voice", "voice chat", "افتح الvoice chat", "start voice", "افتح الفويس"]
            if any(trigger in user_input.lower() for trigger in voice_triggers):
                print("🎤 Starting Voice Agent Spokesperson...")
                import asyncio
                from agents.voice_agent import main as voice_main
                asyncio.run(voice_main())
                continue

            run_single_task(user_input, session_messages, liaison=liaison)

        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            break


def main() -> None:
    if len(sys.argv) > 1:
        if sys.argv[1].lower() == "voice":
            print("🎤 Starting Voice Agent Spokesperson...")
            import asyncio
            from agents.voice_agent import main as voice_main
            asyncio.run(voice_main())
            return
            
        # CLI Argument provided: python main.py "Write a fibonacci function"
        task = " ".join(sys.argv[1:])
        run_single_task(task)
    else:
        # No args provided: Start interactive prompt
        interactive_loop()


if __name__ == "__main__":
    main()
