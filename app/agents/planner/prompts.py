"""Prompts for the Template agent — replace with your own."""

TEMPLATE_SYSTEM_PROMPT = """\
You are a [DESCRIBE YOUR AGENT] agent.
Your job is to [DESCRIBE THE TASK].

You have access to the following tools:
{tools}

Current context:
- File path: {file_path}
- Rules: {rules}
"""
