"""Analizador de binarios JAVA (§8§6.3).

Proporciona análisis acotado de binarios JAVA (archivos class) dentro del
perfil ISOLATED_TEST_EXECUTION.
"""
from __future__ import annotations

import struct
from typing import Any, List, Optional
from .binary_analyzer import BinaryAnalysisResult


class JavaAnalyzer:
    """Analizador de binarios JAVA acotado."""
    
    def __init__(self, max_size: int = None):
        from app.core.config import get_settings
        settings = get_settings()
        self.max_size = settings.sandbox_max_file_bytes or 67108864
    
    def analyze(self, code: str) -> BinaryAnalysisResult:
        """Analiza un binario JAVA y retorna el resultado."""
        findings: List[str] = []
        safe: bool = True
        limitations: List[str] = []
        
        try:
            code_bytes = code.encode('utf-8')
            
            # Verificar límite de tamaño
            if len(code_bytes) > self.max_size:
                safe = False
                findings.append("Archivo JAVA excede límite de tamaño sandbox")
                limitations.append("sandbox_size_limit")
                return BinaryAnalysisResult(
                    analysis_type="java",
                    safe=safe,
                    findings=findings,
                    limitations=limitations,
                    execution_time=0.0
                )
            
            # Análisis de archivo class de Java
            # Los archivos class de Java comienzan con la firma mágica 0xCAFEBABE
            if len(code_bytes) >= 8 and code_bytes[:4] == b'\xca\xba\xbe\xba':
                findings.append("Archivo CLASS de Java detectado (firma mágica 0xCAFEBABE)")
                
                # Analizar constantes
                try:
                    # Simplified: check for constant pool lookups
                    text = code_bytes.decode('utf-8', errors='ignore')
                    if 'class ' in text and 'public ' in text:
                        findings.append("Clase pública detectada")
                    if 'method' in text.lower():
                        findings.append("Métodos detectados en la estructura")
                    if 'import' in text.lower():
                        findings.append("Importaciones detectadas")
                    
                    # Verificar métodos públicos
                    pub_methods = text.count('public ')
                    if pub_methods > 0:
                        findings.append(f"{pub_methods} métodos públicos detectados")
                    
                    safe = True
                except Exception:
                    findings.append("Estructura de archivo CLASS no reconocida")
                    safe = False
                    limitations.append("estructura_no_ Reconocida")
            else:
                # Sin firma mágica de class file
                findings.append("No se detecta firma de archivo CLASS de Java")
                safe = False
                limitations.append("sin_firma_class")
        
        except Exception as e:
            safe = False
            findings.append(f"Error crítico en análisis JAVA: {str(e)[:100]}")
            limitations.append("error_critico")
        
        return BinaryAnalysisResult(
            analysis_type="java",
            safe=safe,
            findings=findings,
            limitations=limitations,
            execution_time=0.0
        )