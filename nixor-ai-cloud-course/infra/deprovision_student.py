#!/usr/bin/env python3
"""
deprovision_student.py — tear down one student's sandbox by deleting their
resource group (which deletes everything inside it). Used at program end and by
the instructor dashboard's "tear down all" action.

TODO for Claude Code:
  • Also remove the student's guest account / role assignment if desired.
  • Add a --all flag that finds every RG tagged course=nixor-ai-cloud and deletes them.
"""
import argparse
import subprocess


def deprovision(team: str) -> None:
    rg_name = f"rg-nixor-{team}"
    subprocess.run(
        ["az", "group", "delete", "--name", rg_name, "--yes", "--no-wait"],
        check=True,
    )
    print(f"deletion started for {rg_name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--team", required=True)
    deprovision(p.parse_args().team)
