def contact_liaison(task_description: str) -> str:
    """
    Contact the Liaison AI agent to perform coding tasks, research, or answer complex questions.
    Use this tool whenever the user asks for something you cannot answer directly, 
    especially regarding software engineering, coding, or deep technical analysis.
    
    Args:
        task_description: A clear and detailed description of what the user wants to do or know.
    """
    from orchestrator.runner import run_workflow
    from gateway.model_registry import get_registry
    from resilience import CircuitBreakerRegistry
    from gateway.smart_gateway import SmartGateway
    from gateway.llm_client import LLMClient
    from agents.liaison import LiaisonAgent
    import os
    
    print(f"\n[Voice Agent -> Liaison] Delegating Task: {task_description}")
    
    try:
        registry = get_registry()
        circuit_breakers = CircuitBreakerRegistry()
        gateway = SmartGateway(registry, circuit_breakers)
        llm_client = LLMClient(smart_gateway=gateway)
        
        liaison = LiaisonAgent(
            registry=registry,
            gateway=gateway,
            circuit_breakers=circuit_breakers,
            llm_client=llm_client
        )
        
        # Determine intent (Conversational / System Command) vs (Technical / Research)
        result = liaison.run(task_description, session_messages=[])
        intent = result.data.get("intent_category") if result.data else None
        
        if intent in ["conversational", "system_command"]:
            print(f"\n[Liaison]: {result.message}")
            return result.message
            
        else:
            # Inject contents of any files mentioned in the prompt to allow direct editing
            import re
            import os
            potential_files = re.findall(r"[\w\.\-/]+\.(?:json|py|md|txt|csv|yaml|yml)", task_description)
            file_contents = ""
            for pf in set(potential_files):
                pf_path = os.path.abspath(pf)
                if os.path.isfile(pf_path):
                    try:
                        with open(pf_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            file_contents += f"\n\n--- Contents of {pf} ---\n{content}\n--- End of {pf} ---\n"
                    except Exception:
                        pass
            
            enhanced_description = task_description
            if file_contents:
                enhanced_description += f"\n\n[System Context: The following files were mentioned in the prompt. Here is their current content to help you edit them directly:]{file_contents}"

            # Full workflow (handled by SemanticRouter + ProjectExplorerAgent + CoderAgent etc.)
            result_workflow = run_workflow(task_description=enhanced_description, max_iterations=5)
            if result_workflow.success:
                files = list(result_workflow.final_code.keys()) if result_workflow.final_code else []
                for filename, content in (result_workflow.final_code or {}).items():
                    file_path = os.path.abspath(filename)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, "w", encoding="utf-8") as fh:
                        fh.write(content)
                        
                explanation = getattr(result_workflow, 'explanation', None)
                if not files and explanation:
                    res = f"Orchestrated task completed successfully:\n{explanation}"
                    print(f"\n[Orchestrator Workflow Text Response]: {res}")
                    return res
                else:
                    res = f"Complex coding/orchestrated workflow completed successfully. Files generated: {', '.join(files) if files else 'None'}."
                    if explanation:
                        res += f"\nExplanation:\n{explanation}"
                    print(f"\n[Orchestrator Workflow]: {res}")
                    return res
            else:
                res = f"Workflow finished with issues. Error: {result_workflow.error}"
                print(f"\n[Orchestrator Workflow Error]: {res}")
                return res
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        res = f"Error contacting Liaison: {str(e)}"
        print(f"\n[Liaison Error]: {res}")
        return res
