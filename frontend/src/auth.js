const UTILISATEUR = "admin";
const MOT_DE_PASSE = "admin";
const CLE_SESSION = "sentinelx-session";

export function connecter(utilisateur, motDePasse) {
  if (utilisateur !== UTILISATEUR || motDePasse !== MOT_DE_PASSE) return false;
  sessionStorage.setItem(CLE_SESSION, utilisateur);
  return true;
}

export function estConnecte() {
  return sessionStorage.getItem(CLE_SESSION) === UTILISATEUR;
}

export function deconnecter() {
  sessionStorage.removeItem(CLE_SESSION);
}
