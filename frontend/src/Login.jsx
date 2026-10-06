import { useState } from "react";
import { connecter } from "./auth";

export default function Login({ onSuccess }) {
  const [utilisateur, setUtilisateur] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState(null);

  function onSubmit(e) {
    e.preventDefault();
    if (connecter(utilisateur, motDePasse)) {
      onSuccess();
    } else {
      setErreur("Identifiant ou mot de passe incorrect.");
      setMotDePasse("");
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="login-brand">
          <span className="brand-mark" aria-hidden="true" />
          <div>
            <div className="kicker">SENTINEL-X</div>
            <h1>Connexion</h1>
          </div>
        </div>
        <p className="login-lead">Accès au tableau de supervision de la table.</p>

        <label className="field">
          <span>Identifiant</span>
          <input
            type="text"
            autoComplete="username"
            value={utilisateur}
            onChange={(e) => setUtilisateur(e.target.value)}
            required
            autoFocus
          />
        </label>

        <label className="field">
          <span>Mot de passe</span>
          <input
            type="password"
            autoComplete="current-password"
            value={motDePasse}
            onChange={(e) => setMotDePasse(e.target.value)}
            required
          />
        </label>

        {erreur && <div className="banner error" role="alert">{erreur}</div>}

        <button type="submit" className="btn primary block">
          Se connecter
        </button>

        <p className="login-foot">Table 1 · Accès réservé à l'équipe</p>
      </form>
    </div>
  );
}
