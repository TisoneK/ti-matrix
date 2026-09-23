/*
 * The confirmer: the engine wants to change something and nothing happens until a person says so.
 *
 * Escape declines. That is the same default the engine already takes from a dropped socket or a closed
 * terminal — a question that goes unanswered is not a yes — so the keyboard can never grant by accident.
 */

import { Button } from "../ui/Controls";
import { Modal } from "../ui/Modal";

export interface ConfirmRequest {
  id: string;
  action: { tool: string; args: Record<string, unknown>; label: string };
  reason: string;
}

export function ConfirmDialog({ request, onAnswer }: {
  request: ConfirmRequest | null;
  onAnswer: (granted: boolean) => void;
}) {
  if (!request) return null;
  return (
    <Modal tone="warn" title="the engine wants to change something" onClose={() => onAnswer(false)}
           footer={
             <div className="dialog-actions">
               <Button variant="primary" onClick={() => onAnswer(true)}>Allow this once</Button>
               <Button variant="ghost" onClick={() => onAnswer(false)}>Deny</Button>
             </div>
           }>
      <pre className="action">{request.action.label}</pre>
      <p className="why"><b>because:</b> {request.reason || "no reason given"}</p>
      <p className="hint">Escape denies, and a run that gets no answer treats it as one.</p>
    </Modal>
  );
}
