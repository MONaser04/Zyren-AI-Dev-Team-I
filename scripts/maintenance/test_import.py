import sys
sys.path.insert(0, "D:\\Downloads\\AI_DEV_TEAM\\src")
from contracts.schemas import RebuttalOutcome

print(f"Name: {RebuttalOutcome.ACCEPTED.name}")
print(f"Value: {RebuttalOutcome.ACCEPTED.value}")
