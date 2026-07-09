from enum import StrEnum

class RebuttalOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"

print(repr(RebuttalOutcome.ACCEPTED))
print(repr(RebuttalOutcome.ACCEPTED.value))
print(f"expected={RebuttalOutcome.ACCEPTED.value}")
