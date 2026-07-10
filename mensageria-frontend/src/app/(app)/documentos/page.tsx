"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FileText, Loader2, Upload, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  documentErrorMessage,
  documentsApi,
  type DocumentFormats,
} from "@/lib/api-documents";
import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = {
  pdf: "PDF",
  docx: "Word (.docx)",
  odt: "OpenDocument (.odt)",
  txt: "Texto (.txt)",
  xlsx: "Excel (.xlsx)",
  ods: "Planilha (.ods)",
  csv: "CSV",
};

function extOf(name: string) {
  const parts = name.split(".");
  return parts.length > 1 ? parts.pop()!.toLowerCase() : "";
}

function stemOf(name: string) {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(0, i) : name;
}

function formatBytes(n: number) {
  return n >= 1024 * 1024
    ? `${(n / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(n / 1024))} KB`;
}

export default function DocumentosPage() {
  const [formats, setFormats] = useState<DocumentFormats | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busyTarget, setBusyTarget] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    documentsApi
      .formats()
      .then(setFormats)
      .catch(() => toast.error("Não foi possível carregar os formatos suportados."));
  }, []);

  const ext = file ? extOf(file.name) : "";
  const targets = formats && ext ? (formats.conversions[ext] ?? []) : [];
  const maxBytes = formats?.max_bytes ?? 0;

  function pick(f: File | undefined) {
    if (!f) return;
    if (!formats) return;
    if (maxBytes && f.size > maxBytes) {
      toast.error(`Arquivo excede o limite de ${formatBytes(maxBytes)}.`);
      return;
    }
    if (!formats.conversions[extOf(f.name)]) {
      toast.error(`Formato .${extOf(f.name) || "?"} não é suportado.`);
      return;
    }
    setFile(f);
  }

  async function run(target: string) {
    if (!file) return;
    setBusyTarget(target);
    try {
      const blob = await documentsApi.convert(file, target);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${stemOf(file.name)}.${target}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Convertido para ${LABELS[target] ?? target}.`);
    } catch (err) {
      toast.error(await documentErrorMessage(err));
    } finally {
      setBusyTarget(null);
    }
  }

  const accept = formats
    ? Object.keys(formats.conversions)
        .map((e) => `.${e}`)
        .join(",")
    : undefined;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <FileText className="h-6 w-6 text-emerald-500" />
          Documentos
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Converta documentos, planilhas e PDFs entre formatos. Os arquivos são
          processados de forma isolada e apagados assim que o download termina.
        </p>
      </div>

      <Card
        className={cn(
          "border-2 border-dashed p-10 text-center transition-colors",
          dragging ? "border-emerald-500 bg-emerald-500/5" : "border-muted",
        )}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          pick(e.dataTransfer.files?.[0]);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => {
            pick(e.target.files?.[0]);
            e.target.value = "";
          }}
        />

        {!file ? (
          <div className="space-y-3">
            <Upload className="mx-auto h-10 w-10 text-muted-foreground" />
            <div>
              <Button onClick={() => inputRef.current?.click()} disabled={!formats}>
                Escolher arquivo
              </Button>
              <p className="mt-2 text-xs text-muted-foreground">
                ou arraste aqui
                {maxBytes ? ` — até ${formatBytes(maxBytes)}` : ""}
              </p>
            </div>
            {formats && (
              <p className="text-xs text-muted-foreground">
                Aceita:{" "}
                {Object.keys(formats.conversions)
                  .map((e) => `.${e}`)
                  .join(", ")}
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-center gap-2 text-sm">
              <FileText className="h-4 w-4 shrink-0 text-emerald-500" />
              <span className="truncate font-medium">{file.name}</span>
              <span className="text-muted-foreground">
                ({formatBytes(file.size)})
              </span>
              <button
                aria-label="Remover arquivo"
                onClick={() => setFile(null)}
                disabled={busyTarget !== null}
                className="text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div>
              <p className="mb-3 text-sm text-muted-foreground">Converter para:</p>
              <div className="flex flex-wrap justify-center gap-2">
                {targets.map((t) => (
                  <Button
                    key={t}
                    variant="outline"
                    onClick={() => run(t)}
                    disabled={busyTarget !== null}
                  >
                    {busyTarget === t ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="mr-2 h-4 w-4" />
                    )}
                    {LABELS[t] ?? t.toUpperCase()}
                  </Button>
                ))}
              </div>
            </div>

            {ext === "pdf" && (
              <p className="mx-auto max-w-md text-xs text-muted-foreground">
                PDF é um formato de impressão: a conversão reconstrói o conteúdo.
                Tabelas com bordas visíveis costumam sair certas; layouts sem
                bordas viram texto corrido.
              </p>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
