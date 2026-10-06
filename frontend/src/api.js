const BASE = "/api/v1";

async function request(path, options) {
  const res = await fetch(BASE + path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Erreur ${res.status}`);
  }
  return res.json();
}

export const getMesures = (tableId, limit = 120) =>
  request(`/mesures?table_id=${tableId}&limit=${limit}`);

export const getAlertes = (tableId) =>
  request(`/alertes?table_id=${tableId}&limit=20`);

export const getEtat = (tableId) => request(`/tables/${tableId}/etat`);

export async function getCameras() {
  const res = await fetch("/vision/cameras");
  if (!res.ok) throw new Error(`Module vision injoignable (${res.status})`);
  return res.json();
}

export async function getPresence() {
  const res = await fetch("/vision/presence");
  if (!res.ok) throw new Error(`Module vision injoignable (${res.status})`);
  return res.json();
}

export async function choisirCamera(index) {
  const res = await fetch("/vision/camera", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Erreur ${res.status}`);
  }
  return res.json();
}

export const getDetections = (tableId) =>
  request(`/detections?table_id=${tableId}&limit=20`);

export const entrainer = (tableId) =>
  request(`/tables/${tableId}/entrainement`, { method: "POST" });

export const commander = (tableId, buzzer) =>
  request(`/tables/${tableId}/commande`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ buzzer }),
  });
