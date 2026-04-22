import { api } from "@/lib/api";
import type { MediaAsset } from "@/types/api";

export const mediaApi = {
  list: () => api.get<MediaAsset[]>("/media").then((r) => r.data),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api
      .post<MediaAsset>("/media/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  remove: (id: number) => api.delete(`/media/${id}`).then(() => undefined),
  // URL relativa — browser usa origem atual; dev aponta pro backend direto
  getUrl: (id: number) => `/api/media/${id}`,
};
