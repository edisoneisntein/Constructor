"use client";

import { useMemo } from "react";
import type { ArchitectureGraph, GraphNode } from "@/lib/api";

const COLUMN_WIDTH = 240;
const ROW_HEIGHT = 46;

const TYPE_COLORS: Record<string, string> = {
  file: "#38bdf8",
  manifest: "#a78bfa",
  dependency: "#f472b6",
  integration: "#34d399",
  env_var: "#fbbf24",
  symbol: "#94a3b8",
  api_route: "#22d3ee",
  entrypoint: "#facc15",
  test: "#4ade80",
};

function layout(nodes: GraphNode[]): { positions: Map<string, { x: number; y: number }>; columns: string[] } {
  const byType = new Map<string, GraphNode[]>();
  for (const node of nodes) {
    const list = byType.get(node.node_type) ?? [];
    list.push(node);
    byType.set(node.node_type, list);
  }
  const columns = Array.from(byType.keys()).sort();
  const positions = new Map<string, { x: number; y: number }>();
  columns.forEach((type, columnIndex) => {
    const list = byType.get(type) ?? [];
    list.forEach((node, rowIndex) => {
      positions.set(node.id, { x: columnIndex * COLUMN_WIDTH + 12, y: rowIndex * ROW_HEIGHT + 30 });
    });
  });
  return { positions, columns };
}

export default function GraphView({
  graph,
  selectedNodeId,
  onSelectNode,
}: {
  graph: ArchitectureGraph;
  selectedNodeId?: string | null;
  onSelectNode?: (nodeId: string) => void;
}) {
  const { positions, columns } = useMemo(() => layout(graph.nodes), [graph.nodes]);
  const width = Math.max(COLUMN_WIDTH, columns.length * COLUMN_WIDTH);
  const maxRows = columns.reduce((max, type) => {
    const count = graph.nodes.filter((node) => node.node_type === type).length;
    return Math.max(max, count);
  }, 1);
  const height = maxRows * ROW_HEIGHT + 80;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-4 text-xs text-slate-400">
        <span>Nodos: {graph.node_count}</span>
        <span>Aristas: {graph.edge_count}</span>
        <span>Dependencias: {graph.dependency_count}</span>
        <span className="text-emerald-400">Confirmadas: {graph.confirmed_edge_count}</span>
        <span className="text-amber-400">Inferidas: {graph.inferred_edge_count}</span>
      </div>

      {graph.node_type_counts && (
        <div className="flex flex-wrap gap-2 text-xs">
          {Object.entries(graph.node_type_counts).map(([type, count]) => (
            <span key={type} className="rounded border border-slate-800 px-2 py-0.5">
              <span style={{ color: TYPE_COLORS[type] ?? "#94a3b8" }}>●</span> {type}: {count}
            </span>
          ))}
        </div>
      )}

      <div className="overflow-x-auto rounded-md border border-slate-800 bg-slate-950 p-2">
        <svg width={width} height={height} role="img" aria-label="Grafo de arquitectura">
          {graph.edges.map((edge) => {
            const source = positions.get(edge.source_node_id);
            const target = edge.target_node_id ? positions.get(edge.target_node_id) : undefined;
            if (!source || !target) return null;
            return (
              <line
                key={edge.id}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke={edge.evidence_level === "DIRECT_EVIDENCE" ? "#34d399" : "#fbbf24"}
                strokeWidth={0.75}
                strokeDasharray={edge.evidence_level === "DIRECT_EVIDENCE" ? undefined : "4 3"}
              />
            );
          })}

          {columns.map((type, columnIndex) => (
            <text key={type} x={columnIndex * COLUMN_WIDTH + 12} y={14} fill="#64748b" fontSize="10">
              {type}
            </text>
          ))}

          {graph.nodes.map((node) => {
            const position = positions.get(node.id);
            if (!position) return null;
            const selected = node.id === selectedNodeId;
            return (
              <g
                key={node.id}
                onClick={onSelectNode ? () => onSelectNode(node.id) : undefined}
                style={{ cursor: onSelectNode ? "pointer" : "default" }}
              >
                <circle
                  cx={position.x}
                  cy={position.y}
                  r={selected ? 6 : 4}
                  fill={TYPE_COLORS[node.node_type] ?? "#38bdf8"}
                  stroke={selected ? "#f8fafc" : "none"}
                  strokeWidth={selected ? 2 : 0}
                />
                <text x={position.x + 10} y={position.y + 4} fill="#cbd5e1" fontSize="11">
                  {node.label.length > 26 ? `${node.label.slice(0, 26)}…` : node.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <p className="text-xs text-slate-500">
        Línea continua = evidencia directa; línea discontinua = inferencia estática. Haz clic en un nodo para inspeccionarlo.
      </p>
    </div>
  );
}
