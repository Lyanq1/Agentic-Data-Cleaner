"""_template — Copy this folder to create a new agent.

Step-by-step guide:
1. Copy this entire `_template/` folder to `app/agents/<your_agent_name>/`
2. Rename `TemplateAgent` → `YourAgent` in agent.py
3. Update `name` and `description` class attributes
4. Add your tools to `app/tools/registry.py` under `YOUR_AGENT_TOOLS`
5. Register your tools: the @AgentRegistry.auto_register decorator handles registration
6. Add your node in `app/graphs/nodes.py`
7. Add the node to `build_graph()` in `app/graphs/builder.py`
"""
