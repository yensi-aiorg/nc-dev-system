"""NC Dev System requirements parser.

Parses markdown requirement documents and extracts structured features,
architecture definitions, and test plans for autonomous code generation.

Usage::

    from src.parser import parse_requirements, Feature, Architecture, TestPlan

    result = await parse_requirements("path/to/requirements.md")
    print(result.features)
    print(result.architecture)
    print(result.test_plan)
    print(result.ambiguities)
"""

from src.parser.models import (
    Architecture,
    Feature,
    ParseResult,
    TestPlan,
)
from src.parser.extractor import parse_requirements

__all__ = [
    "parse_requirements",
    "Feature",
    "Architecture",
    "TestPlan",
    "ParseResult",
]
