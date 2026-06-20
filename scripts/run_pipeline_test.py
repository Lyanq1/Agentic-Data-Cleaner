#!/usr/bin/env python3
"""Automated pipeline test runner for Agentic Data Cleaner.

This script runs the cleaning pipeline end-to-end against a running FastAPI server.
It automates:
1. File upload
2. Clarification answering (auto-selects recommended or first option)
3. Execution plan approval
4. Final validation review approval
5. Cleaned dataset download (XLSX)
6. Generation of Markdown and JSON reports
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
import httpx

# Default configurations
DEFAULT_API_URL = "http://localhost:8000/api/v1"
DEFAULT_OUTPUT_DIR = "./test_results"


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Automated pipeline test runner for Agentic Data Cleaner."
    )
    parser.add_argument(
        "--file", "-f",
        required=True,
        help="Path to the dirty dataset file (CSV, XLSX, etc.)"
    )
    parser.add_argument(
        "--ground-truth", "-g",
        help="Optional path to the clean ground-truth dataset file (for F1 evaluation)"
    )
    parser.add_argument(
        "--prompt", "-p",
        default="",
        help="Optional cleaning instructions/prompt for the agent"
    )
    parser.add_argument(
        "--answers-file", "-a",
        help="Optional JSON file containing answers to expected clarifications (e.g. {'null.Q1_strategy': 'Option A'})"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to save test results (default: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--api-url", "-u",
        default=DEFAULT_API_URL,
        help=f"FastAPI pipeline API v1 URL (default: {DEFAULT_API_URL})"
    )
    return parser.parse_args()


def load_preset_answers(filepath):
    if not filepath:
        return {}
    path = Path(filepath)
    if not path.exists():
        print(f"[-] Answers file not found: {filepath}", file=sys.stderr)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[-] Failed to parse answers file: {e}", file=sys.stderr)
        return {}


def resolve_clarifications(clarifications_dict, preset_answers):
    """Auto-resolve clarifications by choosing preset answers, recommended options, or the first option."""
    answers = {}
    
    for category in ["null", "duplicate", "typecast"]:
        category_data = clarifications_dict.get(category) or {}
        for q_key, q_val in category_data.items():
            if not q_val:
                continue
                
            full_key = f"{category}.{q_key}"
            question_text = q_val.get("question", "")
            options = q_val.get("options") or []
            existing_answer = q_val.get("answer")
            
            # Skip if already answered
            if existing_answer is not None:
                continue
                
            selected_option = None
            
            # 1. Check if we have a preset answer
            if full_key in preset_answers:
                selected_option = preset_answers[full_key]
                print(f"[+] Using preset answer for {full_key}: '{selected_option}'")
            else:
                # 2. Look for an option marked as (Recommended) or containing Recommended
                for opt in options:
                    if "Recommended" in opt or "(Recommended)" in opt:
                        selected_option = opt
                        print(f"[+] Auto-selected recommended option for {full_key}: '{selected_option}'")
                        break
                        
                # 3. Fallback to the first option
                if not selected_option and options:
                    selected_option = options[0]
                    print(f"[+] Fallback to first option for {full_key}: '{selected_option}'")
                    
            if selected_option:
                answers[full_key] = selected_option
            else:
                print(f"[-] WARNING: Could not find options or answers for {full_key}", file=sys.stderr)
                
    return answers


def get_terminal_logs(state):
    """Extract and merge agent logs from state, sorted chronologically."""
    agent_logs = []
    backend_logs = state.get("agent_logs") or {}
    
    if isinstance(backend_logs, dict) and not isinstance(backend_logs, list):
        for val in backend_logs.values():
            if isinstance(val, dict) and isinstance(val.get("logs"), list):
                agent_logs.extend(val["logs"])
    elif isinstance(backend_logs, list):
        agent_logs.extend(backend_logs)
        
    agent_logs.sort(key=lambda x: x.get("timestamp") or 0.0)
    return agent_logs


def run_test():
    args = parse_arguments()
    
    # 1. Validate files
    dirty_path = Path(args.file)
    if not dirty_path.exists():
        print(f"[-] Error: Dirty dataset file not found at {dirty_path}", file=sys.stderr)
        sys.exit(1)
        
    gt_path = None
    if args.ground_truth:
        gt_path = Path(args.ground_truth)
        if not gt_path.exists():
            print(f"[-] Error: Ground truth file not found at {gt_path}", file=sys.stderr)
            sys.exit(1)
            
    preset_answers = load_preset_answers(args.answers_file)
    
    print(f"[*] Starting automated pipeline test...")
    print(f"    - Input file:  {dirty_path.name}")
    if gt_path:
        print(f"    - Ground truth: {gt_path.name}")
    print(f"    - Prompt:      '{args.prompt}'")
    print(f"    - Target URL:   {args.api_url}")
    
    # 2. Upload and start the run
    # Set up client and execute POST /pipeline/run
    client = httpx.Client(timeout=120.0)
    try:
        files = {
            "file": (dirty_path.name, open(dirty_path, "rb"), "application/octet-stream")
        }
        if gt_path:
            files["clean_file"] = (gt_path.name, open(gt_path, "rb"), "application/octet-stream")
            
        data = {
            "user_prompt": args.prompt
        }
        
        response = client.post(f"{args.api_url}/pipeline/run", files=files, data=data)
        if response.status_code != 200:
            print(f"[-] Failed to start pipeline: HTTP {response.status_code} - {response.text}", file=sys.stderr)
            sys.exit(1)
            
        res_data = response.json()
        run_id = res_data["run_id"]
        print(f"[+] Pipeline started successfully! Run ID: {run_id}")
        
    except Exception as e:
        print(f"[-] Connection to FastAPI server failed: {e}", file=sys.stderr)
        print("    Please ensure the server is running (e.g. using 'make run' or 'uvicorn app.main:app').", file=sys.stderr)
        sys.exit(1)
        
    # 3. Polling loop
    start_time = time.time()
    plan_approved = False
    review_approved = False
    last_step = None
    seen_log_timestamps = set()
    
    print("[*] Polling pipeline execution status...")
    
    try:
        while True:
            # Fetch current state
            state_response = client.get(f"{args.api_url}/pipeline/{run_id}/state")
            if state_response.status_code != 200:
                print(f"[-] Failed to poll state: HTTP {state_response.status_code}", file=sys.stderr)
                time.sleep(2)
                continue
                
            state = state_response.json()
            
            # Check for global errors
            errors = state.get("errors") or []
            if errors:
                print(f"\n[-] Pipeline encountered fatal error(s):", file=sys.stderr)
                for err in errors:
                    print(f"    - {err}", file=sys.stderr)
                sys.exit(2)
                
            # Log step changes
            current_step = state.get("current_step") or "initializing"
            if current_step != last_step:
                print(f"\n[+] Active Stage: {current_step.upper()}")
                last_step = current_step
                
            # Print new logs from agents
            logs = get_terminal_logs(state)
            for log in logs:
                ts = log.get("timestamp") or 0.0
                if ts not in seen_log_timestamps:
                    seen_log_timestamps.add(ts)
                    agent = log.get("agent", "system")
                    msg = log.get("message", "")
                    level = log.get("level", "info")
                    prefix = f"[{agent}]"
                    if level != "info":
                        prefix += f" [{level.upper()}]"
                    print(f"    {prefix:22} {msg}")
                    
            # Parse checkpoints and routing
            next_node = state.get("next_node") or []
            if isinstance(next_node, str):
                next_node = [next_node]
                
            completed_steps = state.get("completed_steps") or []
            is_at_end = len(next_node) == 0 or "__end__" in next_node
            is_reporting_completed = current_step == "reporting" or "reporting" in completed_steps
            
            # Check completed success
            if is_at_end and is_reporting_completed:
                print("\n[+] Pipeline execution completed successfully!")
                break
                
            # A. Check for Clarifications (input_validator needs human input)
            val_result = state.get("input_validation_result") or {}
            is_needs_clarification = val_result.get("status") == "needs_clarification"
            
            # Check if there are unanswered questions
            has_unanswered = False
            clarifications = val_result.get("clarifications") or {}
            for cat in ["null", "duplicate", "typecast"]:
                cat_data = clarifications.get(cat) or {}
                for q in cat_data.values():
                    if q and q.get("answer") is None:
                        has_unanswered = True
                        break
                        
            if is_needs_clarification and has_unanswered:
                print("\n[*] Input validation requires clarifications. Auto-resolving...")
                answers = resolve_clarifications(clarifications, preset_answers)
                if answers:
                    resolve_resp = client.post(
                        f"{args.api_url}/pipeline/{run_id}/resolve",
                        json={"answers": answers}
                    )
                    if resolve_resp.status_code == 200:
                        print("[+] Clarifications submitted successfully.")
                    else:
                        print(f"[-] Failed to submit clarifications: HTTP {resolve_resp.status_code} - {resolve_resp.text}", file=sys.stderr)
                        sys.exit(3)
                else:
                    print("[-] Error: Needs clarification but no answers could be generated.", file=sys.stderr)
                    sys.exit(3)
                    
            # B. Check for Execution Plan Approval (HITL before workers)
            has_plan = state.get("execution_plan") is not None
            is_at_worker = any(node in ["deduplication", "null_handling", "type_casting"] for node in next_node)
            
            if has_plan and is_at_worker and not plan_approved:
                print("\n[*] Execution plan generated. Auto-approving...")
                approve_resp = client.post(f"{args.api_url}/pipeline/{run_id}/approve_plan")
                if approve_resp.status_code == 200:
                    print("[+] Execution plan approved. Processing dataset workers...")
                    plan_approved = True
                else:
                    print(f"[-] Failed to approve plan: HTTP {approve_resp.status_code}", file=sys.stderr)
                    sys.exit(4)
                    
            # C. Check for Final Validation Review (HITL before report_agent)
            is_at_report = "report_agent" in next_node
            if is_at_report and not review_approved:
                print("\n[*] Workers validation gates passed. Auto-approving final review...")
                approve_resp = client.post(f"{args.api_url}/pipeline/{run_id}/approve_plan")
                if approve_resp.status_code == 200:
                    print("[+] Final review approved. Generating report...")
                    review_approved = True
                else:
                    print(f"[-] Failed to approve final review: HTTP {approve_resp.status_code}", file=sys.stderr)
                    sys.exit(4)
                    
            time.sleep(1.5)
            
    except KeyboardInterrupt:
        print("\n[-] Testing execution interrupted by user.")
        sys.exit(130)
        
    elapsed_time = time.time() - start_time
    print(f"\n[*] Run completed in {elapsed_time:.2f} seconds.")
    
    # 4. Download finalized XLSX file
    output_dir = Path(args.output_dir) / f"run_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    xlsx_path = output_dir / "cleaned_dataset.xlsx"
    print(f"[*] Downloading cleaned dataset...")
    try:
        dl_resp = client.get(f"{args.api_url}/pipeline/{run_id}/download?format=xlsx")
        if dl_resp.status_code == 200:
            xlsx_path.write_bytes(dl_resp.content)
            print(f"[+] Cleaned file saved to: {xlsx_path.resolve()}")
        else:
            print(f"[-] Failed to download XLSX file: HTTP {dl_resp.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"[-] Error downloading file: {e}", file=sys.stderr)
        
    # 5. Generate reports
    # Request latest state again for absolute accuracy
    state = client.get(f"{args.api_url}/pipeline/{run_id}/state").json()
    
    f1_metrics = state.get("f1_metrics")
    token_metrics = state.get("token_metrics") or {}
    
    # Write JSON report
    report_json_path = output_dir / "test_report.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    print(f"[+] Structured JSON report saved to: {report_json_path.resolve()}")
    
    # Generate Markdown report
    report_md_path = output_dir / "test_report.md"
    generate_markdown_report(report_md_path, run_id, dirty_path.name, elapsed_time, state, f1_metrics, token_metrics)
    print(f"[+] Human-readable report saved to: {report_md_path.resolve()}")
    
    print("\n" + "="*50)
    print(f"TEST SUMMARY FOR RUN: {run_id}")
    print("="*50)
    print(f"Status:       Success")
    print(f"Output File:  {xlsx_path.name}")
    print(f"Time Taken:   {elapsed_time:.1f}s")
    if token_metrics:
        print(f"LLM Tokens:   {token_metrics.get('total_tokens', 0)} total "
              f"({token_metrics.get('prompt_tokens', 0)} prompt, "
              f"{token_metrics.get('completion_tokens', 0)} completion)")
              
    if f1_metrics:
        print("\nGround Truth Evaluation:")
        print(f"  Accuracy:   {f1_metrics.get('cell_accuracy', 0.0) * 100:.2f}%")
        print(f"  Precision:  {f1_metrics.get('error_correction_precision', 0.0) * 100:.2f}%")
        print(f"  Recall:     {f1_metrics.get('error_correction_recall', 0.0) * 100:.2f}%")
        print(f"  F1 Score:   {f1_metrics.get('f1_score', 0.0):.4f}")
    print("="*50)
    
    client.close()


def generate_markdown_report(filepath, run_id, filename, duration, state, f1_metrics, token_metrics):
    """Generates a beautiful human-readable markdown report of the cleaning execution."""
    
    report = []
    report.append(f"# Dataset Cleaning Execution Report - Run `{run_id}`")
    report.append("")
    report.append("## 📊 Run Summary")
    report.append("")
    
    # Summary Table
    report.append("| Metric | Value |")
    report.append("| :--- | :--- |")
    report.append(f"| **Run ID** | `{run_id}` |")
    report.append(f"| **Original Dataset** | `{filename}` |")
    report.append(f"| **Status** | `Completed` |")
    report.append(f"| **Total Duration** | {duration:.1f} seconds |")
    
    if token_metrics:
        report.append(f"| **LLM Tokens Used** | {token_metrics.get('total_tokens', 0):,} |")
        report.append(f"| **Prompt / Completion Tokens** | {token_metrics.get('prompt_tokens', 0):,} / {token_metrics.get('completion_tokens', 0):,} |")
        
    if f1_metrics:
        report.append(f"| **F1 Score** | `{f1_metrics.get('f1_score', 0.0):.4f}` |")
        report.append(f"| **Cell-level Accuracy** | `{f1_metrics.get('cell_accuracy', 0.0) * 100:.2f}%` |")
        
    report.append("")
    
    # Ground Truth Evaluation section
    if f1_metrics:
        report.append("## 🎯 Ground Truth Evaluation (Cell-level)")
        report.append("")
        report.append("Comparing cleaned dataset against the provided ground truth dataset:")
        report.append("")
        report.append("| Evaluation Metric | Value | Description |")
        report.append("| :--- | :---: | :--- |")
        report.append(f"| **F1-Score** | **{f1_metrics.get('f1_score', 0.0):.4f}** | Harmonic mean of precision and recall |")
        report.append(f"| **Precision** | **{f1_metrics.get('error_correction_precision', 0.0) * 100:.2f}%** | Percentage of changes made that were correct |")
        report.append(f"| **Recall** | **{f1_metrics.get('error_correction_recall', 0.0) * 100:.2f}%** | Percentage of actual dirty cells corrected |")
        report.append(f"| **Accuracy** | **{f1_metrics.get('cell_accuracy', 0.0) * 100:.2f}%** | Match rate across all cells |")
        report.append("")
        
        report.append("### Confusion Matrix Statistics:")
        report.append(f"- **True Positives (TP)**: {f1_metrics.get('tp', 0)} (Cells dirty in input, and cleaned correctly)")
        report.append(f"- **False Positives (FP)**: {f1_metrics.get('fp', 0)} (Cells modified to incorrect value)")
        report.append(f"- **False Negatives (FN)**: {f1_metrics.get('fn', 0)} (Cells dirty in input, but left unchanged or cleaned incorrectly)")
        report.append(f"- **Total cells evaluated**: {f1_metrics.get('total_cells_evaluated', 0):,}")
        report.append("")
        
    # Planned execution steps
    plan = state.get("execution_plan")
    if plan:
        report.append("## 📋 Execution Plan Summary")
        report.append("")
        summary_text = plan.get("plan_summary", "No plan summary provided.")
        report.append(f"> {summary_text}")
        report.append("")
        
        report.append("### Ordered Worker Steps:")
        task_list = state.get("task_list") or []
        for idx, task in enumerate(task_list, 1):
            report.append(f"{idx}. **{task.replace('_', ' ').title()}**")
        report.append("")
        
    # Worker Results
    val_results = state.get("validation_results") or []
    if val_results:
        report.append("## ⚖️ Quality Gates & Workers Results")
        report.append("")
        report.append("| Agent | Task | Passed | Failed Rules / Notes | Timestamp |")
        report.append("| :--- | :--- | :---: | :--- | :--- |")
        
        for item in val_results:
            passed = "✅ YES" if item.get("passed") else "❌ NO"
            failed_rules = ", ".join(item.get("failed_rules") or [])
            if not failed_rules and item.get("passed"):
                failed_rules = "No policy violations"
            report.append(
                f"| {item.get('agent')} | {item.get('task_id')} | {passed} | {failed_rules} | {item.get('timestamp')} |"
            )
        report.append("")
        
    # Agent detailed logs
    report.append("## 📝 Chronological Execution Log")
    report.append("```")
    logs = get_terminal_logs(state)
    for log in logs:
        ts = log.get("timestamp") or 0.0
        time_str = time.strftime('%H:%M:%S', time.localtime(ts))
        agent = log.get("agent", "system")
        msg = log.get("message", "")
        level = log.get("level", "info")
        level_str = f" [{level.upper()}]" if level != "info" else ""
        report.append(f"[{time_str}] {agent}{level_str}: {msg}")
    report.append("```")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(report))


if __name__ == "__main__":
    run_test()
