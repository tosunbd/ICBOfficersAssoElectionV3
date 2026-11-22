"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";

export interface PaletteCommand {
  id: string;
  label: string;
  group: string;
  icon: IconName;
  hint?: string;
  keywords?: string;
  run: () => void;
}

/** Ctrl/⌘+K quick switcher for pages and common actions. */
export function CommandPalette({ open, onClose, commands }: { open: boolean; onClose: () => void; commands: PaletteCommand[] }) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => `${c.label} ${c.group} ${c.keywords ?? ""}`.toLowerCase().includes(q));
  }, [commands, query]);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => { setQuery(""); setCursor(0); input.current?.focus(); });
    return () => cancelAnimationFrame(frame);
  }, [open]);

  if (!open) return null;

  const choose = (command: PaletteCommand | undefined) => {
    if (!command) return;
    onClose();
    command.run();
  };

  const onKey = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") { event.preventDefault(); setCursor((c) => Math.min(matches.length - 1, c + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setCursor((c) => Math.max(0, c - 1)); }
    else if (event.key === "Enter") { event.preventDefault(); choose(matches[cursor]); }
    else if (event.key === "Escape") { event.preventDefault(); onClose(); }
  };

  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette" onClick={(e) => e.stopPropagation()} onKeyDown={onKey}>
        <div className="palette-input">
          <Icon name="search" size={19} />
          <input ref={input} value={query} placeholder="Jump to a page or run an action…"
            onChange={(e) => { setQuery(e.target.value); setCursor(0); }} aria-label="Search commands" />
          <span className="kbd">Esc</span>
        </div>
        <ul className="palette-list" role="listbox">
          {matches.length === 0 && <li className="empty-inline"><Icon name="search" size={24} />Nothing matches “{query}”</li>}
          {matches.map((command, index) => {
            const header = index === 0 || matches[index - 1].group !== command.group ? command.group : null;
            return (
              <li key={command.id} role="presentation">
                {header && <div className="palette-group">{header}</div>}
                <div role="option" aria-selected={index === cursor} className={`palette-item ${index === cursor ? "selected" : ""}`}
                  onMouseEnter={() => setCursor(index)} onClick={() => choose(command)}>
                  <span className="icon-box"><Icon name={command.icon} size={16} /></span>
                  {command.label}
                  {command.hint && <span className="hint">{command.hint}</span>}
                </div>
              </li>
            );
          })}
        </ul>
        <div className="palette-foot">
          <span><span className="kbd">↑</span><span className="kbd">↓</span> navigate</span>
          <span><span className="kbd">↵</span> open</span>
          <span><span className="kbd">Ctrl</span><span className="kbd">K</span> toggle</span>
        </div>
      </div>
    </div>
  );
}
