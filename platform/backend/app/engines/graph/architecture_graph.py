"""Construcción del grafo de arquitectura G=(V,E) (§7).

Cada nodo y arista llevan tipo, procedencia, método de detección y nivel de
evidencia. Se distinguen relaciones confirmadas (DIRECT_EVIDENCE) de inferidas
(STATIC_INFERENCE).

Tipos de nodo: file, manifest, symbol, dependency, env_var, integration,
api_route, entrypoint, test.
Tipos de arista: imports, imports_external, depends_on, declares_dependency,
defines, reads_env, uses, exposes, is_entrypoint, is_test, configures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.ids import new_id


@dataclass
class GraphNode:
    node_id: str
    node_type: str
    label: str
    path: str | None
    language: str | None
    evidence_level: str
    detection_method: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str | None
    target_ref: str | None
    edge_type: str
    evidence_level: str
    detection_method: str
    metadata: dict[str, Any] = field(default_factory=dict)


class GraphBuilder:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._edge_keys: set[tuple[str, str, str | None, str | None, str]] = set()

    # -- identificadores de nodo ------------------------------------------
    @staticmethod
    def file_node_id(path: str) -> str:
        return f"file::{path}"

    @staticmethod
    def manifest_node_id(path: str) -> str:
        return f"manifest::{path}"

    @staticmethod
    def dependency_node_id(ecosystem: str, name: str) -> str:
        return f"dep::{ecosystem}::{name}"

    @staticmethod
    def symbol_node_id(path: str, name: str) -> str:
        return f"sym::{path}::{name}"

    @staticmethod
    def env_node_id(name: str) -> str:
        return f"env::{name}"

    @staticmethod
    def integration_node_id(provider: str) -> str:
        return f"integ::{provider}"

    @staticmethod
    def route_node_id(method: str, path: str) -> str:
        return f"route::{method}::{path}"

    @staticmethod
    def entrypoint_node_id(path: str) -> str:
        return f"entry::{path}"

    def _ensure_node(
        self,
        node_id: str,
        *,
        node_type: str,
        label: str,
        path: str | None,
        language: str | None,
        evidence_level: str,
        detection_method: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if node_id not in self._nodes:
            self._nodes[node_id] = GraphNode(
                node_id=node_id,
                node_type=node_type,
                label=label,
                path=path,
                language=language,
                evidence_level=evidence_level,
                detection_method=detection_method,
                metadata=metadata or {},
            )
        return node_id

    # -- nodos -------------------------------------------------------------
    def add_file_node(
        self,
        path: str,
        *,
        language: str,
        evidence_level: str,
        detection_method: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self._ensure_node(
            self.file_node_id(path),
            node_type="file",
            label=path,
            path=path,
            language=language,
            evidence_level=evidence_level,
            detection_method=detection_method,
            metadata=metadata,
        )

    def add_manifest_node(
        self,
        path: str,
        *,
        filename: str,
        evidence_level: str = "DIRECT_EVIDENCE",
        detection_method: str = "manifest_present",
    ) -> str:
        return self._ensure_node(
            self.manifest_node_id(path),
            node_type="manifest",
            label=path,
            path=path,
            language="manifest",
            evidence_level=evidence_level,
            detection_method=detection_method,
            metadata={"filename": filename},
        )

    def add_dependency_node(
        self,
        ecosystem: str,
        name: str,
        *,
        version: str | None,
        evidence_level: str,
        detection_method: str,
    ) -> str:
        return self._ensure_node(
            self.dependency_node_id(ecosystem, name),
            node_type="dependency",
            label=f"{name}@{version}" if version else name,
            path=None,
            language=None,
            evidence_level=evidence_level,
            detection_method=detection_method,
            metadata={"ecosystem": ecosystem, "name": name, "version": version},
        )

    def add_symbol_node(
        self,
        path: str,
        name: str,
        *,
        kind: str,
        line: int,
        language: str,
        evidence_level: str = "DIRECT_EVIDENCE",
        detection_method: str = "ast_symbol",
    ) -> str:
        return self._ensure_node(
            self.symbol_node_id(path, name),
            node_type="symbol",
            label=name,
            path=path,
            language=language,
            evidence_level=evidence_level,
            detection_method=detection_method,
            metadata={"kind": kind, "line": line},
        )

    def add_env_node(
        self,
        name: str,
        *,
        line: int,
        language: str,
        evidence_level: str = "DIRECT_EVIDENCE",
        detection_method: str = "environment_access_detection",
    ) -> str:
        return self._ensure_node(
            self.env_node_id(name),
            node_type="env_var",
            label=name,
            path=None,
            language=language,
            evidence_level=evidence_level,
            detection_method=detection_method,
            metadata={"line": line},
        )

    def add_integration_node(
        self,
        provider: str,
        *,
        package_hint: str,
        evidence_level: str = "DIRECT_EVIDENCE",
        detection_method: str = "import_specifier_exact_match",
    ) -> str:
        return self._ensure_node(
            self.integration_node_id(provider),
            node_type="integration",
            label=provider,
            path=None,
            language=None,
            evidence_level=evidence_level,
            detection_method=detection_method,
            metadata={"provider": provider, "package_hint": package_hint},
        )

    def add_route_node(
        self,
        method: str,
        path: str,
        *,
        framework: str,
        language: str,
        evidence_level: str = "DIRECT_EVIDENCE",
        detection_method: str = "decorator_route_detection",
    ) -> str:
        return self._ensure_node(
            self.route_node_id(method, path),
            node_type="api_route",
            label=f"{method} {path}",
            path=None,
            language=language,
            evidence_level=evidence_level,
            detection_method=detection_method,
            metadata={"framework": framework, "method": method, "route": path},
        )

    def add_entrypoint_node(
        self,
        path: str,
        *,
        language: str,
        evidence_level: str = "DIRECT_EVIDENCE",
        detection_method: str = "entry_point_detection",
    ) -> str:
        return self._ensure_node(
            self.entrypoint_node_id(path),
            node_type="entrypoint",
            label=f"entrypoint: {path}",
            path=path,
            language=language,
            evidence_level=evidence_level,
            detection_method=detection_method,
        )

    def add_test_node(
        self,
        path: str,
        *,
        language: str,
        evidence_level: str = "DIRECT_EVIDENCE",
        detection_method: str = "test_file_detection",
    ) -> str:
        return self._ensure_node(
            f"test::{path}",
            node_type="test",
            label=f"test: {path}",
            path=path,
            language=language,
            evidence_level=evidence_level,
            detection_method=detection_method,
        )

    # -- aristas -----------------------------------------------------------
    def add_edge(
        self,
        source_node_id: str,
        *,
        edge_type: str,
        evidence_level: str,
        detection_method: str,
        target_node_id: str | None = None,
        target_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        key = (source_node_id, edge_type, target_node_id, target_ref, evidence_level)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self._edges.append(
            GraphEdge(
                edge_id=new_id("edg"),
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                target_ref=target_ref,
                edge_type=edge_type,
                evidence_level=evidence_level,
                detection_method=detection_method,
                metadata=metadata or {},
            )
        )

    # -- consultas ---------------------------------------------------------
    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def nodes(self) -> list[GraphNode]:
        return list(self._nodes.values())

    def node_records(self, *, analysis_id: str, project_id: str, organization_id: str, created_at: str) -> list[dict[str, Any]]:
        return [
            {
                "id": node.node_id,
                "analysis_id": analysis_id,
                "project_id": project_id,
                "organization_id": organization_id,
                "node_type": node.node_type,
                "label": node.label,
                "path": node.path,
                "language": node.language,
                "evidence_level": node.evidence_level,
                "detection_method": node.detection_method,
                "metadata": json.dumps(node.metadata, ensure_ascii=False),
                "created_at": created_at,
            }
            for node in self._nodes.values()
        ]

    def edge_records(self, *, analysis_id: str, project_id: str, organization_id: str, created_at: str) -> list[dict[str, Any]]:
        return [
            {
                "id": edge.edge_id,
                "analysis_id": analysis_id,
                "project_id": project_id,
                "organization_id": organization_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "target_ref": edge.target_ref,
                "edge_type": edge.edge_type,
                "evidence_level": edge.evidence_level,
                "detection_method": edge.detection_method,
                "metadata": json.dumps(edge.metadata, ensure_ascii=False),
                "created_at": created_at,
            }
            for edge in self._edges
        ]

    def node_type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self._nodes.values():
            counts[node.node_type] = counts.get(node.node_type, 0) + 1
        return counts

    def edge_type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for edge in self._edges:
            counts[edge.edge_type] = counts.get(edge.edge_type, 0) + 1
        return counts

    def confirmed_edge_count(self) -> int:
        return sum(1 for edge in self._edges if edge.evidence_level == "DIRECT_EVIDENCE")

    def inferred_edge_count(self) -> int:
        return sum(1 for edge in self._edges if edge.evidence_level == "STATIC_INFERENCE")
