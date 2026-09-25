/*
 * The shape of the search itself — a real tree, drawn from the engine's own bookkeeping.
 *
 * The engine hands out the ids (`search.py` stamps every event): a `state` event carries `node` and
 * `parent`, a `backtrack` names the node it returns to, and every other event carries `at`, the node the
 * run was standing on when it happened. So the tree is read, not inferred — the parent of a node is what
 * the engine said it was, and a decision belongs to the node it was taken from because the event said so.
 *
 * A log without those fields is still read: an older engine, or a run log from a CLI, falls back to
 * deriving the shape from the `trail` each state carries (a state whose trail is another's plus one step is
 * its child). The fallback is strictly worse — it cannot see a re-parented ancestor after a retreat — so it
 * exists for compatibility, not as the normal path.
 *
 * Folding is a view concern and lives here anyway, because a long run's tree is unreadable without it: a
 * cold subtree collapses into the node it branched from, and manual collapse is per-node.
 */

import { Decision, EngineEventFrame } from "./types";
import { foldDecisions } from "./decisions";

export interface TreeNode {
  id: string;
  parent: string | null;
  depth: number;
  /** The move that reached this node — the last entry of its trail. */
  last: string;
  progress: number;
  facts: number;
  /** Event index of the `state` event that announced this node. */
  enteredAt: number;
  /**
   * The decision this node *is*: the one that selected the move reaching it, so the node can answer "why
   * this branch over its siblings?". For the entry state — which no decision created — it is the first
   * decision taken from it.
   */
  decision: number | null;
  children: string[];
  /** The engine retreated past this node; nothing below it is live any more. */
  dead: boolean;
  /** The node the run was standing on when the log ends. */
  current: boolean;
  /** Depth-first position, filled by the layout. */
  x: number;
  y: number;
}

export interface SearchTree {
  nodes: Map<string, TreeNode>;
  roots: string[];
  current: string | null;
  backtracks: number;
  maxDepth: number;
  progress: number;
  /** How many states the run stood on — not the number of events. */
  states: number;
  /** False when the log had no engine-supplied ids and the shape was derived from trails. */
  authoritative: boolean;
}

/** The root's trail is empty; this is what a fallback-derived root is called. */
export const ROOT = "(entry)";

const idOf = (trail: string[]): string => (trail.length === 0 ? ROOT : trail.join(" → "));

/**
 * The tree as it stood after `upto` events. Nodes appear when first stood on and go cold when the engine
 * retreats past them, so scrubbing back shows the search as it looked, not as it ended up.
 */
