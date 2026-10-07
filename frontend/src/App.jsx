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
  commanderLed,
  entrainer,
  getAlertes,
  getCameras,
  getDetections,
  getEtat,
  getMesures,
  getPresence,
  getSupervision,
} from "./api";

const TABLE_ID = "table1";
const TABLE_LABEL = "Sentinel G9";
const POLL_MS = 3000;
const FENETRE_GRAPHIQUE_MS = 60 * 60 * 1000;
const PERSONNE_RECENTE_MS = 15000;
const SUPERVISION_MS = 10000;

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
  const [supervision, setSupervision] = useState(null);

  useEffect(() => {
    const charger = () =>
      getSupervision()
        .then(setSupervision)
        .catch(() => setSupervision(null));
    charger();
    const id = setInterval(charger, SUPERVISION_MS);
    return () => clearInterval(id);
  }, []);

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

  async function onLed(state) {
    setMessage(null);
    try {
      await commanderLed(TABLE_ID, state);
      setMessage(state === "on" ? "LED activée." : "LED coupée.");
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

      {(etat.alerte_active || personneRecente) && (
        <div className="banner alert-banner">
          {etat.alerte_active && alertes[0] && (
            <div className="alert-banner-line">
              <span className="alert-banner-icon">⚠</span>
              {alertes[0].kind === "hausse_temperature" ? "Hausse de température" : "Anomalie capteurs"} à{" "}
              {formatHeure(alertes[0].created_at)} — {alertes[0].temp.toFixed(1)} °C · {alertes[0].hum.toFixed(1)} % ·
              gaz {alertes[0].gas}
            </div>
          )}
          {personneRecente && (
            <div className="alert-banner-line">
              <span className="alert-banner-icon">⚠</span>
              Personne détectée à {formatHeure(personneRecente.created_at)} (confiance{" "}
              {Math.round(personneRecente.confidence * 100)} %)
            </div>
          )}
        </div>
      )}

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
            <button type="button" className="btn cmd" onClick={() => onLed("on")}>
              Activer la LED
            </button>
            <button type="button" className="btn" onClick={() => onLed("off")}>
              Couper la LED
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
                    <Explication details={a.details} alerte={a} mesures={mesures} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <Supervision data={supervision} />
      </section>
    </div>
  );
}

function Jauge({ label, pourcent, detail }) {
  const niveau = pourcent >= 90 ? "alert" : pourcent >= 70 ? "warn" : "ok";
  return (
    <div className="jauge">
      <div className="jauge-tete">
        <span>{label}</span>
        <span className="jauge-valeur">{detail ?? `${Math.round(pourcent)} %`}</span>
      </div>
      <div className="jauge-barre">
        <div className={`jauge-remplissage ${niveau}`} style={{ width: `${Math.min(pourcent, 100)}%` }} />
      </div>
    </div>
  );
}

