filepath = 'tests/test_orchestrator.py'
with open(filepath, 'r') as f:
    content = f.read()

content = content.replace('"orchestrator.graph.SemanticRouter.classify"', '"orchestrator.semantic_router.SemanticRouter.classify"')

with open(filepath, 'w') as f:
    f.write(content)
print("Done")
