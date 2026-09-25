/*
 * The confirmer: the engine asking permission, and the answer travelling back.
 *
 * A run performing read-only actions never reaches this. It appears when the engine wants to do something
 * that changes the world — and it blocks the run until answered, which is why it is a modal, why it takes
 * focus, and why the safe answer is the one on the left. A dropped socket is a refusal, so the default is
 * the same everywhere: nothing happens unless a person says so.
 */

import { ConfirmRequest } from "../hooks/useSidecar";
import { Button, Modal } from "../ui/controls";

export function ConfirmDialog({ request, onAnswer }: { request: ConfirmRequest | null; onAnswer: (granted: boolean) => void }) {
  if (request === null) return null;
  const { action } = request;
  const args = Object.entries(action.args ?? {});
  return (
    <Modal
      title="The run wants to change something"
      onClose={() => onAnswer(false)}
      footer={
        <>
          <Button onClick={() => onAnswer(false)} title="refuse — the run treats it as a refused action and carries on">
            Deny
          </Button>
          <Button variant="primary" onClick={() => onAnswer(true)} title="allow this one action">
            Allow once
          </Button>
        </>
      }
    >
      <p>
        This action is not read-only, so the engine will not take it on its own.
        {request.reason ? <> It says: <em>{request.reason}</em></> : null}
      </p>
      <code className="code">{action.label}</code>
      {args.length > 0 ? (
        <code className="code">
          {args.map(([k, v]) => `${k} = ${typeof v === "string" ? v : JSON.stringify(v)}`).join("\n")}
        </code>
      ) : null}
      <p className="dim" style={{ marginTop: 10, fontSize: 11.5 }}>
        Denying does not end the run: the engine records the refusal as an observation and searches on.
      </p>
    </Modal>
  );
}