export function readTree(events: EngineEventFrame[], upto = events.length, decisions?: Decision[]): SearchTree {
  const limit = Math.max(0, Math.min(upto, events.length));
  const run = decisions ?? foldDecisions(events.slice(0, limit));
  const tree: SearchTree = {
    nodes: new Map(), roots: [], current: null, backtracks: 0, maxDepth: 0, progress: 0,
    states: 0, authoritative: true,
  };

  /** The node each event index was standing on — read from `at`, or from whatever state preceded it. */
  const nodeAt: (string | null)[] = new Array(limit).fill(null);

  const ensure = (id: string, parent: string | null, depth: number, at: number, last: string): TreeNode => {
    let node = tree.nodes.get(id);
    if (!node) {
      node = {
        id, parent, depth, last, progress: 0, facts: 0, enteredAt: at, decision: null,
        children: [], dead: false, current: false, x: 0, y: depth,
      };
      tree.nodes.set(id, node);
      if (parent && tree.nodes.has(parent)) tree.nodes.get(parent)!.children.push(id);
      else if (id === ROOT || parent === null) tree.roots.push(id);
    }
    return node;
  };

  for (let i = 0; i < limit; i += 1) {
    const e = events[i];
    const at = typeof e["at"] === "string" ? (e["at"] as string) : null;

    if (e.kind === "state") {
      const trail = Array.isArray(e["trail"]) ? (e["trail"] as unknown[]).map(String) : [];
      const declared = typeof e["node"] === "string" ? (e["node"] as string) : null;
      const parentField = e["parent"];
      if (declared === null) tree.authoritative = false;
      const id = declared ?? idOf(trail);
      const parent = declared === null
        ? (trail.length === 0 ? null : idOf(trail.slice(0, -1)))
        : (typeof parentField === "string" ? parentField : null);
      const node = ensure(id, parent, Number(e["depth"] ?? trail.length), i, trail[trail.length - 1] ?? "");
      node.progress = Number(e["progress"] ?? node.progress);
      node.facts = Number(e["facts"] ?? node.facts);
      node.enteredAt = Math.min(node.enteredAt, i);
      for (const other of tree.nodes.values()) other.current = false;
      node.current = true;
      // Standing on a node again after a retreat makes it live: the run is back.
      node.dead = false;
      tree.current = node.id;
      tree.maxDepth = Math.max(tree.maxDepth, node.depth);
      tree.progress = node.progress;
      tree.states += 1;
      nodeAt[i] = node.id;
      continue;
    }

    if (e.kind === "backtrack") {
      tree.backtracks += 1;
      const target = typeof e["node"] === "string" ? (e["node"] as string)
        : ancestorAtDepth(tree, tree.current, Number(e["to_depth"] ?? 0));
      // Everything between where the run stood and where it retreated to is abandoned — that is what a
      // backtrack is, and the engine's stack says exactly which nodes those are.
      let id = tree.current;
      while (id && id !== target) {
        const node = tree.nodes.get(id);
        if (!node) break;
        node.dead = true;
        node.current = false;
        id = node.parent;
      }
      const back = target ? tree.nodes.get(target) : undefined;
      for (const other of tree.nodes.values()) other.current = false;
      if (back) {
        back.current = true;
        back.dead = false;
        tree.current = back.id;
        tree.progress = back.progress;
      }
      nodeAt[i] = tree.current;
      continue;
    }

    nodeAt[i] = at ?? tree.current;
  }

  // Which decision each node is: the selection that created it, found through the decision's own event span.
  const creatorOf = new Map<string, number>();
  for (let i = 0; i < limit; i += 1) {
    const e = events[i];
    if (e.kind !== "state") continue;
    const id = nodeAt[i];
    if (id === null) continue;
    // The state immediately after a decision's `selected` was produced by that decision.
    for (let d = run.length - 1; d >= 0; d -= 1) {
      const decision = run[d];
      if (decision.from <= i && i <= decision.to && decision.kind !== "backtrack") {
        if (!creatorOf.has(id)) creatorOf.set(id, decision.index);
        break;
      }
    }
  }
  for (const node of tree.nodes.values()) {
    const created = creatorOf.get(node.id);
    node.decision = created ?? firstDecisionAt(run, node.enteredAt);
  }

  for (const node of tree.nodes.values()) node.y = node.depth;
  return tree;
}

/** The first decision taken while the run stood on this node — the entry state's answer to "what happened here". */
function firstDecisionAt(run: Decision[], enteredAt: number): number | null {
  for (const d of run) {
    if (d.from >= enteredAt) return d.index;
  }
  return run.length > 0 ? 0 : null;
}

/** The node at a given depth on the path up from `id` — the fallback when a log predates named nodes. */
function ancestorAtDepth(tree: SearchTree, id: string | null, depth: number): string | null {
  let node = id ? tree.nodes.get(id) : undefined;
  while (node && node.depth > depth) node = node.parent ? tree.nodes.get(node.parent) : undefined;
  return node ? node.id : null;
}

// ── folding ─────────────────────────────────────────────────────────────────

export interface FoldState {
  /** Node ids the viewer collapsed by hand. */
  collapsed: Set<string>;
  /** Fold dead subtrees automatically, which is what keeps a long run's tree legible. */
  foldDead: boolean;
}

export interface FoldedView {
  /** Nodes to draw, with their positions already tidy. */
  visible: TreeNode[];
  /** One entry per folded subtree: the node standing in for it, and how much is inside. */
  folds: { from: string; hidden: number; dead: number }[];
  edges: { from: TreeNode; to: TreeNode; dead: boolean; live: boolean }[];
  width: number;
  height: number;
  columns: number;
}

const subtreeNodes = (tree: SearchTree, id: string): string[] => {
  const out: string[] = [];
  const walk = (n: string): void => {
    out.push(n);
    for (const child of tree.nodes.get(n)?.children ?? []) walk(child);
  };
  walk(id);
  return out;
};

