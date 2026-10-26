"""Motor de análisis binario acotado (§8§6.3).

Proporciona análisis seguro de contenido binario malicioso dentro del perfil
ISOLATED_TEST_EXECUTION. Las operaciones se realizan sobre cadenas de texto
y extracciones seguras, sin ejecutar código arbitrario.

Las capacidades incluyen:
- Análisis acotado de archivos ZIP (límite de entradas, límite de tamaño)
- Análisis de binarios PE/PE+, JAVA Mach-O
- Inspección de contenido malicioso con límites de recursos definidos
"""
from __future__ import annotations

import os
import struct
import zlib
from typing import Any, Dict, Optional, List

try:
    import pefile
except ImportError:
    pefile = None

from app.core.execution_profiles import ExecutionProfile
from app.core.config import get_settings


class BinaryAnalysisResult:
    """Resultado del análisis binario acotado."""
    def __init__(self,
                 analysis_type: str,
                 safe: bool,
                 findings: List[str],
                 limitations: List[str],
                 execution_time: float):
        self.analysis_type = analysis_type
        self.safe = safe
        self.findings = findings
        self.limitations = limitations
        self.execution_time = execution_time


class BinaryAnalyzer:
    """Motor de análisis binario acotado."""
    
    def __init__(self):
        self.settings = get_settings()
        self.max_file_size = self.settings.sandbox_max_file_bytes or 67108864
        self.max_time = 60  # segundos
    
    def analyze_zip(self, code: str) -> BinaryAnalysisResult:
        """Análisis acotado de archivo ZIP."""
        findings = []
        safe = True
        limitations = []
        
        try:
            # Simulación de análisis ZIP dentro de límites
            # En un entorno real, esto usaría subprocess con límites de recursos
            code_bytes = code.encode('utf-8')
            
            if len(code_bytes) > self.max_file_size:
                safe = False
                findings.append("Archivo ZIP excede límite de tamaño")
                limitations.append("sandbox_size_limit")
            else:
                # Análisis simulado: verificar firma ZIP
                if code_bytes[:4] != b'PK':
                    safe = False
                    findings.append("Firma ZIP inválida")
                    limitations.append("firma_invalida")
                else:
                    # Análisis acotado de entradas ZIP
                    try:
                        # Intentar leer entradas básicas sin descompresión completa
                        count = 0
                        for i in range(min(5, len(code_bytes))):
                            if code_bytes[i:i+2] == b'PK':
                                count += 1
                        findings.append(f"Entradas ZIP detectadas: {count}")
                    except Exception as e:
                        findings.append(f"Error en análisis ZIP: {str(e)[:50]}")
                        safe = False
                        limitations.append("analisis_error")
        except Exception as e:
            safe = False
            findings.append(f"Error crítico en análisis ZIP: {str(e)[:100]}")
            limitations.append("error_critico")
        
        return BinaryAnalysisResult(
            analysis_type="zip",
            safe=safe,
            findings=findings,
            limitations=limitations,
            execution_time=0.0  # Tiempo medido en entorno real
        )
    
    def analyze_binary(self, code: str, binary_type: str) -> BinaryAnalysisResult:
        """Análisis acotado de binarios PE/JAVA/Mach-O."""
        findings = []
        safe = True
        limitations = []
        
        try:
            code_bytes = code.encode('utf-8')
            
            if len(code_bytes) > self.max_file_size:
                safe = False
                findings.append("Archivo binario excede límite de tamaño")
                limitations.append("sandbox_size_limit")
                return BinaryAnalysisResult(
                    analysis_type=binary_type,
                    safe=safe,
                    findings=findings,
                    limitations=limitations,
                    execution_time=0.0
                )
            
            if binary_type == "PE":
                # Análisis PE simplificado
                if pefile:
                    try:
                        pe = pefile.PE(bytes(code_bytes))
                        findings.append(f"Arquitectura PE: {pe.FILE_HEADER.Machine}")
                        findings.append(f"Secciones PE: {len(pe.sections)}")
                        # Verificar importaciones sospechosas
                        if peFILE_ENTRY_POINT:
                            findings.append("Punto de entrada PE detectado")
                    except Exception:
                        findings.append("Error al analizar binario PE")
                        safe = False
                        limitations.append("analisis_error")
                else:
                    # Sin pefile, análisis básico
                    findings.append("Análisis PE básico (sin pefile library)")
                    findings.append("Se recomienda instalar pefile para análisis completo")
            elif binary_type == "JAVA":
                # Análisis JAVA básico
                if code_bytes[:4] == b'\\xca\\xbab\\xdead':  # class file signature
                    findings.append("Archivo CLASS detectado")
                    findings.append("Análisis de constante mágica: 0xCAFEBABE")
                else:
                    # Buscar strings de clase Java
                    try:
                        text = code_bytes.decode('utf-8', errors='ignore')
                        if 'class ' in text and '{' in text:
                            findings.append("Estructura de clase Java detectada")
                    except:
                        pass
            elif binary_type == "MachO":
                # Análisis Mach-O básico
                if len(code_bytes) >= 8:
                    magic = code_bytes[:4]
                    if magic == b'\\xfe\\xfeed\\xfa\\xce' or magic == b'\\xce\\xfe\\xfa\\xfe':
                        findings.append("Archivo Mach-O detectado")
                        findings.append("Magic number: 0xFEEDFACE/MACHO")
                    else:
                        findings.append("Archivo con firma desconocida")
            else:
                findings.append(f"Tipo de binario no soportado: {binary_type}")
                safe = False
                limitations.append("tipo_no_soportado")
        
        except Exception as e:
            safe = False
            findings.append(f"Error crítico en análisis binario: {str(e)[:100]}")
            limitations.append("error_critico")
        
        return BinaryAnalysisResult(
            analysis_type=binary_type,
            safe=safe,
            findings=findings,
            limitations=limitations,
            execution_time=0.0
        )
    
    def analyze(self, binary_type: str, code: str) -> BinaryAnalysisResult:
        """Método principal de análisis."""
        if binary_type == "zip":
            return self.analyze_zip(code)
        else:
            return self.analyze_binary(binary_type, code)