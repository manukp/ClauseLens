import { useMemo } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "reactflow";
import dagre from "dagre";
import "reactflow/dist/style.css";
import type { EntityGraph as EntityGraphData } from "../lib/types";

// react-flow graph on the navy stage (D12). The mockup's SVG node positions are
// illustrative only — node placement and edge routing come from dagre + react-flow
// here; we match the mockup's STYLING (light node cards, type ticks, conflict
// edges in garnet). Relationship edges are slate; conflicts_with are garnet dashed.

const NODE_W = 172;
const NODE_H = 62;

const TICK: Record<string, string> = {
  organisation: "#475569", // slate
  person: "#D97706", // marigold (per the graph mockup legend)
  deliverable: "#4D7C6F", // sage
};
const TYPE_LABEL: Record<string, string> = {
  organisation: "Organisation",
  person: "Role / person",
  deliverable: "Deliverable",
};

export interface EntityNodeData {
  label: string;
  type: string;
  flagged: boolean;
}

function EntityNode({ data, selected }: NodeProps<EntityNodeData>) {
  const tick = TICK[data.type] ?? "#475569";
  return (
    <div
      className={[
        "relative w-[172px] rounded-[11px] px-3 py-2.5 transition-transform",
        selected
          ? "bg-white ring-2 ring-marigold ring-offset-2 ring-offset-ink"
          : "bg-[#FBF9F5]",
        data.flagged ? "border-[1.5px] border-dashed border-severity-high" : "border border-white/60",
      ].join(" ")}
      style={{ boxShadow: "0 10px 22px -12px rgba(0,0,0,.55)" }}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate">
        <span className="h-2 w-2 rounded-[2px]" style={{ background: tick }} />
        {TYPE_LABEL[data.type] ?? data.type}
      </div>
      <div className="mt-1 text-[13.5px] font-semibold leading-tight text-ink">{data.label}</div>
      {data.flagged && (
        <span className="absolute -right-2 -top-2 rounded-full bg-severity-high px-2 py-0.5 text-[10px] font-semibold text-white shadow">
          High risk
        </span>
      )}
      <Handle type="source" position={Position.Right} className="!opacity-0" />
    </div>
  );
}

const nodeTypes = { entity: EntityNode };

function layout(
  graph: EntityGraphData,
  flaggedIds: Set<string>,
): { nodes: Node<EntityNodeData>[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 36, ranksep: 96, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(() => ({}));

  graph.nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  graph.edges.forEach((e) => {
    if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target);
  });
  dagre.layout(g);

  const nodes: Node<EntityNodeData>[] = graph.nodes.map((n) => {
    const p = g.node(n.id);
    return {
      id: n.id,
      type: "entity",
      position: { x: (p?.x ?? 0) - NODE_W / 2, y: (p?.y ?? 0) - NODE_H / 2 },
      data: { label: n.label, type: n.type, flagged: flaggedIds.has(n.id) },
    };
  });

  const edges: Edge[] = graph.edges.map((e) => {
    const conflict = e.relation === "conflicts_with";
    const color = conflict ? "#B14A4A" : "#5E6B7C";
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label || e.relation.replace(/_/g, " "),
      // Bezier (react-flow's "default") rather than orthogonal smoothstep, so
      // overlapping relationship paths are easier to follow.
      type: "default",
      animated: conflict,
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      style: { stroke: color, strokeWidth: conflict ? 1.8 : 1.4, strokeDasharray: conflict ? "6 5" : undefined },
      labelStyle: { fill: conflict ? "#E9A6A6" : "#9AA4B2", fontSize: 10.5, fontWeight: 500 },
      labelBgStyle: { fill: conflict ? "rgba(50,18,18,.85)" : "rgba(20,28,38,.78)" },
      labelBgPadding: [6, 3] as [number, number],
      labelBgBorderRadius: 6,
    };
  });

  return { nodes, edges };
}

export default function EntityGraph({
  graph,
  flaggedIds,
  onSelect,
}: {
  graph: EntityGraphData;
  flaggedIds: Set<string>;
  onSelect: (nodeId: string | null) => void;
}) {
  const { nodes, edges } = useMemo(() => layout(graph, flaggedIds), [graph, flaggedIds]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.18 }}
      minZoom={0.3}
      maxZoom={1.6}
      proOptions={{ hideAttribution: true }}
      onNodeClick={(_, node) => onSelect(node.id)}
      onPaneClick={() => onSelect(null)}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#33404f" />
    </ReactFlow>
  );
}