/**
 * The nodes worth drawing, and where.
 *
 * Depth runs down the page and siblings spread across it; a node with a folded subtree drops the whole
 * thing and stands in for it, and a parent sits over the middle of whatever children remain. A search tree
 * this size does not need a general graph layout — it needs to stop being drawn once it is cold.
 */
export function layoutTree(tree: SearchTree, fold: FoldState, opts: { xGap?: number; yGap?: number } = {}): FoldedView {
  const xGap = opts.xGap ?? 30;
  const yGap = opts.yGap ?? 40;
  const hidden = new Set<string>();
  const folds: FoldedView["folds"] = [];

  for (const id of tree.nodes.keys()) {
    if (hidden.has(id)) continue;
    const node = tree.nodes.get(id);
    if (!node || node.children.length === 0) continue;
    // A dead branch with something under it is noise once the run has moved on; a live one is never folded
    // unless the viewer said so.
    if (!fold.collapsed.has(id) && !(fold.foldDead && node.dead)) continue;
    const inside = subtreeNodes(tree, id).filter((n) => n !== id);
    for (const n of inside) hidden.add(n);
    folds.push({ from: id, hidden: inside.length, dead: inside.filter((n) => tree.nodes.get(n)?.dead).length });
  }

  const visible = new Set([...tree.nodes.keys()].filter((id) => !hidden.has(id)));
  const placed = new Map<string, TreeNode>();
  let column = 0;

  const walk = (id: string): number | null => {
    const node = tree.nodes.get(id);
    if (!node || !visible.has(id)) return null;
    const children = node.children.filter((c) => visible.has(c));
    let x: number;
    if (children.length === 0) {
      x = column * xGap;
      column += 1;
    } else {
      const spots = children.map(walk).filter((v): v is number => v !== null);
      x = spots.length > 0 ? (spots[0] + spots[spots.length - 1]) / 2 : (column++) * xGap;
    }
    node.x = x;
    node.y = node.depth * yGap;
    placed.set(id, node);
    return x;
  };

  for (const root of tree.roots) walk(root);

  const edges: FoldedView["edges"] = [];
  for (const node of placed.values()) {
    if (!node.parent) continue;
    const parent = placed.get(node.parent);
    if (!parent) continue;
    edges.push({
      from: parent, to: node, dead: node.dead,
      live: node.current || isAncestor(tree, node.id, tree.current),
    });
  }

  return {
    visible: [...placed.values()],
    folds,
    edges,
    width: Math.max(1, column) * xGap,
    height: (tree.maxDepth + 1) * yGap,
    columns: column,
  };
}

/** Is `ancestor` on the path from the root down to `id`? Used to brighten the line that is still live. */
export function isAncestor(tree: SearchTree, ancestor: string, id: string | null): boolean {
  let node = id ? tree.nodes.get(id) : undefined;
  while (node) {
    if (node.id === ancestor) return true;
    node = node.parent ? tree.nodes.get(node.parent) : undefined;
  }
  return false;
}

/** The nodes from the root down to `id`, entry first. */
export function pathTo(tree: SearchTree, id: string | null): TreeNode[] {
  const out: TreeNode[] = [];
  let node = id ? tree.nodes.get(id) : undefined;
  while (node) {
    out.unshift(node);
    node = node.parent ? tree.nodes.get(node.parent) : undefined;
  }
  return out;
}

/** Why this branch, over its siblings: the options the model offered when this node was created, ranked. */
export function siblingContext(tree: SearchTree, decisions: Decision[], id: string): {
  chosen: Decision | null;
  siblings: { label: string; progress: number; done: boolean; ok: boolean; chosen: boolean }[];
} {
  const node = tree.nodes.get(id);
  const decision = node?.decision === null || node?.decision === undefined ? null : decisions[node.decision] ?? null;
  if (!decision) return { chosen: null, siblings: [] };
  return {
    chosen: decision,
    siblings: decision.options.map((o) => ({
      label: o.label,
      progress: o.progress ?? 0,
      done: Boolean(o.done),
      ok: o.ok !== false,
      chosen: Boolean(o.chosen),
    })),
  };
}
