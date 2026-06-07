import logging
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from app.core.llm_factory import create_llm

from app.agents.base import BaseAgent
from app.graphs.states.global_state import GlobalState
from app.agents.result_validators.models import ValidatorOutput
from app.tools.data.quality_control.tool import perform_data_quality_check
from app.graphs.utils import _resolve_active_task
from app.agents.result_validators.prompts import SYSTEM_PROMPT
from app.tools.data.quality_control.validator import run_pandas_validation

logger = logging.getLogger(__name__)

class ValidatorAgent(BaseAgent):
    """Output Validator Agent that evaluates data quality using ReAct LLM loop."""

    name = "output_validator_agent"
    description = "Evaluates data quality using ReAct and assigns a score."
    
    tools = [perform_data_quality_check]

    def __init__(self) -> None:
        super().__init__()
        self.structured_llm = create_llm().with_structured_output(ValidatorOutput)

    async def run(self, state: GlobalState) -> Dict[str, Any]:
        logger.info("ValidatorAgent: Starting output validation...")
        
        user_prompt = state.get("user_prompt", "")
        raw_req = state.get("raw_requirement_input", "")
        active_task = _resolve_active_task(state)
        task_plan_str = active_task.model_dump_json() if active_task else "No specific task plan."
        
        # The worker saved the output to path_file_to_validate or physical_dataframe_path
        file_path = state.get("path_file_to_validate") or state.get("physical_dataframe_path")
        if not file_path:
            logger.error("ValidatorAgent: No path_file_to_validate found to validate.")
            return {
                "validator_agent_result": None,
                "error": "No path_file_to_validate found.",
                "success": False
            }
            
        # Resolve agent name
        agent_name = getattr(active_task.agent, "value", str(active_task.agent)) if active_task else "Unknown Agent"
        
        # Run deterministic pandas validation
        validation_result_str = run_pandas_validation(
            file_path=file_path,
            task=active_task,
            semantic_profile=state.get("semantic_profile")
        )
            
        human_content = (
            f"--- USER PROMPT ---\n{user_prompt}\n\n"
            f"--- CLARIFICATIONS ---\n{raw_req}\n\n"
            f"--- TASK PLAN ---\n{task_plan_str}\n\n"
            f"--- AGENT NAME ---\n{agent_name}\n\n"
            f"--- DETERMINISTIC VALIDATION RESULT ---\n{validation_result_str}\n\n"
            f"The dataset is located at: {file_path}\n"
            "You may call `perform_data_quality_check` on this file_path if you need to observe the full profiling state, then provide your structured output. "
            "Remember to ONLY penalize the data for issues that were within the scope of the Agent Name listed above."
        )
        
        messages: list[Any] = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_content)
        ]
        
        try:
            # 1. First LLM call: expects a tool call
            ai_msg = await self.llm.ainvoke(messages)
            messages.append(ai_msg)
            
            # 2. Check if tool was called
            if ai_msg.tool_calls:
                for tool_call in ai_msg.tool_calls:
                    if tool_call["name"] == "perform_data_quality_check":
                        logger.info(f"ValidatorAgent: LLM called tool: {tool_call['name']}")
                        # Execute the tool
                        tool_result = perform_data_quality_check.invoke(tool_call["args"])
                        messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"]))
            else:
                logger.warning("ValidatorAgent: LLM did not call the QC tool! Proceeding anyway...")

            # 3. Second LLM call: generate structured output based on observation
            output: ValidatorOutput = await self.structured_llm.ainvoke(messages)
            
            return {
                "validator_agent_result": output,
                "df_validated_path": file_path,
                "success": True
            }
        except Exception as exc:
            logger.error(f"ValidatorAgent: ReAct LLM error: {exc}")
            return {
                "validator_agent_result": None,
                "error": str(exc),
                "success": False
            }
