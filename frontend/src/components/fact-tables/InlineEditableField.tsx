import { cn } from "@/lib/utils";
import { Check, Pencil } from "lucide-react";
import { type ReactNode, useRef, useState } from "react";

interface Props {
  label: string;
  value: string | number | null;
  onSave: (v: string | number) => void;
  type?: "text" | "textarea" | "number" | "select";
  options?: string[];
  render?: (v: string | number | null) => ReactNode;
}

export function InlineEditableField({ label, value, onSave, type = "text", options, render }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value ?? ""));
  const ref = useRef<HTMLInputElement & HTMLTextAreaElement & HTMLSelectElement>(null);

  const start = () => { setDraft(String(value ?? "")); setEditing(true); };
  const save = () => {
    const v = type === "number" ? Number(draft) : draft;
    onSave(v);
    setEditing(false);
  };
  const cancel = () => setEditing(false);

  if (editing) {
    const inputCls = "w-full rounded-md border bg-background px-2 py-1 text-sm outline-none focus:border-primary";
    if (type === "textarea") {
      return (
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">{label}</label>
          <textarea ref={ref} value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={save} rows={3} className={cn(inputCls, "resize-y")} autoFocus />
        </div>
      );
    }
    if (type === "select" && options) {
      return (
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">{label}</label>
          <select ref={ref} value={draft} onChange={(e) => { setDraft(e.target.value); save(); }} onBlur={cancel} className={inputCls} autoFocus>
            {options.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
      );
    }
    return (
      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground">{label}</label>
        <input ref={ref} type={type === "number" ? "number" : "text"} value={draft} onChange={(e) => setDraft(e.target.value)}
          onBlur={save} onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") cancel(); }}
          className={inputCls} autoFocus />
      </div>
    );
  }

  return (
    <div className="group/field cursor-pointer space-y-0.5" onClick={start}>
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <div className="flex items-start gap-1.5">
        <div className="min-w-0 flex-1 text-sm">
          {render ? render(value) : (value != null && value !== "" ? String(value) : <span className="text-muted-foreground">—</span>)}
        </div>
        <Pencil className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground opacity-0 group-hover/field:opacity-100 transition-opacity" />
      </div>
    </div>
  );
}
