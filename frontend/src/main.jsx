import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import Login from "./Login.jsx";
import { deconnecter, estConnecte } from "./auth";
import "./styles.css";

function Racine() {
  const [connecte, setConnecte] = useState(estConnecte);

  if (!connecte) {
    return <Login onSuccess={() => setConnecte(true)} />;
  }
  return (
    <App
      onLogout={() => {
        deconnecter();
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
