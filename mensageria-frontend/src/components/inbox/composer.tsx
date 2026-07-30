"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  FileText,
  Image as ImageIcon,
  LayoutTemplate,
  Loader2,
  Mic,
  Paperclip,
  Send,
  Square,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { inboxApi } from "@/lib/api-inbox";
import { cn } from "@/lib/utils";
import type { Channel, Contact } from "@/types/api";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const FEEDBACK_MS = 2000;

type Feedback = "ok" | "error" | null;

interface Props {
  contact: Contact;
  channel: Channel | null;
  /** Envio de texto, roteado por provider pela página. */
  onSendText: (text: string) => Promise<void>;
  onAfterSend: () => void;
  onOpenTemplate: () => void;
}

function mmss(total: number) {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function Composer({
  contact,
  channel,
  onSendText,
  onAfterSend,
  onOpenTemplate,
}: Props) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [uploading, setUploading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);

  const imageInput = useRef<HTMLInputElement>(null);
  const docInput = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const discardRef = useRef(false);

  // Só o canal oficial tem rota de mídia: /send-media rejeita evolution e
  // instagram com 404, e o provider do IG nem aceita arquivo local.
  const supportsMedia = channel?.provider === "official";

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
      recorderRef.current?.stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const flash = (kind: Feedback) => {
    setFeedback(kind);
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    feedbackTimer.current = setTimeout(() => setFeedback(null), FEEDBACK_MS);
  };

  const sendText = async () => {
    if (!input.trim() || sending) return;
    setSending(true);
    try {
      await onSendText(input);
      setInput("");
      flash("ok");
    } catch {
      flash("error");
    } finally {
      setSending(false);
    }
  };

  const sendFile = async (
    file: File,
    mediaType: "image" | "document" | "audio",
  ) => {
    if (!channel || !supportsMedia) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      toast.error("Arquivo maior que 10 MB.");
      return;
    }
    setUploading(true);
    try {
      const asset = await inboxApi.uploadMedia(file);
      await inboxApi.sendMedia(channel.id, {
        to: contact.wa_id,
        media_type: mediaType,
        media_id: asset.id,
        caption: mediaType === "audio" ? undefined : input.trim() || undefined,
      });
      if (mediaType !== "audio") setInput("");
      flash("ok");
      onAfterSend();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Falha ao enviar o arquivo");
      flash("error");
      // O backend registra a falha no chat; recarrega para exibi-la.
      onAfterSend();
    } finally {
      setUploading(false);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Chrome/Firefox gravam webm/opus (o backend remuxa para ogg);
      // o Safari só oferece mp4, que o WhatsApp aceita direto.
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "";
      const rec = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      discardRef.current = false;
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.start();
      recorderRef.current = rec;
      setIsRecording(true);
      setRecordingTime(0);
      timerRef.current = setInterval(() => setRecordingTime((t) => t + 1), 1000);
    } catch {
      toast.error("Permissão de microfone negada.");
    }
  };

  const stopTracks = (rec: MediaRecorder) =>
    rec.stream.getTracks().forEach((t) => t.stop());

  const finishRecording = async (discard: boolean) => {
    const rec = recorderRef.current;
    if (!rec) return;
    discardRef.current = discard;

    await new Promise<void>((resolve) => {
      rec.onstop = () => resolve();
      rec.stop();
    });
    stopTracks(rec);
    if (timerRef.current) clearInterval(timerRef.current);
    setIsRecording(false);
    setRecordingTime(0);
    recorderRef.current = null;

    if (discard) {
      chunksRef.current = [];
      return;
    }

    const type = rec.mimeType || "audio/webm";
    const blob = new Blob(chunksRef.current, { type });
    chunksRef.current = [];
    if (blob.size === 0) {
      toast.error("Gravação vazia.");
      return;
    }
    // O tipo do MediaRecorder vem com codecs=…; o backend só olha o mime base.
    const base = type.split(";")[0];
    const ext = base === "audio/mp4" ? "m4a" : "webm";
    const file = new File([blob], `audio_${Date.now()}.${ext}`, { type: base });
    await sendFile(file, "audio");
  };

  const busy = sending || uploading;

  if (isRecording) {
    return (
      <div className="flex items-center gap-3 border-t border-border bg-secondary p-3">
        <span className="flex h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
        <span className="flex-1 text-sm tabular-nums">
          Gravando… {mmss(recordingTime)}
        </span>
        <Button
          size="icon"
          variant="ghost"
          onClick={() => finishRecording(true)}
          aria-label="Descartar gravação"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
        <Button
          size="icon"
          onClick={() => finishRecording(false)}
          aria-label="Enviar áudio"
        >
          <Square className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="border-t border-border bg-secondary p-3">
      <div className="flex items-end gap-2">
        {supportsMedia && (
          <>
            <input
              ref={imageInput}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (f) sendFile(f, "image");
              }}
            />
            <input
              ref={docInput}
              type="file"
              accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (f) sendFile(f, "document");
              }}
            />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  size="icon"
                  variant="ghost"
                  className="shrink-0"
                  disabled={busy}
                  aria-label="Anexar"
                >
                  <Paperclip className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="wa-theme">
                <DropdownMenuItem onClick={() => imageInput.current?.click()}>
                  <ImageIcon className="mr-2 h-4 w-4" />
                  Imagem
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => docInput.current?.click()}>
                  <FileText className="mr-2 h-4 w-4" />
                  Documento
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Botão próprio: enviar template não é "anexar um arquivo", e fora
                da janela de 24h é o único caminho que entrega. */}
            <Button
              size="icon"
              variant="ghost"
              className="shrink-0"
              disabled={busy}
              onClick={onOpenTemplate}
              title="Enviar template"
              aria-label="Enviar template"
            >
              <LayoutTemplate className="h-4 w-4" />
            </Button>
          </>
        )}

        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendText();
            }
          }}
          placeholder="Digite uma mensagem…"
          disabled={busy}
          rows={1}
          className="max-h-32 min-h-[40px] resize-none"
        />

        {feedback && (
          <div
            className={cn(
              "flex h-10 w-8 items-center justify-center",
              feedback === "ok" ? "text-emerald-500" : "text-destructive",
            )}
          >
            {feedback === "ok" ? (
              <Check className="h-4 w-4" />
            ) : (
              <AlertCircle className="h-4 w-4" />
            )}
          </div>
        )}

        {supportsMedia && !input.trim() ? (
          <Button
            size="icon"
            className="shrink-0"
            disabled={busy}
            onClick={startRecording}
            aria-label="Gravar áudio"
          >
            {uploading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
          </Button>
        ) : (
          <Button
            size="icon"
            className="shrink-0"
            onClick={sendText}
            disabled={busy || !input.trim()}
            aria-label="Enviar"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        )}
      </div>
    </div>
  );
}
