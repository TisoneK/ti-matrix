/*
 * One view per world.
 *
 * A world is a name, a few settings fields and an Environment (server/appserver/worlds.py), so the app can
 * only draw a world it has been taught — and a registry the app has not been taught still renders: it falls
 * back to the raw record of what each probe asked and was told, which is the same text the engine's facts
 * carry. Nothing breaks by adding a world on the server side; it just looks plainer until it gets a view.
 */

import { EngineEventFrame } from "../protocol";
import { probesOf } from "../lib/probe";
import { Panel, Empty } from "../ui/Panel";
import { BrowserView } from "./BrowserView";
import { FilesView } from "./FilesView";
import { LedgerView } from "./LedgerView";
import { MazeView } from "./MazeView";

const VIEWS: Record<string, (props: { events: EngineEventFrame[] }) => JSX.Element> = {
  maze: MazeView,
  files: FilesView,
  ledger: LedgerView,
  browser: BrowserView,
};

function GenericView({ events }: { events: EngineEventFrame[] }) {
  const probes = probesOf(events);
  return (
    <Panel title="what the run asked and was told" meta={`${probes.length} probes`}>
      {probes.length === 0 ? (
        <Empty>Nothing yet — this world has no dedicated view, so the record is shown as it is.</Empty>
      ) : (
        <ul className="plain-list probes">
          {probes.map((p) => (
            <li key={p.seq} className={p.ok ? "" : "bad"}>
              <code className="tool">{p.move}</code>
              <span className="detail">{p.excerpt || "(no answer)"}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function WorldView({ world, events }: { world: string; events: EngineEventFrame[] }) {
  const View = VIEWS[world] ?? GenericView;
  return <View events={events} />;
}

/** Whether a world is worth a panel before the run has said anything at all. */
export const WORLD_VIEWS = Object.keys(VIEWS);
