// Connexion auprès de l'API. Le jeton est dans un cookie HttpOnly posé par le
// backend : le JavaScript ne le voit jamais, le navigateur l'envoie tout seul.
export const SESSION_EXPIREE = "sentinelx:session-expiree";

export async function connecter(utilisateur, motDePasse) {
  const res = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ utilisateur, mot_de_passe: motDePasse }),
  });
  if (res.ok) return null;
  const body = await res.json().catch(() => ({}));
  return body.detail ?? `Erreur ${res.status}`;
}

export async function verifierSession() {
  const res = await fetch("/api/v1/auth/verifier").catch(() => null);
  return Boolean(res?.ok);
}

export async function deconnecter() {
  await fetch("/api/v1/auth/logout", { method: "POST" }).catch(() => null);
}