function Supervision({ data }) {
  if (!data) {
    return (
      <div className="panel">
        <h2>Supervision machine</h2>
        <Vide texte="Supervision indisponible." />
      </div>
    );
  }
  const { hote, base, media, mqtt, retention } = data;
  const lignes = [
    ["Mesures en base", `${base.mesures.toLocaleString("fr-FR")}${base.taille_mesures_mo != null ? ` · ${base.taille_mesures_mo} Mo` : ""}`],
    ["Taille de la base", base.taille_base_mo != null ? `${base.taille_base_mo} Mo` : "—"],
    ["Clips vidéo", `${media.clips} · ${media.taille_mo} / ${media.max_mo} Mo`],
    ["Clients MQTT", mqtt.clients_connectes ?? "—"],
    ["Messages MQTT reçus / min", mqtt.messages_recus_par_min ? Math.round(Number(mqtt.messages_recus_par_min)) : "—"],
    ["Rétention", `mesures ${retention.mesures_jours} j · clips ${retention.clips_jours} j`],
  ];
  return (
    <div className="panel">
      <h2>Supervision machine</h2>
      <Jauge label={`CPU (${hote.cpu_coeurs} cœurs)`} pourcent={hote.cpu_pourcent} />
      <Jauge
        label="RAM"
        pourcent={hote.ram_pourcent}
        detail={`${hote.ram_utilisee_mo} / ${hote.ram_totale_mo} Mo`}
      />
      <Jauge label="Disque" pourcent={hote.disque_pourcent} />
      <dl className="supervision-liste">
        {lignes.map(([cle, valeur]) => (
          <div key={cle}>
            <dt>{cle}</dt>
            <dd>{valeur}</dd>
          </div>
        ))}
      </dl>
      <p className="hint">
        Hôte Docker, rafraîchi toutes les 10 s. Détail par conteneur : <a href="http://localhost:8080" target="_blank" rel="noreferrer">cAdvisor</a>.
      </p>
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

const FENETRE_AVANT_MS = 10 * 60 * 1000;
const FENETRE_APRES_MS = 2 * 60 * 1000;

function phraseCausale(details) {
  if (!details?.caracteristiques?.length) return null;
  const pires = [...details.caracteristiques]
    .filter((c) => c.ecart !== undefined)
    .sort((a, b) => Math.abs(b.ecart) - Math.abs(a.ecart));
  if (pires.length === 0) return null;
  const pire = pires[0];
  const sens = pire.ecart > 0 ? "au-dessus" : "en dessous";
  return (
    <>
      Surtout causée par <b>{pire.nom}</b> : {pire.valeur} contre {pire.normal} habituellement, soit{" "}
      {Math.abs(pire.ecart)} σ {sens} de la normale.
    </>
  );
}

function Explication({ details, alerte, mesures }) {
  const [ouvert, setOuvert] = useState(false);
  const momentAlerte = new Date(alerte.created_at).getTime();
  const fenetre = [...mesures]
    .map((m) => ({ t: new Date(m.received_at).getTime(), temp: m.temp, hum: m.hum, gaz: m.gas }))
    .filter((m) => m.t >= momentAlerte - FENETRE_AVANT_MS && m.t <= momentAlerte + FENETRE_APRES_MS)
    .sort((a, b) => a.t - b.t);

  return (
    <div className="explication">
      <button type="button" className="btn small" onClick={() => setOuvert((o) => !o)} aria-expanded={ouvert}>
        {ouvert ? "Masquer le détail" : "Détail"}
      </button>
      {ouvert && !details && (
        <p className="explication-note">
          Pas de détail enregistré pour cette alerte : elle a été créée avant la mise à jour.
        </p>
      )}
      {ouvert && details && (
      <div className="explication-body">
        <div className="explication-modele">
          Modèle {details.modele}
          {details.facteur_lof !== undefined && <> · facteur LOF {details.facteur_lof} (normal ≈ 1)</>}
          {details.probabilite !== undefined && <> · probabilité de hausse {Math.round(details.probabilite * 100)} %</>}
        </div>
        <p className="explication-phrase">{phraseCausale(details)}</p>
        <table>
          <thead>
            <tr>
              <th>Caractéristique</th>
              <th>Valeur</th>
              <th>Normal</th>
              <th>Écart</th>
            </tr>
          </thead>
          <tbody>
            {details.caracteristiques.map((c) => (
              <tr key={c.nom} className={c.ecart !== undefined && Math.abs(c.ecart) > 3 ? "hors-norme" : ""}>
                <td>{c.nom}</td>
                <td>{c.valeur}</td>
                <td>{c.normal ?? "—"}</td>
                <td>{c.ecart !== undefined ? `${c.ecart} σ` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="explication-note">Écart en nombre d'écarts-types par rapport à la baseline apprise. Au-delà de 3 σ, la valeur est surlignée.</p>

        <div className="explication-evolution">
          <div className="explication-label">Évolution autour de l'alerte (10 min avant, 2 min après)</div>
          {fenetre.length < 2 ? (
            <p className="explication-note">
              Pas assez de mesures encore en mémoire côté dashboard pour tracer cette fenêtre.
            </p>
          ) : (
            <div className="sparkline">
              <ResponsiveContainer width="100%" height={90}>
                <LineChart data={fenetre}>
                  <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} hide />
                  <YAxis yAxisId="t" hide domain={["auto", "auto"]} />
                  <YAxis yAxisId="g" orientation="right" hide domain={["auto", "auto"]} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={formatHeure} />
                  <ReferenceLine x={momentAlerte} yAxisId="t" stroke="#ff6b6b" strokeDasharray="3 3" />
                  <Line yAxisId="t" type="monotone" dataKey="temp" stroke="#5fd9f0" dot={false} strokeWidth={1.5} name="Température" />
                  <Line yAxisId="g" type="monotone" dataKey="gaz" stroke="#ff6f6f" dot={false} strokeWidth={1.5} name="Gaz" />
                </LineChart>
              </ResponsiveContainer>
              <div className="chart-legend">
                <span><i style={{ background: "#5fd9f0" }} /> Température</span>
                <span><i style={{ background: "#ff6f6f" }} /> Gaz</span>
                <span><i style={{ background: "#ff6b6b" }} /> Moment de l'alerte</span>
              </div>
            </div>
          )}
        </div>
      </div>
      )}
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
