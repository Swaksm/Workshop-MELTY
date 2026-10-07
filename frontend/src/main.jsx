import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import Login from "./Login.jsx";
import { SESSION_EXPIREE, deconnecter, verifierSession } from "./auth";
import "./styles.css";

function Racine() {
  // null tant que l'API n'a pas dit si le cookie de session est encore valide
  const [connecte, setConnecte] = useState(null);

  useEffect(() => {
    verifierSession().then(setConnecte);
    const expiree = () => setConnecte(false);
    window.addEventListener(SESSION_EXPIREE, expiree);
    return () => window.removeEventListener(SESSION_EXPIREE, expiree);
  }, []);

  if (connecte === null) return null;
  if (!connecte) {
    return <Login onSuccess={() => setConnecte(true)} />;
  }
  return (
    <App
      onLogout={async () => {
        await deconnecter();
        setConnecte(false);
      }}
    />
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Racine />
  </StrictMode>,
);
