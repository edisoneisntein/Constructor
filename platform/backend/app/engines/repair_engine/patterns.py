"""Patrones comunes de Python que el RepairEngine puede reconocer y reparar.

Este módulo define secuencias de caracteres y expresiones regulares que
identifican errores frecuentes en código Python. Cada patrón tiene asociado
una reparación segura que aplica el motor cuando el patrón es detectado y
fuerza la flag ``apply`` correspondiente.

Los patrones están diseñados para detectarse en código fuente estático
(sin necesidad de ejecución en tiempo real).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RepairPattern:
    """Un patrón detectable y reparable."""

    name: str
    pattern: str  # expresión regular sobre el código fuente
    description: str
    repair: str  # código Python que devuelve el código reparado
    aply: bool = True  # whether to apply by default


# Patrones de Python comunes y detectables estáticamente

# 1. Uso inseguro de eval/exec
EVAL_EXEC_PATTERN = RepairPattern(
    name="EvalExec",
    pattern=r"\beval\(|\\bexec\(",
    description="Uso de eval o exec - riesgo de inyección de código",
    repair='''# Reemplo: evaluar expresión de forma segura sandboxed
import ast
import builtins

def safe_eval(expr, allowed_names=None):
    if allowed_names is None:
        allowed_names = {"True": True, "False": False, "None": None}
    return expr  # Placeholder: usar ast.literal_eval en producción'''
)

# 2. Variables potencialmente no definidas (asignación a nombre sospechoso)
SUSPICIOUS_ASSIGN_PATTERN = RepairPattern(
    name="SuspiciousAssign",
    pattern=r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*__[a-zA-Z_]+__",  # asignación a dunder
    description="Asignación a atributo dunder - puede indicar confusión",
    repair='''# Reparo: usar nombre de variable explícito en lugar de dunder
nombre_explicito = valor  # type: ignore
''',
)

# 3. Excepciones sin captura (bare except)
BARE_EXCEPT_PATTERN = RepairPattern(
    name="BareExcept",
    pattern=r"\bexcept\s*:",
    description="Bloque excepto sin tipo de excepción - captura todo",
    repair='''# Reparo: capturar excepción específica
except Exception as e:
    # Manejo de error con información
    pass
''',
)

# 4. Open file sin contexto (missing with statement)
OPEN_WITHOUT_CONTEXT_PATTERN = RepairPattern(
    name="OpenWithoutContext",
    pattern=r"\bopen\([^)]+\)",
    description="Archivo abierto sin contexto - riesgo de fuga de descriptores",
    repair='''# Reparo: usar "with" para cierre automático
with open(ruta, "modo") as f:
    contenido = f.read()
''',
)

# 5. Cadena de formato insegura
UNSAFE_FORMAT_PATTERN = RepairPattern(
    name="UnsafeFormat",
    pattern=r"format\([^)]+%s[^)]*\)",
    description="Formato de cadena con %s sin validación",
    repair='''# Reparo: usar formato .format() o f-strings seguros
cadena.format(argumento) if argumento else "valor por defecto"
''',
)

COMMON_PYTHON_PATTERNS = [
    EVAL_EXEC_PATTERN,
    SUSPICIOUS_ASSIGN_PATTERN,
    BARE_EXCEPT_PATTERN,
    OPEN_WITHOUT_CONTEXT_PATTERN,
    UNSAFE_FORMAT_PATTERN,
]