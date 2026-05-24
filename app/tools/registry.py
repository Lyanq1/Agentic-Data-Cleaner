"""Tool registry — maps tools to agent roles.

Add new tools here after creating them in the appropriate subpackage.
Agents import their tool list from this registry.
"""
from app.tools.data.read_file import read_file
from app.tools.data.profile_dataframe import profile_dataframe
from app.tools.data.clean_nulls import clean_nulls
from app.tools.data.remove_duplicates import remove_duplicates
from app.tools.data.normalize_columns import normalize_columns
from app.tools.storage.save_to_postgres import save_to_postgres
from app.tools.storage.save_to_file import save_to_file
from app.tools.external.http_client import call_external_api
from app.tools.data.eda import perform_eda

# ── Per-agent tool sets ──
PROFILER_TOOLS = [read_file, profile_dataframe, perform_eda]
CLEANER_TOOLS = [read_file, clean_nulls, remove_duplicates, normalize_columns]
VALIDATOR_TOOLS = [read_file]
TRANSFORMER_TOOLS = [read_file, normalize_columns, call_external_api]
REPORTER_TOOLS = [save_to_file, save_to_postgres]

# ── Master list (for documentation/inspection) ──
ALL_TOOLS = list({t.name: t for t in PROFILER_TOOLS + CLEANER_TOOLS + VALIDATOR_TOOLS + TRANSFORMER_TOOLS + REPORTER_TOOLS}.values())
