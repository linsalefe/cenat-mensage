"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { ArrowLeft, FileUp, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CsvUploadDialog } from "@/components/listas/csv-upload-dialog";
import { contactListsApi } from "@/lib/api-contact-lists";
import type { ContactList, ContactListMember } from "@/types/api";

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

const PAGE_SIZE = 50;

export default function ListDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params?.id);

  const [list, setList] = useState<ContactList | null>(null);
  const [members, setMembers] = useState<ContactListMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [uploadOpen, setUploadOpen] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(id)) return;
    setLoading(true);
    try {
      const [lst, m] = await Promise.all([
        contactListsApi.get(id),
        contactListsApi.members(id, { limit: PAGE_SIZE, offset: page * PAGE_SIZE, search: search || undefined }),
      ]);
      setList(lst);
      setMembers(m.members);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar"));
    } finally {
      setLoading(false);
    }
  }, [id, page, search]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRemove(memberId: number) {
    if (!list) return;
    try {
      await contactListsApi.removeMember(list.id, memberId);
      toast.success("Removido");
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao remover"));
    }
  }

  if (!Number.isFinite(id)) {
    return <div className="text-sm text-muted-foreground">ID inválido.</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/listas")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {list?.name || "Carregando…"}
            </h1>
            {list?.description && (
              <p className="text-sm text-muted-foreground">{list.description}</p>
            )}
          </div>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <FileUp className="mr-2 h-4 w-4" /> Importar CSV
        </Button>
      </div>

      <Card className="flex items-center gap-4 p-4">
        <div className="flex-1">
          <div className="text-xs text-muted-foreground">Total de contatos</div>
          <div className="text-2xl font-semibold">{list?.member_count ?? 0}</div>
        </div>
        <div className="relative w-72">
          <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder="Buscar por nome ou telefone…"
            className="pl-8"
          />
        </div>
      </Card>

      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Telefone</TableHead>
              <TableHead>Variáveis</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-16 text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                  Carregando…
                </TableCell>
              </TableRow>
            ) : members.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                  Sem contatos. Importe um CSV para começar.
                </TableCell>
              </TableRow>
            ) : (
              members.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="font-medium">{m.name || "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{m.wa_id}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {Object.keys(m.custom_vars).length > 0
                      ? Object.entries(m.custom_vars)
                          .map(([k, v]) => `${k}=${v}`)
                          .join(", ")
                      : "—"}
                  </TableCell>
                  <TableCell>
                    {m.opted_out ? (
                      <Badge variant="outline" className="bg-red-500/10 text-red-700 dark:text-red-400">
                        opt-out
                      </Badge>
                    ) : (
                      <Badge variant="outline">ativo</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleRemove(m.id)}
                      aria-label="Remover"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Página {page + 1} • mostrando até {PAGE_SIZE} por vez
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => Math.max(0, p - 1))}>
            Anterior
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={members.length < PAGE_SIZE}
            onClick={() => setPage(p => p + 1)}
          >
            Próxima
          </Button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        <Link href="/listas" className="underline">
          ← Voltar para listas
        </Link>
      </p>

      <CsvUploadDialog
        listId={id}
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onImported={load}
      />
    </div>
  );
}
