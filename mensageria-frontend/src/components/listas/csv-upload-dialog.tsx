"use client";

import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { Download, FileUp, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { contactListsApi } from "@/lib/api-contact-lists";
import type { CsvImportResult } from "@/types/api";

interface Props {
  listId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: () => void;
}

function errMsg(err: unknown, fallback = "Erro inesperado") {
  if (axios.isAxiosError(err) && err.response?.data?.detail) {
    const detail = err.response.data.detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return fallback;
}

export function CsvUploadDialog({ listId, open, onOpenChange, onImported }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<CsvImportResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setFile(null);
      setResult(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }, [open]);

  function downloadTemplate() {
    const csv = "nome,telefone,curso\nJoao Exemplo,5511999998888,Psicologia\n";
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "modelo-contatos.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleUpload() {
    if (!file) {
      toast.error("Selecione um arquivo CSV");
      return;
    }
    setUploading(true);
    setResult(null);
    try {
      const r = await contactListsApi.importCsv(listId, file);
      setResult(r);
      if (r.imported > 0) {
        toast.success(`${r.imported} ${r.imported === 1 ? "contato importado" : "contatos importados"}`);
        onImported();
      } else if (r.errors.length > 0) {
        toast.error("Nenhum contato importado — confira erros");
      } else {
        toast.message("Nenhum novo (todos duplicados)");
        onImported();
      }
    } catch (err) {
      toast.error(errMsg(err, "Falha ao importar"));
    } finally {
      setUploading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileUp className="h-4 w-4" /> Importar CSV
          </DialogTitle>
          <DialogDescription>
            Cabeçalho esperado: <code>nome,telefone,curso</code> (curso opcional). Outras colunas
            viram variáveis customizadas.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Button variant="outline" size="sm" onClick={downloadTemplate}>
              <Download className="mr-2 h-4 w-4" /> Baixar modelo
            </Button>
          </div>

          <div className="rounded-md border border-dashed p-4 text-center">
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-secondary/80"
            />
            {file && (
              <p className="mt-2 text-xs text-muted-foreground">
                {file.name} ({(file.size / 1024).toFixed(1)} KB)
              </p>
            )}
          </div>

          {result && (
            <div className="space-y-2 rounded-md border p-3 text-xs">
              <div className="grid grid-cols-3 gap-2">
                <Metric label="Importados" value={result.imported} variant="ok" />
                <Metric label="Duplicados" value={result.skipped_duplicates} variant="muted" />
                <Metric label="Erros" value={result.errors.length} variant="warn" />
              </div>
              {result.errors.length > 0 && (
                <ScrollArea className="h-32 rounded-md bg-muted/30 p-2">
                  <ul className="space-y-1 font-mono text-[11px]">
                    {result.errors.slice(0, 10).map((e, i) => (
                      <li key={i}>
                        linha {e.line}: {e.reason}
                      </li>
                    ))}
                    {result.errors.length > 10 && (
                      <li className="text-muted-foreground">
                        … e mais {result.errors.length - 10}
                      </li>
                    )}
                  </ul>
                </ScrollArea>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={uploading}>
            Fechar
          </Button>
          <Button onClick={handleUpload} disabled={uploading || !file}>
            <Upload className="mr-2 h-4 w-4" />
            {uploading ? "Enviando…" : "Importar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Metric({
  label,
  value,
  variant,
}: {
  label: string;
  value: number;
  variant: "ok" | "warn" | "muted";
}) {
  const colorMap = {
    ok: "text-emerald-600 dark:text-emerald-400",
    warn: "text-amber-600 dark:text-amber-400",
    muted: "text-muted-foreground",
  };
  return (
    <div className="rounded-md bg-muted/30 p-2 text-center">
      <div className={`text-lg font-semibold ${colorMap[variant]}`}>{value}</div>
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
    </div>
  );
}
