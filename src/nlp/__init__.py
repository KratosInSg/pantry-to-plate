"""Natural-language understanding of the user's pantry description.

Pipeline: ``segmenter`` -> ``urgency`` -> ``quantities`` -> ``resolver`` -> ``pantry_parser`` (orchestrates).
Public entry point: :class:`nlp.pantry_parser.PantryParser`. See ``md docs/modules/nlp/README.md``.
"""
from nlp.pantry_parser import PantryParser
from nlp.schemas import GramsSource, MatchStatus, ParsedItem, ParseResult, Urgency

__all__ = ["PantryParser", "ParseResult", "ParsedItem", "Urgency", "MatchStatus", "GramsSource"]
