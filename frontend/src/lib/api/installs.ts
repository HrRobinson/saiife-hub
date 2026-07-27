import { api } from "@/lib/api";

export type Install = {
  id: string;
  name: string;
  created_at: string;
  last_seen_at: string | null;
};

export type IngressUrl = {
  id: string;
  integration: string;
  url: string;
  created_at: string;
};

export type Delivery = {
  delivery_id: string;
  ingress_id: string;
  integration: string;
  received_at: string;
  status: string;
};

export function listInstalls() {
  return api<Install[]>("/api/v1/installs");
}

export function createInstall(name: string) {
  return api<Install>("/api/v1/installs", { method: "POST", json: { name } });
}

export function deleteInstall(id: string) {
  return api<void>(`/api/v1/installs/${id}`, { method: "DELETE" });
}

export function listIngressUrls() {
  return api<{ ingress_urls: IngressUrl[] }>("/api/v1/installs/ingress-urls");
}

export function listDeliveries(limit = 50) {
  return api<{ deliveries: Delivery[] }>(`/api/v1/installs/deliveries?limit=${limit}`);
}
