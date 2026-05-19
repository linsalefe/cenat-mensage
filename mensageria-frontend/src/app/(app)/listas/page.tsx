"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import axios from "axios";
import { ListChecks, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { contactListsApi } from "@/lib/api-contact-lists";
import type { ContactList } from "@/types/api";

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

export default function ListasPage() {
  const [lists, setLists] = useState<ContactList[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ContactList | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await contactListsApi.list();
      setLists(data);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar listas"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate() {
    if (!newName.trim()) {
      toast.error("Informe o nome da lista");
      return;
    }
    setCreating(true);
    try {
      await contactListsApi.create({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
      });
      toast.success("Lista criada");
      setCreateOpen(false);
      setNewName("");
      setNewDesc("");
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao criar"));
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await contactListsApi.remove(deleteTarget.id);
      toast.success("Lista excluída");
      setDeleteTarget(null);
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao excluir"));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-2xl font-semibold tracking-tight">Listas</h1>
          <p className="text-sm text-muted-foreground">
            Listas de contatos para campanhas e broadcasts.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> Nova lista
        </Button>
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground">Carregando…</div>
      ) : lists.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-12 text-center">
          <ListChecks className="h-10 w-10 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">
            Nenhuma lista ainda — crie a primeira.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {lists.map((l) => (
            <Card key={l.id} className="group relative p-4 transition hover:border-foreground/30">
              <Link href={`/listas/${l.id}`} className="block space-y-2">
                <div className="flex items-center gap-2">
                  <ListChecks className="h-4 w-4 text-muted-foreground" />
                  <h2 className="font-medium leading-tight">{l.name}</h2>
                </div>
                {l.description && (
                  <p className="line-clamp-2 text-xs text-muted-foreground">{l.description}</p>
                )}
                <div className="text-xs text-muted-foreground">
                  {l.member_count} {l.member_count === 1 ? "contato" : "contatos"}
                </div>
              </Link>
              <Button
                size="icon"
                variant="ghost"
                className="absolute right-2 top-2 h-7 w-7 opacity-0 transition group-hover:opacity-100"
                onClick={(e) => {
                  e.preventDefault();
                  setDeleteTarget(l);
                }}
                aria-label="Excluir lista"
              >
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nova lista</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="lst-name">Nome</Label>
              <Input
                id="lst-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Ex: Alunos psicologia abril"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="lst-desc">Descrição (opcional)</Label>
              <Textarea
                id="lst-desc"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                rows={2}
                placeholder="Notas internas sobre a lista"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={creating}>
              Cancelar
            </Button>
            <Button onClick={handleCreate} disabled={creating}>
              {creating ? "Criando…" : "Criar lista"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir lista {deleteTarget?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Remove a lista e todos os {deleteTarget?.member_count} contatos vinculados.{" "}
              <strong>Irreversível.</strong>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
