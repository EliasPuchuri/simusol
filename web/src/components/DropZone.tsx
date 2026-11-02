import { useRef, useState } from "react";

import { filesFromDrop, folderLabel } from "../format";

type Props = {
  folderLabelText: string;
  disabled?: boolean;
  compact?: boolean;
  onFiles: (files: File[], folder: string) => void;
};

export function DropZone({ folderLabelText, disabled, compact, onFiles }: Props) {
  const folderInput = useRef<HTMLInputElement>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const picked = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length > 0) onFiles(files, folderLabel(files));
  };

  return (
    <div
      className={`dropzone${over ? " dropzone-over" : ""}${compact ? " dropzone-compact" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={async (e) => {
        e.preventDefault();
        setOver(false);
        if (disabled) return;
        const { files, folder } = await filesFromDrop(e.dataTransfer);
        if (files.length > 0) onFiles(files, folder);
      }}
    >
      <p className="dropzone-title">
        {compact ? "Arrastra aquí más archivos" : "Arrastra aquí la carpeta con los archivos .obj"}
      </p>
      <p className="dropzone-actions">
        <button type="button" className="primary" disabled={disabled} onClick={() => folderInput.current?.click()}>
          Elegir carpeta
        </button>
        <button type="button" className="link" disabled={disabled} onClick={() => filesInput.current?.click()}>
          o elegir archivos sueltos
        </button>
      </p>
      <input ref={folderInput} className="sr-only" type="file" multiple tabIndex={-1} aria-label={folderLabelText}
        onChange={picked} {...({ webkitdirectory: "" } as Record<string, string>)} />
      <input ref={filesInput} className="sr-only" type="file" multiple accept=".obj" tabIndex={-1}
        aria-label={`${folderLabelText.replace("Carpeta", "Archivos")}`} onChange={picked} />
    </div>
  );
}
