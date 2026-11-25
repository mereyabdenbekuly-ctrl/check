"""Gemini detector registry."""

from .base import ActiveDetector, BaseDetector, PassiveDetector
from .basic_request import BasicRequestDetector
from .dynamic_challenge import DynamicChallengeDetector
from .function_calling import FunctionCallingDetector
from .integrity import IntegrityDetector
from .model_info import ModelInfoDetector
from .pelican_svg import PelicanSVGDetector
from .protocol import ProtocolDetector
from .structured_output import StructuredOutputDetector
from .system_injection import SystemInjectionDetector
from .token_usage import TokenUsageDetector
from .tokenizer_probe import TokenizerProbeDetector
from .vision_image import VisionImageDetector


def build_all() -> list[BaseDetector]:
    return [
        BasicRequestDetector(),
        ModelInfoDetector(),
        FunctionCallingDetector(),
        StructuredOutputDetector(),
        ProtocolDetector(),
        IntegrityDetector(),
        TokenUsageDetector(),
        TokenizerProbeDetector(),
        SystemInjectionDetector(),
        VisionImageDetector(),
        DynamicChallengeDetector(),
        PelicanSVGDetector(),
    ]


__all__ = [
    "BaseDetector",
    "ActiveDetector",
    "PassiveDetector",
    "BasicRequestDetector",
    "ModelInfoDetector",
    "FunctionCallingDetector",
    "StructuredOutputDetector",
    "ProtocolDetector",
    "IntegrityDetector",
    "TokenUsageDetector",
    "TokenizerProbeDetector",
    "SystemInjectionDetector",
    "VisionImageDetector",
    "DynamicChallengeDetector",
    "PelicanSVGDetector",
    "build_all",
]
