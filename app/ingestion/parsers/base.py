"""Abstract base class for all format parsers."""
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class BaseParser(ABC):
    """Parse a file into a raw pandas DataFrame.

    Subclasses must not apply any cleaning — that is the responsibility
    of the agent pipeline. The parser only handles format decoding.
    """

    @abstractmethod
    def parse(self, file_path: Path) -> pd.DataFrame:
        """Read the file and return a raw DataFrame preserving original dtypes."""
        ...

    @abstractmethod
    def supports(self, file_path: Path) -> bool:
        """Return True if this parser can handle the given file."""
        ...

    @abstractmethod
    def get_schema(self, file_path: Path) -> dict:
        """Return a dict mapping column names to their expected data types."""
        ...