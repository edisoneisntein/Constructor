"""Analizador de binarios Mach-O (§8§6.3).

Proporciona análisis acotado de binarios Mach-O dentro del perfil
ISOLATED_TEST_EXECUTION.
"""
from __future__ import annotations

import struct
from typing import Any, List, Optional
from .binary_analyzer import BinaryAnalysisResult


class MachOAnalyzer:
    """Analizador de binarios Mach-O acotado."""
    
    def __init__(self, max_size: int = None):
        from app.core.config import get_settings
        settings = get_settings()
        self.max_size = settings.sandbox_max_file_bytes or 67108864
    
    def analyze(self, code: str) -> BinaryAnalysisResult:
        """Analiza un binario Mach-O y retorna el resultado."""
        findings: List[str] = []
        safe: bool = True
        limitations: List[str] = []
        
        try:
            code_bytes = code.encode('utf-8')
            
            # Verificar límite de tamaño
            if len(code_bytes) > self.max_size:
                safe = False
                findings.append("Archivo Mach-O excede límite de tamaño sandbox")
                limitations.append("sandbox_size_limit")
                return BinaryAnalysisResult(
                    analysis_type="mach_o",
                    safe=safe,
                    findings=findings,
                    limitations=limitations,
                    execution_time=0.0
                )
            
            # Análisis de encabezado Mach-O
            # Mach-O magic numbers
            # 0xFEEDFACE (32-bit, big-endian)
            # 0xFEEDFACF (64-bit, big-endian)
            # 0xCEFAE7 (32-bit, little-endian)
            # 0xCFFAE7 (64-bit, little-endian)
            
            if len(code_bytes) >= 8:
                magic_32_be = code_bytes[:4] == b'\\xfe\\xed\\xfa\\xce'
                magic_32_le = code_bytes[:4] == b'\\xce\\xf\\xe7\\xfa'
                magic_64_be = code_bytes[:4] == b'\\xce\\xfa\\xfe\\xed'
                magic_64_le = code_bytes[:4] == b'\\xed\\xfa\\xfe\\xce'
                
                if magic_32_be:
                    findings.append("Mach-O 32-bit, big-endian detectado (magic: 0xFEEDFACE)")
                    findings.append("Tipo de archivo: 32-bit (MH_MAGIC)")
                    safe = True
                elif magic_32_le:
                    findings.append("Mach-O 32-bit, little-endian detectado (magic: 0xCEFAE7)")
                    findings.append("Tipo de archivo: 32-bit (MH_MAGIC)")
                    safe = True
                elif magic_64_be:
                    findings.append("Mach-O 64-bit, big-endian detectado (magic: 0xFEEDFACF)")
                    findings.append("Tipo de archivo: 64-bit (MH_MAGIC_64)")
                    safe = True
                elif magic_64_le:
                    findings.append("Mach-O 64-bit, little-endian detectado (magic: 0xCFFAE7)")
                    findings.append("Tipo de archivo: 64-bit (MH_MAGIC_64)")
                    safe = True
                else:
                    findings.append("No se detecta firma Mach-O válida")
                    safe = False
                    limitations.append("sin_firma_mach_o")
            else:
                findings.append("Archivo demasiado corto para análisis Mach-O")
                safe = False
                limitations.append("archivo_corto")
        
        except Exception as e:
            safe = False
            findings.append(f"Error crítico en análisis Mach-O: {str(e)[:100]}")
            limitations.append("error_critico")
        
        return BinaryAnalysisResult(
            analysis_type="mach_o",
            safe=safe,
            findings=findings,
            limitations=limitations,
            execution_time=0.0
        )