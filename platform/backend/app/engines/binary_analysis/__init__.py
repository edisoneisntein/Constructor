"""Binary Analysis Engine (§8§6.3).

Motor de análisis binario acotado para la Fase 8§6.3.
Proporciona análisis seguro de contenido malicioso dentro del perfil
ISOLATED_TEST_EXECUTION, con límites de CPU, memoria y tiempo.

No ejecuta código arbitrario: solo realiza análisis estático y extracción
segura de contenido de archivos binarios (ZIP, PE, JAVA, Mach-O).
"""
from __future__ import annotations

from app.engines.binary_analysis.analyzer import BinaryLimits, analyze_binary, compare_binaries
from app.engines.binary_analysis.binary_analyzer import BinaryAnalyzer
from app.engines.binary_analysis.formats import detect_format
from app.engines.binary_analysis.zip_analyzer import ZIPAnalyzer
from app.engines.binary_analysis.pe_analyzer import PEAnalyzer
from app.engines.binary_analysis.java_analyzer import JavaAnalyzer
from app.engines.binary_analysis.mach_o_analyzer import MachOAnalyzer

__all__ = [
    "BinaryAnalyzer",
    "BinaryLimits",
    "ZIPAnalyzer",
    "PEAnalyzer",
    "JavaAnalyzer",
    "MachOAnalyzer",
    "analyze_binary",
    "compare_binaries",
    "detect_format",
]