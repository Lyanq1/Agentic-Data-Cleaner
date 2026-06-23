"""Planner Agent — copy and customize to create a new agent."""
import json
import logging
from pathlib import Path
from typing import Any
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from datetime import datetime
from app.graphs.states.global_state import GlobalState

from app.graphs.states.planning import ExecutionPlan, TaskDetail, TaskDetailWrapper, PlanMetadata, GlobalConstraints

logger = logging.getLogger(__name__)


@AgentRegistry.auto_register
class PlannerAgent(BaseAgent):
    """Generates the data cleaning DAG and execution plan based on profiles and user inputs."""

    name = "planner"
    description = "Generates a structured execution plan for deduplication, null handling, and type casting."
    tools = []  # pure LLM reasoning

    async def run(self, state: GlobalState) -> dict[str, Any]:
        """Invoke the LLM to generate the ExecutionPlan.

        Args:
            state: Current GlobalState dict.

        Returns:
            State updates with the execution plan and task list.
            - execution_plan: ExecutionPlan Pydantic model.
            - task_list: List[str] containing mapped active task ids.
        """
        data_profile = state.get("statistical_profile")
        semantic_profile = state.get("semantic_profile")
        validation_result = state.get("input_validation_result")
        user_prompt = state.get("user_prompt", "")
        prior_messages = state.get("messages", [])

        # Output Validation Feedback for Replanning
        replan_reason = state.get("replan_reason")
        last_validation_error = state.get("last_validation_error")
        validation_results = state.get("validation_results", [])
        latest_replan_hints = {}
        if validation_results:
            latest_result = validation_results[-1]
            if hasattr(latest_result, "replan_hints"):
                latest_replan_hints = latest_result.replan_hints
            elif isinstance(latest_result, dict):
                latest_replan_hints = latest_result.get("replan_hints", {})

        # Format profiles safely (handling dict or Pydantic models)
        def to_dict(obj: Any) -> Any:
            if not obj:
                return None
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            elif hasattr(obj, "dict"):
                return obj.dict()
            return obj

        data_profile_dict = to_dict(data_profile)
        semantic_profile_dict = to_dict(semantic_profile)
        validation_dict = to_dict(validation_result)

        if semantic_profile_dict and "thinking" in semantic_profile_dict:
            # Remove thinking field to reduce token usage and avoid confusing the LLM parser
            del semantic_profile_dict["thinking"]

        pipeline_mode = state.get("pipeline_mode", "interactive")
        if pipeline_mode == "benchmark":
            user_instruction_block = "N/A — no user requirement; goal is the cleanest possible version of this dataset."
        else:
            user_instruction_block = user_prompt

        human_content = (
            f"## User Instruction\n{user_instruction_block}\n\n"
        )
        if validation_dict:
            human_content += f"## Input Validation Decision\n```json\n{json.dumps(validation_dict, indent=2, default=str)}\n```\n\n"
        if data_profile_dict:
            human_content += f"## Dataset Statistical Profile\n```json\n{json.dumps(data_profile_dict, indent=2, default=str)}\n```\n\n"
        if semantic_profile_dict:
            human_content += f"## Dataset Semantic Profile\n```json\n{json.dumps(semantic_profile_dict, indent=2, default=str)}\n```\n"

        if replan_reason or last_validation_error:
            human_content += f"## REPLAN REQUIRED\nThe previous plan failed validation. You must adjust your plan or strategy based on this feedback to avoid failing again.\n"
            if replan_reason:
                human_content += f"- **Replan Reason**: {replan_reason}\n"
            if last_validation_error:
                human_content += f"- **Validation Error**: {last_validation_error}\n"
            if latest_replan_hints:
                human_content += f"- **Hints**: {json.dumps(latest_replan_hints, indent=2, default=str)}\n"
            human_content += "\n"

        # Load the planner skill file dynamically
        skill_path = Path.cwd() / ".agents" / "skills" / "data-cleaning-planner" / "SKILL.md"
        if skill_path.exists():
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Strip YAML frontmatter if present
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        planner_system_prompt = parts[2].strip()
                    else:
                        planner_system_prompt = content
                else:
                    planner_system_prompt = content
        else:
            logger.warning(f"PlannerAgent: Skill file not found at {skill_path}. Falling back to default prompt.")
            from app.agents.planner.prompts import PLANNER_SYSTEM_PROMPT as planner_system_prompt

        messages = [
            SystemMessage(content=planner_system_prompt),
            HumanMessage(content=human_content),
        ]

        # Append any prior conversation history so the LLM remembers previous answers
        for msg in prior_messages:
            if isinstance(msg, (HumanMessage, AIMessage)):
                messages.append(msg)

        # Force JSON output mode
        messages.append(SystemMessage(content="CRITICAL: You must output ONLY a valid JSON object matching the requested schema. Do NOT wrap the response in markdown code blocks like ```json ... ```, and do NOT add any trailing characters or conversational text."))

        logger.info("PlannerAgent: invoking LLM for structured execution planning...")
        
        try:
            json_llm = self.llm.bind(response_format={"type": "json_object"})
            raw_response = await json_llm.ainvoke(messages)
            content = raw_response.content
            
            # Clean up the output string in case the model ignores the response_format and uses markdown
            content_clean = content.strip()
            if content_clean.startswith("```json"):
                content_clean = content_clean[7:]
            elif content_clean.startswith("```"):
                content_clean = content_clean[3:]
            if content_clean.endswith("```"):
                content_clean = content_clean[:-3]
            content_clean = content_clean.strip()
            
            # Extract only the JSON object boundaries
            start = content_clean.find("{")
            end = content_clean.rfind("}")
            if start != -1 and end != -1:
                content_clean = content_clean[start:end+1]
                
            response = ExecutionPlan.model_validate_json(content_clean)
        except Exception as e:
            logger.error(f"PlannerAgent failed to parse LLM JSON output: {e}")
            # Fallback to a safe execution plan where we skip all and log the error
            response = ExecutionPlan(
                metadata=PlanMetadata(
                    plan_id="fallback",
                    plan_version=1,
                    created_at=datetime.now().isoformat()
                ),
                global_constraints=GlobalConstraints(
                    max_retries_per_task=3,
                    preserve_columns=[]
                ),
                task_list=[
                  TaskDetailWrapper(
                      work_order=TaskDetail(
                          task_id="deduplication",
                          agent="dedup_agent",
                          skip=True,
                          skip_reason=f"Failed to generate plan due to error: {e}",
                          columns=[],
                          strategy={}
                      )
                  ),
                  TaskDetailWrapper(
                      work_order=TaskDetail(
                          task_id="type_casting",
                          agent="typecast_agent",
                          skip=True,
                          skip_reason=f"Failed to generate plan due to error: {e}",
                          columns=[],
                          strategy={}
                      )
                  ),
                  TaskDetailWrapper(
                      work_order=TaskDetail(
                          task_id="null_handling",
                          agent="null_agent",
                          skip=True,
                          skip_reason=f"Failed to generate plan due to error: {e}",
                          columns=[],
                          strategy={}
                      )
                  )
                ],
                plan_summary=f"Fallback execution plan created because LLM plan parsing failed: {e}."
            )

        logger.info("PlannerAgent successfully parsed execution plan.")

        # Enforce execution sequence: deduplication -> type_casting -> null_handling
        active_tasks_set = {
            task.work_order.task_id
            for task in response.task_list
            if not task.work_order.skip
        }
        active_task_names = []
        for task_id in ["deduplication", "type_casting", "null_handling"]:
            if task_id in active_tasks_set:
                active_task_names.append(task_id)

        logger.info(f"PlannerAgent active task list: {active_task_names}")

        json_data = response.model_dump()
        final_message = json.dumps(json_data, ensure_ascii=False, indent=2)

        # Update state with the plan and the mapped task_list
        updates: dict[str, Any] = {
            "messages": [AIMessage(content=final_message, name=self.name)],
            "execution_plan": response,
            "task_list": active_task_names,
            "current_task_idx": 0,
            "retry_count": 0
        }

        return updates
