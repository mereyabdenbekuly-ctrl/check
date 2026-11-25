"""OpenAI Chat Completions detector registry."""

from .base import ActiveDetector, BaseDetector, PassiveDetector
from .basic_request import BasicRequestDetector
from .dynamic_challenge import DynamicChallengeDetector
from .function_calling import FunctionCallingDetector
from .integrity import IntegrityDetector
from .long_context import LongContextDetector
from .model_consistency import ModelConsistencyDetector
from .pelican_svg import PelicanSVGDetector
from .prompt_cache import PromptCacheDetector
from .protocol import ProtocolDetector
from .structured_output import StructuredOutputDetector
from .system_injection import SystemInjectionDetector
from .token_billing import TokenBillingDetector
from .tokenizer_probe import TokenizerProbeDetector
from .vision_image import VisionImageDetector


def build_all() -> list[BaseDetector]:
    return [
        BasicRequestDetector(),
        ModelConsistencyDetector(),
        FunctionCallingDetector(),
        StructuredOutputDetector(),
        ProtocolDetector(),
        IntegrityDetector(),
        TokenBillingDetector(),
        TokenizerProbeDetector(),
        PromptCacheDetector(),
        SystemInjectionDetector(),
        VisionImageDetector(),
        DynamicChallengeDetector(),
        PelicanSVGDetector(),
        LongContextDetector(),
    ]


__all__ = [
    "BaseDetector",
    "ActiveDetector",
    "PassiveDetector",
    "BasicRequestDetector",
    "ModelConsistencyDetector",
    "FunctionCallingDetector",
    "StructuredOutputDetector",
    "ProtocolDetector",
    "IntegrityDetector",
    "TokenBillingDetector",
    "TokenizerProbeDetector",
    "PromptCacheDetector",
    "SystemInjectionDetector",
    "VisionImageDetector",
    "DynamicChallengeDetector",
    "PelicanSVGDetector",
    "LongContextDetector",
    "build_all",
]
