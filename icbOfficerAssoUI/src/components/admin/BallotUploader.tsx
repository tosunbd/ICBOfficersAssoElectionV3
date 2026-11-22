"use client";

import { useRef, useState, type DragEvent } from "react";
import { Icon } from "@/components/ui/Icon";

const ACCEPT = [".pdf", ".jpg", ".jpeg", ".jfif", ".png", ".tif", ".tiff", ".bmp", ".webp"];

interface Props {
  disabled?: boolean;
  busy?: boolean;
  onUpload: (files: File[]) => Promise<void>;
}

/** Drag-and-drop / click-to-select uploader for scanned ballot files. */
export function BallotUploader({ disabled, busy, onUpload }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const accept = (list: FileList | null) => {
    if (!list) return;
    const picked = Array.from(list).filter((f) => ACCEPT.some((ext) => f.name.toLowerCase().endsWith(ext)));
    setFiles(picked);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    if (!disabled) accept(event.dataTransfer.files);
  };

  const submit = async () => {
    if (!files.length) return;
    await onUpload(files);
    setFiles([]);
    if (input.current) input.current.value = "";
  };

  return (
    <div>
      <div
        className={`upload-zone ${dragOver ? "drag-over" : ""} ${disabled ? "disabled" : ""}`}
        onClick={() => !disabled && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !disabled) { e.preventDefault(); input.current?.click(); } }}
      >
        <div className="upload-icon"><Icon name="upload" size={28} /></div>
        <p className="upload-text">
          <strong>{dragOver ? "Release to add the ballots" : "Click to choose"}</strong>{dragOver ? "" : " or drag scanned ballots here"}<br />
          <span className="text-faint text-xs">PDF or image (JPG, PNG, TIFF, BMP, WebP) · multi-page PDF/TIFF allowed</span>
        </p>
        {files.length > 0 && (
          <div className="file-chips">
            {files.slice(0, 6).map((f) => <span key={f.name} className="file-chip"><Icon name="file" size={13} />{f.name}</span>)}
            {files.length > 6 && <span className="file-chip">+{files.length - 6} more</span>}
          </div>
        )}
        <input ref={input} type="file" multiple accept={ACCEPT.join(",")} style={{ display: "none" }} onChange={(e) => accept(e.target.files)} />
      </div>
      <div className="flex gap-3 mt-4 items-center">
        <button className="btn btn-primary" onClick={submit} disabled={disabled || busy || files.length === 0}>
          {busy ? <><span className="btn-spinner" /> Processing…</> : <><Icon name="upload" size={16} /> Upload & process{files.length ? ` ${files.length} file${files.length > 1 ? "s" : ""}` : ""}</>}
        </button>
        {files.length > 0 && !busy && (
          <button className="btn btn-ghost" onClick={() => setFiles([])}><Icon name="x" size={15} /> Clear</button>
        )}
      </div>
    </div>
  );
}
