"""Planner Agent — copy and customize to create a new agent."""
import json
import logging
from typing import Any
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.planner.prompts import PLANNER_SYSTEM_PROMPT
from datetime import datetime
from app.graphs.states.global_state import ExecutionPlan, TaskDetail, TaskDetailWrapper, PlanMetadata, GlobalConstraints, GlobalState

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

        human_content = (
            f"## User Instruction\n{user_prompt}\n\n"
        )
        if validation_dict:
            human_content += f"## Input Validation Decision\n```json\n{json.dumps(validation_dict, indent=2, default=str)}\n```\n\n"
        if data_profile_dict:
            human_content += f"## Dataset Statistical Profile\n```json\n{json.dumps(data_profile_dict, indent=2, default=str)}\n```\n\n"
        if semantic_profile_dict:
            human_content += f"## Dataset Semantic Profile\n```json\n{json.dumps(semantic_profile_dict, indent=2, default=str)}\n```\n"

        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
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
                          task_id="null_handling",
                          agent="null_agent",
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
                  )
                ],
                plan_summary=f"Fallback execution plan created because LLM plan parsing failed: {e}."
            )

        logger.info("PlannerAgent successfully parsed execution plan.")

        # Map active tasks (skip == False) to the LangGraph router's task_list
        task_mapping = {
            "deduplication": "deduplication",
            "null_handling": "null_handling",
            "type_casting": "type_casting"
        }
        active_task_names = []
        for task in response.task_list:
            if not task.work_order.skip:
                mapped_name = task_mapping.get(task.work_order.task_id)
                if mapped_name:
                    active_task_names.append(mapped_name)

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
