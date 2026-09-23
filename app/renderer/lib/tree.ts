/*
 * The shape of the search itself.
 *
 * Every `state` event carries the trail of actions that reached it, so the tree is not an invention: a
 * state whose trail is another's plus one step *is* its child. `selected` says which branch the engine
 * committed to, and a `backtrack` says it gave one up — so the picture shows the beam widening, the
 * deepest line being the live one, and the branches it pruned going cold.
 */

import { EngineEventFrame } from "../protocol";

export interface TreeNode {
  id: string;
  parent: string | null;
  depth: number;
  last: string;
  progress: number;
  facts: number;
  seq: number;
  children: string[];
  dead: boolean;
  current: boolean;
}

export interface SearchTree {
  nodes: Map<string, TreeNode>;
  roots: string[];
  current: string | null;
  backtracks: number;
  maxDepth: number;
  progress: number;
  states: number;
}

const ROOT = "(start)";

export function readTree(events: EngineEventFrame[]): SearchTree {
  const tree: SearchTree = {
    nodes: new Map(), roots: [], current: null, backtracks: 0, maxDepth: 0, progress: 0, states: 0,
  };

  const ensure = (trail: string[]): TreeNode => {
    const id = trail.length === 0 ? ROOT : trail.join(" → ");
    let node = tree.nodes.get(id);
    if (!node) {
      const parentTrail = trail.slice(0, -1);
      const parent = trail.length === 0 ? null : (parentTrail.length === 0 ? ROOT : parentTrail.join(" → "));
      node = {
        id, parent, depth: trail.length, last: trail[trail.length - 1] ?? "",
        progress: 0, facts: 0, seq: 0, children: [], dead: false, current: false,
      };
      tree.nodes.set(id, node);
      if (parent && tree.nodes.has(parent)) tree.nodes.get(parent)!.children.push(id);
      else if (parent) tree.roots.push(parent);
      else if (trail.length === 0) tree.roots.push(id);
    }
    return node;
  };

  const parentOf = (id: string): string | null => tree.nodes.get(id)?.parent ?? null;

  for (const e of events) {
    if (e.kind === "state") {
      const trail = Array.isArray(e["trail"]) ? (e["trail"] as string[]).map(String) : [];
      const node = ensure(trail);
      node.progress = Number(e["progress"] ?? node.progress);
      node.facts = Number(e["facts"] ?? node.facts);
      node.seq = e.seq;
      for (const other of tree.nodes.values()) other.current = false;
      node.current = true;
      tree.current = node.id;
      tree.maxDepth = Math.max(tree.maxDepth, node.depth);
      tree.progress = node.progress;
      tree.states += 1;
    } else if (e.kind === "backtrack") {
      tree.backtracks += 1;
      const toDepth = Number(e["to_depth"] ?? 0);
      // Everything deeper than where the engine retreated to is abandoned — that is what a backtrack is.
      let id = tree.current;
      while (id) {
        const node = tree.nodes.get(id);
        if (!node || node.depth <= toDepth) break;
        node.dead = true;
        node.current = false;
        id = parentOf(node.id);
      }
      if (id) {
        const node = tree.nodes.get(id);
        if (node) {
          node.current = true;
          tree.current = node.id;
          tree.progress = node.progress;
        }
      }
    }
  }
  return tree;
}

export interface Placed {
  node: TreeNode;
  x: number;
  y: number;
}

export interface TreeLayout {
  placed: Placed[];
  edges: { from: Placed; to: Placed; dead: boolean }[];
  width: number;
  height: number;
}

/**
 * Depth runs down the page, siblings spread across it. Leaves take the next free column and every parent
 * sits over the middle of its children, which is the whole of the layout — a search tree is small.
 */
export function layoutTree(tree: SearchTree, opts: { xGap?: number; yGap?: number } = {}): TreeLayout {
  const xGap = opts.xGap ?? 26;
  const yGap = opts.yGap ?? 34;
  const placed: Placed[] = [];
  const byId = new Map<string, Placed>();
  let column = 0;

  const walk = (id: string, depth: number): Placed | null => {
    const node = tree.nodes.get(id);
    if (!node) return null;
    const children = node.children.map((c) => tree.nodes.get(c)).filter((c): c is TreeNode => Boolean(c));
    let x: number;
    if (children.length === 0) {
      x = column * xGap;
      column += 1;
    } else {
      const spots = children.map((c) => walk(c.id, depth + 1)).filter((p): p is Placed => p !== null);
      x = spots.length > 0 ? (spots[0].x + spots[spots.length - 1].x) / 2 : column++ * xGap;
    }
    const spot: Placed = { node, x, y: depth * yGap };
    placed.push(spot);
    byId.set(id, spot);
    return spot;
  };

  for (const root of tree.roots) walk(root, 0);

  const edges = placed
    .filter((p) => p.node.parent)
    .map((p) => ({ from: byId.get(p.node.parent!)!, to: p, dead: p.node.dead }))
    .filter((e) => Boolean(e.from));

  const width = Math.max(1, column) * xGap;
  const height = (tree.maxDepth + 1) * yGap;
  return { placed, edges, width, height };
}
