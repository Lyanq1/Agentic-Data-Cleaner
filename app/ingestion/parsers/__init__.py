"""Ingestion parsers — format-specific file readers."""
from app.ingestion.parsers.csv_parser import CSVParser
from app.ingestion.parsers.excel_parser import ExcelParser
from app.ingestion.parsers.json_parser import JSONParser

__all__ = ["CSVParser", "ExcelParser", "JSONParser"]
