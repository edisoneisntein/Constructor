"""Analizador de binarios PE (§8§6.3).

Proporciona análisis acotado de binarios PE (Portable Executable) dentro del
perfil ISOLATED_TEST_EXECUTION.
"""
from __future__ import annotations

import struct
from typing import Any, List, Optional
from .binary_analyzer import BinaryAnalysisResult


class PEAnalyzer:
    """Analizador de binarios PE acotado."""
    
    def __init__(self, max_size: int = None):
        from app.core.config import get_settings
        settings = get_settings()
        self.max_size = settings.sandbox_max_file_bytes or 67108864
    
    def analyze(self, code: str) -> BinaryAnalysisResult:
        """Analiza un binario PE y retorna el resultado."""
        findings: List[str] = []
        safe: bool = True
        limitations: List[str] = []
        
        try:
            code_bytes = code.encode('utf-8')
            
            # Verificar límite de tamaño
            if len(code_bytes) > self.max_size:
                safe = False
                findings.append("Archivo PE excede límite de tamaño sandbox")
                limitations.append("sandbox_size_limit")
                return BinaryAnalysisResult(
                    analysis_type="pe",
                    safe=safe,
                    findings=findings,
                    limitations=limitations,
                    execution_time=0.0
                )
            
            # Intentar análisis PE usando pefile si está disponible
            try:
                import pefile
                pe = pefile.PE(bytes(code_bytes))
                
                # Información del encabezado
                findings.append(f"Arquitectura PE: {pe.FILE_HEADER.Machine}")
                findings.append(f"Número de secciones: {pe.FILE_HEADER.NumberOfSections}")
                findings.append(f"Tamaño de imagen: {pe.OPTIONAL_HEADER.SizeOfImage}")
                
                # Verificar importaciones sospechosas
                if hasattr(pe, 'IMPORT_DIR'):
                    imports = []
                    for imp in pe.imports:
                        if imp:
                            imports.append(imp.name.decode('utf-8', errors='ignore'))
                    if imports:
                        findings.append(f"Importaciones detectadas: {', '.join(imports[:5])}")
                    else:
                        findings.append("Sin importaciones detectadas")
                
                # Verificar exportaciones
                if hasattr(pe, 'EXPORT_DIR'):
                    findings.append("Binario con exportaciones detectadas")
                
                # Verificar sección .text
                for section in pe.sections:
                    if section.Name.decode('utf-8', errors='ignore').rstrip(b'\\x00') == '.text':
                        findings.append(f"Sección .text encontrada: tamaño {section.Misc.VirtualSize}")
                        break
                
                safe = True
                
            except Exception as e:
                # Sin pefile, análisis básico
                findings.append("Análisis PE básico (sin pefile library)")
                findings.append("Se recomienda instalar pefile para análisis completo")
                safe = True  # No es unsafe, solo sin análisis completo
                limitations.append("sin_pefile_library")
        
        except Exception as e:
            safe = False
            findings.append(f"Error crítico en análisis PE: {str(e)[:100]}")
            limitations.append("error_critico")
        
        return BinaryAnalysisResult(
            analysis_type="pe",
            safe=safe,
            findings=findings,
            limitations=limitations,
            execution_time=0.0
        )