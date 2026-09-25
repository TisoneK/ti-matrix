/*
 * What a run has amounted to so far.
 *
 * The engine's own record is facts, not chatter: every `state` carries the bounded text of the
 * observations it holds (`fact_list`, the same lines the model is shown) and the moves it has ruled out.
 * That is what a person watching wants first — what does it know, what has it excluded, how far has it
 * got — and the event log is the raw material behind it, not the headline.
 */

import { EngineEventFrame } from "../protocol";

export interface Vitals {
  progress: number;
  depth: number;
  facts: string[];
  deadEnds: string[];
  ruledOut: number;
  modelCalls: number;
  trail: string[];
  settled: boolean;
  events: number;
}

export function readVitals(events: EngineEventFrame[]): Vitals {
  const v: Vitals = {
    progress: 0, depth: 0, facts: [], deadEnds: [], ruledOut: 0, modelCalls: 0, trail: [],
    settled: false, events: events.length,
  };
  for (const e of events) {
    switch (e.kind) {
      case "state": {
        v.progress = Number(e["progress"] ?? v.progress);
        v.depth = Number(e["depth"] ?? v.depth);
        if (Array.isArray(e["fact_list"])) v.facts = (e["fact_list"] as unknown[]).map(String);
        if (Array.isArray(e["failed_fps"])) v.ruledOut = (e["failed_fps"] as unknown[]).length;
        if (Array.isArray(e["trail"])) v.trail = (e["trail"] as unknown[]).map(String);
        break;
      }
      case "probe": {
        // A probe that failed is a move this run will not propose again — worth naming, not counting.
        if (!e["ok"]) v.deadEnds.push(String(e["move"] ?? ""));
        break;
      }
      case "done": {
        v.settled = true;
        v.progress = 1;
        v.modelCalls = Number(e["model_calls"] ?? v.modelCalls);
        if (Array.isArray(e["trail"])) v.trail = (e["trail"] as unknown[]).map(String);
        break;
      }
      case "stopped": {
        v.modelCalls = Number(e["model_calls"] ?? v.modelCalls);
        if (Array.isArray(e["trail"])) v.trail = (e["trail"] as unknown[]).map(String);
        break;
      }
      default:
        break;
    }
  }
  return v;
}

/** The newest fact first: the last thing learned is the thing being read. */
export function newestFirst(facts: string[]): string[] {
  return [...facts].reverse();
}
