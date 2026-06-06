import logging
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from app.core.llm_factory import create_llm

from app.agents.base import BaseAgent
from app.graphs.states.global_state import GlobalState
from app.agents.result_validators.models import ValidatorOutput
from app.tools.data.quality_control.tool import perform_data_quality_check
from app.agents.result_validators.runner import _resolve_active_task

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Output Validator Agent in a data cleaning pipeline.
Your job is to evaluate the quality of the dataset after a worker agent has processed it.

You MUST use the `perform_data_quality_check` tool on the provided `file_path` to get the Data Quality Control (QC) Report.

Your workflow (ReAct & Scoring):
1. THINK: Analyze the context and call the `perform_data_quality_check` tool to observe the dataset.
2. OBSERVE: Read the QC report returned by the tool. Check for nulls, duplicates, disguised nulls, etc.
3. SCORE & REFINE: Calculate a `quality_score` from 0 to 100.
    - Start at 100.
    - Deduct points for issues (e.g. -20 for high nulls, -30 for duplicates, -10 for disguised nulls).
    - If score >= 80, it is PASS. If < 80, it is FAIL.
4. OUTPUT: Provide the structured ValidatorOutput.

Be strict but fair.
"""

class ValidatorAgent(BaseAgent):
    """Output Validator Agent that evaluates data quality using ReAct LLM loop."""

    name = "output_validator_agent"
    description = "Evaluates data quality using ReAct and assigns a score."
    
    tools = [perform_data_quality_check]

    def __init__(self) -> None:
        super().__init__()
        self.structured_llm = create_llm().with_structured_output(ValidatorOutput)

    async def run(self, state: GlobalState) -> Dict[str, Any]:
        logger.info("ValidatorAgent: Starting output validation via ReAct...")
        
        user_prompt = state.get("user_prompt", "")
        raw_req = state.get("raw_requirement_input", "")
        active_task = _resolve_active_task(state)
        task_plan_str = active_task.model_dump_json() if active_task else "No specific task plan."
        
        # The worker saved the output to physical_dataframe_path
        file_path = state.get("physical_dataframe_path")
        if not file_path:
            logger.error("ValidatorAgent: No physical_dataframe_path found to validate.")
            return {
                "validator_agent_result": None,
                "error": "No physical_dataframe_path found.",
                "success": False
            }
            
        human_content = (
            f"--- USER PROMPT ---\n{user_prompt}\n\n"
            f"--- CLARIFICATIONS ---\n{raw_req}\n\n"
            f"--- TASK PLAN ---\n{task_plan_str}\n\n"
            f"The dataset is located at: {file_path}\n"
            "Please call `perform_data_quality_check` on this file_path, then provide your structured output."
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
            
            # Note: We don't have df loaded in memory here, so we leave df_validated as None or load it if needed.
            # But the validator_node in app/graphs/nodes.py expects df_validated to push to LineageService.
            # So we load it here.
            import pandas as pd
            df_validated = pd.read_parquet(file_path) if str(file_path).endswith('.parquet') else pd.read_csv(file_path)

            return {
                "validator_agent_result": output,
                "df_validated": df_validated,
                "success": True
            }
        except Exception as exc:
            logger.error(f"ValidatorAgent: ReAct LLM error: {exc}")
            return {
                "validator_agent_result": None,
                "error": str(exc),
                "success": False
            }
