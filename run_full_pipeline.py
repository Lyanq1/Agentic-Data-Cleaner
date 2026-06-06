import asyncio
import uuid
from pathlib import Path

from app.ingestion.normalizer import ingest_to_canonical
from app.graphs.checkpointer import get_checkpointer_manager
from app.graphs.graph import build_graph

async def main():
    original_csv = Path("tests/olist_products_dataset.csv")
    if not original_csv.exists():
        print("Error: tests/olist_products_dataset.csv not found.")
        return
        
    print(f"--- 1. Ingesting raw dataset: {original_csv} ---")
    canonical_path, input_format, _ = ingest_to_canonical(original_csv)
    
    run_id = f"test-full-{uuid.uuid4().hex[:8]}"
    initial_state = {
        "dataset_path": str(canonical_path),
        "user_prompt": "Please deduplicate and handle missing values",
        "project_id": run_id,
        "session_id": original_csv.stem,
    }
    
    config = {"configurable": {"thread_id": run_id}}
    
    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        
        print("\n--- 2. Starting Pipeline (Up to Planner) ---")
        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node, state_update in event.items():
                print(f"✅ Completed Node: {node}")
        
        # Check if paused
        state = await graph.aget_state(config)
        if state.next:
            print(f"\n--- 3. Graph paused at: {state.next}. Resuming to run Worker & Validator! ---")
            # Resume graph to force workers and validator to run
            async for event in graph.astream(None, config=config, stream_mode="updates"):
                for node, state_update in event.items():
                    print(f"✅ Completed Node: {node}")
                    if node == "validator":
                        val_result = state_update.get("validation_results")
                        if val_result:
                            print(f"\n   -> Validator Decision: Passed={val_result.passed}")
                            print(f"   -> Failed Rules: {val_result.failed_rules}")
                        print(f"   -> Dataset Version: {state_update.get('dataset_version')}")
                        print("\n===============================")
        
        print("\n--- 4. Final state reached ---")
        final_state = await graph.aget_state(config)
        print("Completed Steps:", final_state.values.get("completed_steps"))
        
if __name__ == "__main__":
    import sys
    import selectors
    if sys.platform == 'win32':
        loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    else:
        loop_factory = None
    asyncio.run(main(), loop_factory=loop_factory)
