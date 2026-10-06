import { useCallback, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  choisirCamera,
  commander,
  entrainer,
  getAlertes,
  getCameras,
  getDetections,
  getEtat,
  getMesures,
  getPresence,
} from "./api";

const TABLE_ID = "table1";
const TABLE_LABEL = "Sentinel G9";
const POLL_MS = 3000;
const FENETRE_GRAPHIQUE_MS = 60 * 60 * 1000;
const PERSONNE_RECENTE_MS = 15000;

const formatHeure = (iso) => new Date(iso).toLocaleTimeString("fr-FR");
const formatTick = (horodatage) => new Date(horodatage).toLocaleTimeString("fr-FR");
const couleurAlerte = (a) => (a.kind === "hausse_temperature" ? "#f5b041" : "#ff6b6b");
const formatDate = (iso) => new Date(iso).toLocaleString("fr-FR");

export default function App({ onLogout }) {
  const [mesures, setMesures] = useState([]);
  const [alertes, setAlertes] = useState([]);
  const [detections, setDetections] = useState([]);
  const [etat, setEtat] = useState({ alerte_active: false, modele_entraine: false });
  const [erreur, setErreur] = useState(null);
  const [message, setMessage] = useState(null);
  const [videoOk, setVideoOk] = useState(true);
  const [cameras, setCameras] = useState({ disponibles: [], active: null });
  const [erreurCamera, setErreurCamera] = useState(null);
  const [presence, setPresence] = useState({ progression: 0, confirmee: false });

  useEffect(() => {
    getCameras()
      .then(setCameras)
      .catch(() => setCameras({ disponibles: [], active: null }));
  }, []);

  useEffect(() => {
    const id = setInterval(() => {
      getPresence()
        .then(setPresence)
        .catch(() => setPresence({ progression: 0, confirmee: false }));
    }, 500);
    return () => clearInterval(id);
  }, []);

  async function onChoisirCamera(index) {
    setErreurCamera(null);
    try {
      await choisirCamera(index);
      setCameras(await getCameras());
    } catch (err) {
      setErreurCamera(err.message);
    }
  }

  const rafraichir = useCallback(async () => {
    try {
      const [m, a, e, d] = await Promise.all([
        getMesures(TABLE_ID),
        getAlertes(TABLE_ID),
        getEtat(TABLE_ID),
        getDetections(TABLE_ID),
      ]);
      setMesures(m);
      setAlertes(a);
      setEtat(e);
      setDetections(d);
      setErreur(null);
    } catch (err) {
      setErreur(err.message);
    }
  }, []);

  useEffect(() => {
    rafraichir();
    const id = setInterval(rafraichir, POLL_MS);
    return () => clearInterval(id);
  }, [rafraichir]);

  const serie = [...mesures]
    .reverse()
    .map((m) => ({
      t: new Date(m.received_at).getTime(),
      temp: m.temp,
      hum: m.hum,
      gaz: m.gas,
    }))
    .filter((p) => Date.now() - p.t <= FENETRE_GRAPHIQUE_MS);
  const derniere = mesures[0];
  const debutFenetre = serie.length ? serie[0].t : 0;
  const finFenetre = serie.length ? serie[serie.length - 1].t : 0;
  const marqueurs = alertes
    .map((a) => ({ ...a, t: new Date(a.created_at).getTime() }))
    .filter((a) => a.t >= debutFenetre && a.t <= finFenetre);

  async function onEntrainer() {
    setMessage(null);
    try {
      const r = await entrainer(TABLE_ID);
      setMessage(`Modèle entraîné sur ${r.mesures_utilisees} mesures.`);
      rafraichir();
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function onBuzzer(state) {
    setMessage(null);
    try {
      await commander(TABLE_ID, state);
      setMessage(state === "on" ? "Buzzer activé." : "Buzzer coupé.");
    } catch (err) {
      setMessage(err.message);
    }
  }

  const statut = etat.alerte_active
    ? { libelle: "Alerte active", classe: "alert" }
    : { libelle: "Système nominal", classe: "ok" };

  const personneRecente = detections.find(
    (d) => Date.now() - new Date(d.created_at).getTime() < PERSONNE_RECENTE_MS,
  );

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <div className="kicker">SENTINEL-X · {TABLE_LABEL}</div>
          <h1>Supervision</h1>
        </div>
        <div className="status-group">
          <span className={`pill ${statut.classe}`}>
            <span className="dot" />
            {statut.libelle}
          </span>
          {personneRecente && (
            <span className="pill alert">
              <span className="dot" />
              Personne détectée
            </span>
          )}
          <span className={`pill ${etat.modele_entraine ? "ok" : "warn"}`}>
            {etat.modele_entraine ? "Modèle entraîné" : "Modèle non entraîné"}
          </span>
          <button type="button" className="btn ghost" onClick={onLogout}>
            Se déconnecter
          </button>
        </div>
      </header>

      {erreur && <div className="banner error">Connexion à l'API impossible : {erreur}</div>}

      <section className="tiles">
        <Tuile label="Température" valeur={derniere?.temp} unite="°C" />
        <Tuile label="Humidité" valeur={derniere?.hum} unite="%HR" />
        <Tuile label="Gaz (valeur brute ADC)" valeur={derniere?.gas} unite="" />
      </section>

      <section className="charts">
        <div className="panel">
          <h2>Environnement</h2>
          <div className="chart">
            {serie.length === 0 ? (
              <Vide texte="Aucune mesure reçue." />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={serie}>
                  <CartesianGrid stroke="#1b3147" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={formatTick}
                    stroke="#5c7891"
                    fontSize={11}
                  />
                  <YAxis yAxisId="t" stroke="#5fd9f0" fontSize={11} unit="°C" />
                  <YAxis yAxisId="h" orientation="right" stroke="#74e0a8" fontSize={11} unit="%" />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={formatTick} />
                  <Line yAxisId="t" type="monotone" dataKey="temp" stroke="#5fd9f0" dot={false} strokeWidth={2} />
                  <Line yAxisId="h" type="monotone" dataKey="hum" stroke="#74e0a8" dot={false} strokeWidth={2} />
                  {marqueurs.map((a) => (
                    <ReferenceLine
                      key={`l${a.id}`}
                      x={a.t}
                      yAxisId="t"
                      stroke={couleurAlerte(a)}
                      strokeDasharray="4 4"
                    />
                  ))}
                  {marqueurs.map((a) => (
                    <ReferenceDot
                      key={`d${a.id}`}
                      x={a.t}
                      y={a.temp}
                      yAxisId="t"
                      r={6}
                      fill={couleurAlerte(a)}
                      stroke="#0e1d2e"
                      strokeWidth={2}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="chart-legend">
            <span><i style={{ background: "#ff6b6b" }} /> Anomalie capteurs</span>
            <span><i style={{ background: "#f5b041" }} /> Hausse de température</span>
          </div>
        </div>

        <div className="panel">
          <h2>Gaz</h2>
          <div className="chart">
            {serie.length === 0 ? (
              <Vide texte="Aucune mesure reçue." />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={serie}>
                  <defs>
                    <linearGradient id="gazFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ff6f6f" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#ff6f6f" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1b3147" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={formatTick}
                    stroke="#5c7891"
                    fontSize={11}
                  />
                  <YAxis stroke="#ff6f6f" fontSize={11} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={formatTick} />
                  <Area type="monotone" dataKey="gaz" stroke="#ff6f6f" fill="url(#gazFill)" strokeWidth={2} />
                  {marqueurs.map((a) => (
                    <ReferenceLine key={`l${a.id}`} x={a.t} stroke={couleurAlerte(a)} strokeDasharray="4 4" />
                  ))}
                  {marqueurs.map((a) => (
                    <ReferenceDot
                      key={`d${a.id}`}
                      x={a.t}
                      y={a.gas}
                      r={6}
                      fill={couleurAlerte(a)}
                      stroke="#0e1d2e"
                      strokeWidth={2}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="chart-legend">
            <span><i style={{ background: "#ff6b6b" }} /> Anomalie capteurs</span>
            <span><i style={{ background: "#f5b041" }} /> Hausse de température</span>
          </div>
        </div>
      </section>

      <section className="panel video-panel">
        <div className="video-head">
          <h2>Surveillance vidéo</h2>
          {cameras.disponibles.length > 1 ? (
            <label className="camera-select">
              Caméra
              <select
                value={cameras.active ?? ""}
                onChange={(e) => onChoisirCamera(Number(e.target.value))}
              >
                {cameras.disponibles.map((index) => (
                  <option key={index} value={index}>
                    Caméra n°{index}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            cameras.disponibles.length === 1 && (
              <span className="hint">Une seule caméra détectée (n°{cameras.disponibles[0]})</span>
            )
          )}
        </div>
        {erreurCamera && <div className="banner error">{erreurCamera}</div>}
        <div className="video">
          {videoOk ? (
            <img
              src="/vision/stream"
              alt="Flux de la webcam avec les détections en cours"
              onError={() => setVideoOk(false)}
            />
          ) : (
            <Vide texte="Flux indisponible : lance le module vision sur le PC (voir le README)." />
          )}
        </div>
        <p className="hint">
          Rouge : personne (déclenche une alerte et le buzzer). Orange : animal (affiché, sans alerte). Les autres objets ne sont pas affichés.
        </p>
        <aside className="video-side">
          <div className="presence">
            <div className="presence-head">
              <span>Présence devant la caméra</span>
              <span className={presence.confirmee ? "presence-ok" : ""}>
                {presence.confirmee
                  ? "Confirmée : alerte envoyée"
                  : `${(presence.progression * 3).toFixed(1)} / 3 s`}
              </span>
            </div>
            <div className="presence-bar" role="progressbar" aria-valuemin={0} aria-valuemax={3}
                 aria-valuenow={Number((presence.progression * 3).toFixed(1))}>
              <div
                className={`presence-fill ${presence.confirmee ? "done" : ""}`}
                style={{ width: `${Math.round(presence.progression * 100)}%` }}
              />
            </div>
          </div>

          {detections.length === 0 ? (
            <Vide texte="Aucune personne détectée." />
          ) : (
            <ul className="alerts">
              {detections.slice(0, 10).map((d) => (
                <li key={d.id} className="alert-item">
                  <span className="stripe" />
                  <div>
                    <div className="alert-title">Personne détectée</div>
                    <div className="alert-meta">
                      {formatDate(d.created_at)} · confiance {Math.round(d.confidence * 100)} %
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </section>

      <section className="bottom">
        <div className="panel">
          <h2>Commandes</h2>
          <div className="actions">
            <button type="button" className="btn cmd" onClick={() => onBuzzer("on")}>
              Activer le buzzer
            </button>
            <button type="button" className="btn" onClick={() => onBuzzer("off")}>
              Couper le buzzer
            </button>
            <button type="button" className="btn" onClick={onEntrainer}>
              Entraîner le modèle
            </button>
          </div>
          <p className="hint">
            Le modèle apprend la baseline à partir des mesures stockées (100 minimum). Aucun seuil n'est fixé à la main.
          </p>
          {message && <p className="message">{message}</p>}
        </div>

        <div className="panel">
          <h2>Alertes</h2>
          {alertes.length === 0 ? (
            <Vide texte="Aucune alerte pour l'instant." />
          ) : (
            <ul className="alerts">
              {alertes.map((a) => (
                <li key={a.id} className={`alert-item ${a.kind === "hausse_temperature" ? "hausse" : ""}`}>
                  <span className="stripe" />
                  <div>
                    <div className="alert-title">
                      {a.kind === "hausse_temperature" ? "Hausse de température" : "Anomalie détectée"}
                    </div>
                    <div className="alert-meta">
                      {formatDate(a.created_at)} · {a.temp.toFixed(1)} °C · {a.hum.toFixed(1)} % · gaz {a.gas}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function Tuile({ label, valeur, unite }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">
        {valeur === undefined ? "—" : valeur}
        {valeur !== undefined && unite && <span className="unit"> {unite}</span>}
      </div>
    </div>
  );
}

function Vide({ texte }) {
  return <div className="empty">{texte}</div>;
}

const tooltipStyle = {
  background: "#0b1a2a",
  border: "1px solid #22394f",
  color: "#e7eef5",
  fontSize: 12,
};
