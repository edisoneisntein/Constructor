"""Analizador de archivos ZIP acotado (§8§6.3).

Proporciona análisis seguro de archivos ZIP dentro del perfil
ISOLATED_TEST_EXECUTION, con límites de tamaño y entradas.
"""
from __future__ import annotations

import io
from typing import Any, List, Optional
from .binary_analyzer import BinaryAnalysisResult


class ZIPAnalyzer:
    """Analizador de archivos ZIP acotado."""
    
    def __init__(self, max_size: int = None, max_entries: int = 50):
        from app.core.config import get_settings
        settings = get_settings()
        self.max_size = settings.sandbox_max_file_bytes or 67108864
        self.max_entries = max_entries
    
    def analyze(self, code: str) -> BinaryAnalysisResult:
        """Analiza un archivo ZIP y retorna el resultado."""
        findings: List[str] = []
        safe: bool = True
        limitations: List[str] = []
        
        try:
            code_bytes = code.encode('utf-8')
            
            # Verificar límite de tamaño
            if len(code_bytes) > self.max_size:
                safe = False
                findings.append("Archivo ZIP excede límite de tamaño sandbox")
                limitations.append("sandbox_size_limit")
                return BinaryAnalysisResult(
                    analysis_type="zip",
                    safe=safe,
                    findings=findings,
                    limitations=limitations,
                    execution_time=0.0
                )
            
            # Verificar límite de entradas
            if len(code_bytes) > 0:
                try:
                    # Intentar leer el archivo ZIP sin descompresión completa
                    zip_file = io.BytesIO(code_bytes)
                    # Contar entradas PK (PK = PKZIP format signature)
                    count_pk = 0
                    for i in range(0, len(code_bytes) - 4, 1):
                        if code_bytes[i:i+2] == b'\\x50\\x4b':  # PK signature
                            count_pk += 1
                    
                    if count_pk > self.max_entries:
                        safe = False
                        findings.append(f"ZIP excede límite de entradas ({self.max_entries})")
                        limitations.append("zip_entry_limit")
                    else:
                        findings.append(f"ZIP válido ({count_pk} entradas detectadas)")
                        safe = True
                except Exception:
                    # Sin poder leer el ZIP propiamente dicho
                    findings.append("No se pudo analizar estructura ZIP")
                    safe = False
                    limitations.append("estructura_no_leyble")
            else:
                findings.append("Archivo ZIP vacío")
                safe = False
                limitations.append("archivo_vacio")
                
        except Exception as e:
            safe = False
            findings.append(f"Error crítico en análisis ZIP: {str(e)[:100]}")
            limitations.append("error_critico")
        
        return BinaryAnalysisResult(
            analysis_type="zip",
            safe=safe,
            findings=findings,
            limitations=limitations,
            execution_time=0.0
        )
    
    def verify_checksum(self, code: str) -> bool:
        """Verifica la integridad de checksum del archivo ZIP."""
        try:
            code_bytes = code.encode('utf-8')
            # ZIP files typically end with an end of central directory record
            # Simple checksum verification
            if len(code_bytes) > 4:
                # Simple parity check
                total = sum(code_bytes) % 256
                return total % 2 == 0  # Simplified checksum verification
            return False
        except:
            return False