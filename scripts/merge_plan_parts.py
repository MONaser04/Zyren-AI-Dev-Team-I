#!/usr/bin/env python3
"""Merge all plan parts into COMPREHENSIVE_MASTER_PLAN.md"""

import os
from pathlib import Path

# Order of parts - matching actual filenames created
parts = [
    "part_01_executive_summary.md",
    "part_02_gap_analysis.md",
    "part_03_phase_0_1_model_registry.md",
    "part_04_phases_2_3_researcher_gateway.md",
    "part_05_phase_4_agent_roster.md",
    "part_06_phase_5_production.md",
    "part_07_phase_6_evaluation.md",
    "part_08_phase_7_self_improvement.md",
    "part_09_execution_order.md",
]

parts_dir = Path("temp_plan_parts")
output_path = Path("docs/COMPREHENSIVE_MASTER_PLAN.md")

# Read and merge
merged = []
for part_file in parts:
    part_path = parts_dir / part_file
    if part_path.exists():
        content = part_path.read_text(encoding="utf-8")
        merged.append(content)
        print(f"✅ Merged: {part_file}")
    else:
        print(f"❌ Missing: {part_file}")

# Write final document
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("\n\n---\n\n".join(merged), encoding="utf-8")
print(f"\n✅ Created: {output_path}")
print(f"📄 Total parts merged: {len([p for p in parts if (parts_dir / p).exists()])}")