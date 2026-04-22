"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { formatDistanceToNow, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import axios from "axios";
import { toast } from "sonner";
import { MoreVertical, Copy, RefreshCw } from "lucide-react";

import { useAuth } from "@/contexts/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usersApi, type AdminUser } from "@/lib/api-users";

function errMsg(err: unknown, fb = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fb;
}

function fmtDistance(s: string | null) {
  if (!s) return "—";
  try {
    return formatDistanceToNow(parseISO(s), { locale: ptBR, addSuffix: true });
  } catch {
    return s;
  }
}

function genPassword(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  let out = "";
  const arr = new Uint8Array(12);
  crypto.getRandomValues(arr);
  for (const v of arr) out += chars[v % chars.length];
  return out;
}

export default function UsuariosPage() {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = !!user?.is_admin;

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);

  // Create
  const [createOpen, setCreateOpen] = useState(false);
  const [cEmail, setCEmail] = useState("");
  const [cName, setCName] = useState("");
  const [cPassword, setCPassword] = useState("");
  const [cAdmin, setCAdmin] = useState(false);
  const [creating, setCreating] = useState(false);

  // Reset
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [resetPwd, setResetPwd] = useState("");
  const [resetting, setResetting] = useState(false);

  // Delete
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await usersApi.list());
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar usuários"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    if (!isAdmin) {
      router.replace("/");
      return;
    }
    load();
  }, [user, isAdmin, load, router]);

  const createUser = async () => {
    if (!cEmail || !cPassword || cPassword.length < 8) {
      toast.error("Email e senha (>=8) obrigatórios");
      return;
    }
    setCreating(true);
    try {
      await usersApi.create({
        email: cEmail,
        password: cPassword,
        name: cName || undefined,
        is_admin: cAdmin,
      });
      toast.success("Usuário criado");
      setCreateOpen(false);
      setCEmail("");
      setCName("");
      setCPassword("");
      setCAdmin(false);
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao criar"));
    } finally {
      setCreating(false);
    }
  };

  const toggleActive = async (u: AdminUser, next: boolean) => {
    try {
      await usersApi.update(u.id, { is_active: next });
      await load();
    } catch (err) {
      toast.error(errMsg(err));
    }
  };

  const toggleAdmin = async (u: AdminUser) => {
    try {
      await usersApi.update(u.id, { is_admin: !u.is_admin });
      toast.success(u.is_admin ? "Admin removido" : "Tornou admin");
      await load();
    } catch (err) {
      toast.error(errMsg(err));
    }
  };

  const resetPassword = async () => {
    if (!resetTarget) return;
    if (resetPwd.length < 8) {
      toast.error("Senha precisa ter no mínimo 8 caracteres");
      return;
    }
    setResetting(true);
    try {
      await usersApi.resetPassword(resetTarget.id, resetPwd);
      toast.success(`Senha resetada para ${resetTarget.email}`);
      setResetTarget(null);
      setResetPwd("");
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setResetting(false);
    }
  };

  const removeUser = async () => {
    if (!deleteTarget) return;
    try {
      await usersApi.remove(deleteTarget.id);
      toast.success(`Usuário ${deleteTarget.email} excluído`);
      setDeleteTarget(null);
      await load();
    } catch (err) {
      toast.error(errMsg(err));
    }
  };

  if (!user) return null;
  if (!isAdmin) {
    return (
      <div className="text-sm text-muted-foreground">
        Acesso restrito a administradores.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-2xl font-semibold tracking-tight">Usuários</h1>
          <p className="text-sm text-muted-foreground">
            Administre quem tem acesso ao WhatsFlow.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>Novo usuário</Button>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nome</TableHead>
            <TableHead>Email</TableHead>
            <TableHead>Admin</TableHead>
            <TableHead>Ativo</TableHead>
            <TableHead>Último login</TableHead>
            <TableHead>Criado</TableHead>
            <TableHead className="text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                Carregando…
              </TableCell>
            </TableRow>
          ) : (
            users.map((u) => {
              const isSelf = u.id === user?.id;
              return (
                <TableRow key={u.id}>
                  <TableCell>{u.name || "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{u.email}</TableCell>
                  <TableCell>
                    {u.is_admin ? <Badge>admin</Badge> : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={u.is_active}
                      onCheckedChange={(v) => toggleActive(u, v)}
                      disabled={isSelf}
                    />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {fmtDistance(u.last_login_at)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {fmtDistance(u.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm" variant="ghost">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => {
                            setResetTarget(u);
                            setResetPwd("");
                          }}
                        >
                          Resetar senha
                        </DropdownMenuItem>
                        {!isSelf && (
                          <DropdownMenuItem onClick={() => toggleAdmin(u)}>
                            {u.is_admin ? "Remover admin" : "Tornar admin"}
                          </DropdownMenuItem>
                        )}
                        {!isSelf && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => setDeleteTarget(u)}
                              className="text-destructive focus:text-destructive"
                            >
                              Excluir
                            </DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>

      {/* Create */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>Novo usuário</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Email</Label>
              <Input
                type="email"
                value={cEmail}
                onChange={(e) => setCEmail(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="space-y-1">
              <Label>Nome</Label>
              <Input value={cName} onChange={(e) => setCName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Senha (mín. 8)</Label>
              <div className="flex gap-2">
                <Input
                  value={cPassword}
                  onChange={(e) => setCPassword(e.target.value)}
                  autoComplete="new-password"
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setCPassword(genPassword())}
                  title="Gerar senha"
                >
                  <RefreshCw className="h-3 w-3" />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={!cPassword}
                  onClick={() => {
                    navigator.clipboard.writeText(cPassword);
                    toast.success("Copiado");
                  }}
                  title="Copiar"
                >
                  <Copy className="h-3 w-3" />
                </Button>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={cAdmin} onCheckedChange={setCAdmin} />
              <Label className="cursor-pointer">Conceder admin</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={createUser} disabled={creating}>
              {creating ? "Criando…" : "Criar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset Password */}
      <Dialog
        open={!!resetTarget}
        onOpenChange={(open) => !open && setResetTarget(null)}
      >
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Resetar senha</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="text-sm text-muted-foreground">
              Usuário: <span className="font-mono">{resetTarget?.email}</span>
            </div>
            <div className="space-y-1">
              <Label>Nova senha</Label>
              <div className="flex gap-2">
                <Input
                  value={resetPwd}
                  onChange={(e) => setResetPwd(e.target.value)}
                  autoComplete="new-password"
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setResetPwd(genPassword())}
                >
                  <RefreshCw className="h-3 w-3" />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={!resetPwd}
                  onClick={() => {
                    navigator.clipboard.writeText(resetPwd);
                    toast.success("Copiado");
                  }}
                >
                  <Copy className="h-3 w-3" />
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetTarget(null)}>
              Cancelar
            </Button>
            <Button onClick={resetPassword} disabled={resetting}>
              {resetting ? "Salvando…" : "Resetar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir usuário?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta ação não pode ser desfeita. O usuário{" "}
              <strong>{deleteTarget?.email}</strong> será removido permanentemente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={removeUser}
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
