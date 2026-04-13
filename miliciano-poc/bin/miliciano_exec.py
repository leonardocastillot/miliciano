#!/usr/bin/env python3
import sys

from miliciano_agent import run_execution, run_mission, run_reasoning, run_shell
from miliciano_ui import banner, response_box, response_meta_line


def cmd_shell():
    banner()
    run_shell()


def cmd_think(prompt):
    forced_role = None
    raw_prompt = prompt.strip()
    if raw_prompt.startswith("--fast "):
        forced_role = "fast"
        raw_prompt = raw_prompt[7:].strip()
    elif raw_prompt.startswith("--reasoning "):
        forced_role = "reasoning"
        raw_prompt = raw_prompt[12:].strip()
    rc, result = run_reasoning(raw_prompt, forced_role=forced_role)
    response_meta_line(result, mode=forced_role or "reasoning")
    if result["content"]:
        response_box(result["content"])
    sys.exit(rc)


def cmd_exec(prompt):
    rc, result = run_execution(prompt, source="exec", check_policy=True)
    response_meta_line(result, mode="exec")
    if result["content"]:
        response_box(result["content"], title="OpenClaw")
    sys.exit(rc)


def cmd_mission(prompt):
    rc, result = run_mission(prompt)
    planner = result.get("planner") or {}
    executor = result.get("executor") or {}
    if planner.get("content"):
        response_meta_line(planner, mode="plan")
        response_box(planner["content"], title="Plan")
    if executor.get("content"):
        response_meta_line(executor, mode="exec")
        response_box(executor["content"], title="Ejecución")
    sys.exit(rc)
