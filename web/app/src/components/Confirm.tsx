// Modal confirmation for actions that delete data (native <dialog>: focus trap, Esc to cancel).
import { useEffect, useRef, type ReactNode } from "react";
import { useApp } from "../state";

type Props = {
  open: boolean;
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function Confirm({ open, title, children, confirmLabel, danger, onConfirm, onCancel }: Props) {
  const { L } = useApp();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} className="confirm" onCancel={(e) => { e.preventDefault(); onCancel(); }} aria-labelledby="confirm-title">
      <h2 id="confirm-title">{title}</h2>
      {children && <div className="confirm-body">{children}</div>}
      <div className="confirm-actions">
        <button type="button" className="btn" onClick={onCancel} autoFocus>{L("cancel")}</button>
        <button type="button" className={`btn ${danger ? "danger" : "primary"}`} onClick={onConfirm} data-testid="confirm-ok">
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
