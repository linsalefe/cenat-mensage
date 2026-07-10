import { api } from "@/lib/api";

export interface DocumentFormats {
  max_bytes: number;
  /** extensão de entrada -> extensões de saída possíveis */
  conversions: Record<string, string[]>;
}

export const documentsApi = {
  formats: () =>
    api.get<DocumentFormats>("/documents/formats").then((r) => r.data),

  convert: (file: File, target: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("target", target);
    return api
      .post("/documents/convert", fd, {
        responseType: "blob",
        headers: { "Content-Type": "multipart/form-data" },
        // Conversão roda num container; docx->pdf leva ~2s, arquivos grandes mais.
        timeout: 180_000,
      })
      .then((r) => r.data as Blob);
  },
};

/**
 * Com responseType "blob" o axios entrega o corpo de erro também como Blob,
 * então o `detail` do FastAPI só aparece depois de ler o texto.
 */
export async function documentErrorMessage(
  err: unknown,
  fallback = "Não foi possível converter o arquivo.",
): Promise<string> {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text());
      if (parsed?.detail) return String(parsed.detail);
    } catch {
      /* corpo não era JSON */
    }
  } else if (data && typeof data === "object" && "detail" in data) {
    return String((data as { detail: unknown }).detail);
  }
  return fallback;
}
