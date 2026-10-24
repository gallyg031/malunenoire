/* Ma Lune Noire — l'entrée et la cérémonie de calcul (spec 01 §4-5). */
(function () {
  "use strict";
  const LLN = window.LLN;
  const $ = (id) => document.getElementById(id);
  const form = $("formulaire");
  const champDate = $("date"), champHeure = $("heure"), champLieu = $("lieu");
  const liste = $("suggestions"), bouton = $("reveler");
  const M = form.dataset;

  const MOIS = { janvier: 1, janv: 1, jan: 1, fevrier: 2, fevr: 2, fev: 2, mars: 3, mar: 3, avril: 4, avr: 4,
    mai: 5, juin: 6, juillet: 7, juil: 7, aout: 8, septembre: 9, sept: 9, sep: 9, octobre: 10, oct: 10,
    novembre: 11, nov: 11, decembre: 12, dec: 12 };
  const MOIS_AFF = ["JANVIER", "FÉVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET", "AOÛT", "SEPTEMBRE",
    "OCTOBRE", "NOVEMBRE", "DÉCEMBRE"];
  const sansAccent = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  // ---------------------------------------------------------------- date
  function lireDate(brut) {
    const s = sansAccent(brut.trim()).replace(/\s+/g, " ");
    if (!s) return { vide: true };
    let j, m, a, r;
    if ((r = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/))) [a, m, j] = [+r[1], +r[2], +r[3]];
    else if ((r = s.match(/^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$/))) [j, m, a] = [+r[1], +r[2], +r[3]];
    else if ((r = s.match(/^(\d{1,2})(?:er)? ([a-z]+)\.? (\d{4})$/)) && MOIS[r[2]]) [j, m, a] = [+r[1], MOIS[r[2]], +r[3]];
    else return { invalide: true };
    const d = new Date(Date.UTC(a, m - 1, j));
    if (d.getUTCFullYear() !== a || d.getUTCMonth() !== m - 1 || d.getUTCDate() !== j) return { invalide: true };
    const aujourdhui = new Date();
    const limite = Date.UTC(aujourdhui.getFullYear(), aujourdhui.getMonth(), aujourdhui.getDate());
    if (a < 1900 || d.getTime() > limite) return { invalide: true };
    const iso = `${a}-${String(m).padStart(2, "0")}-${String(j).padStart(2, "0")}`;
    return { iso, affichage: `${j} ${MOIS_AFF[m - 1]} ${a}` };
  }

  // ---------------------------------------------------------------- heure
  let sansHeure = false;
  function lireHeure(brut) {
    const r = brut.trim().toLowerCase().match(/^(\d{1,2})\s*[:h. ]?\s*(\d{2})$/);
    if (!r || +r[1] > 23 || +r[2] > 59) return null;
    return `${r[1].padStart(2, "0")}:${r[2]}`;
  }
  $("bascule-heure").addEventListener("click", () => {
    sansHeure = !sansHeure;
    champHeure.hidden = sansHeure;
    $("sans-heure").hidden = !sansHeure;
    $("note-sans-heure").hidden = !sansHeure;
    $("err-heure").hidden = true;
    $("bascule-heure").textContent = sansHeure ? M.lienAvec : M.lienSans;
    majBouton();
  });

  // ---------------------------------------------------------------- lieu (spec 05 §5 : 250 ms, ≥ 1 caractère)
  let suggestions = [], choisi = null, minuteur = null, actif = -1, requete = 0;
  function afficherSuggestions() {
    liste.innerHTML = "";
    suggestions.slice(0, 4).forEach((s, i) => {
      const li = document.createElement("li");
      li.textContent = s.label;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", i === actif ? "true" : "false");
      li.addEventListener("mousedown", (e) => { e.preventDefault(); choisir(s); });
      liste.appendChild(li);
    });
    const ouvert = suggestions.length > 0 && document.activeElement === champLieu && !choisi;
    liste.hidden = !ouvert;
    champLieu.setAttribute("aria-expanded", ouvert ? "true" : "false");
  }
  function choisir(s) {
    choisi = s;
    champLieu.value = s.label;
    suggestions = [s];
    liste.hidden = true;
    champLieu.setAttribute("aria-expanded", "false");
    $("err-lieu").hidden = true;
    majBouton();
  }
  async function chercher(q) {
    const n = ++requete;
    try {
      const r = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
      const data = r.ok ? await r.json() : [];
      if (n !== requete) return;
      suggestions = Array.isArray(data) ? data : [];
      actif = -1;
      afficherSuggestions();
      majBouton();
    } catch (e) { /* réseau : on garde les suggestions précédentes */ }
  }
  champLieu.addEventListener("input", () => {
    choisi = null;
    clearTimeout(minuteur);
    const q = champLieu.value.trim();
    if (!q) { suggestions = []; afficherSuggestions(); majBouton(); return; }
    minuteur = setTimeout(() => chercher(q), 250);
    majBouton();
  });
  champLieu.addEventListener("focus", afficherSuggestions);
  champLieu.addEventListener("blur", () => setTimeout(() => { liste.hidden = true; }, 120));
  champLieu.addEventListener("keydown", (e) => {
    const n = Math.min(suggestions.length, 4);
    if (!n || choisi) return;
    if (e.key === "ArrowDown") { actif = (actif + 1) % n; afficherSuggestions(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { actif = (actif - 1 + n) % n; afficherSuggestions(); e.preventDefault(); }
    else if (e.key === "Enter" && actif >= 0) { choisir(suggestions[actif]); e.preventDefault(); }
    else if (e.key === "Escape") { liste.hidden = true; }
  });

  // ---------------------------------------------------------------- validation
  function erreur(id, texte) { const el = $(id); el.textContent = texte || ""; el.hidden = !texte; }
  function etat() {
    const d = lireDate(champDate.value);
    const h = sansHeure ? null : lireHeure(champHeure.value);
    const lieu = choisi || (champLieu.value.trim() && suggestions[0]) || null;
    return { d, h, lieu, ok: !!d.iso && (sansHeure || !!h) && !!lieu };
  }
  function majBouton() { bouton.disabled = !etat().ok; }
  [champDate, champHeure].forEach((c) => c.addEventListener("input", majBouton));
  champDate.addEventListener("blur", () => {
    const d = lireDate(champDate.value);
    erreur("err-date", d.vide ? "" : d.invalide ? M.errInexistante : "");
  });
  champHeure.addEventListener("blur", () => {
    if (!champHeure.value.trim()) return erreur("err-heure", "");
    const h = lireHeure(champHeure.value);
    if (h) champHeure.value = h;
    erreur("err-heure", h ? "" : M.errHeure);
  });

  // ---------------------------------------------------------------- la cérémonie
  const calcul = $("calcul"), anneau = $("anneau"), diamant = $("diamant");
  const lignes = Array.from(calcul.querySelectorAll(".statut-ligne"));
  const ligne3AvecHeure = $("ligne3").textContent;
  const MIN = LLN.reduit ? 0 : 5400, RESOLUTION = LLN.reduit ? 300 : 1200, TROP_LONG = 25000;
  let envoi = null;

  function montrerLigne(i) { lignes.forEach((l) => l.classList.toggle("on", Number(l.dataset.i) === i)); }

  function ceremonie(entree) {
    const t0 = performance.now();
    let reponse = null, erreurApi = null, fini = false, degAff = 0, tDeg = null;
    const coord = [entree.d.affichage, entree.h, entree.lieu.name.toUpperCase()].filter(Boolean);
    $("coordonnees").innerHTML = "";
    coord.forEach((c, i) => {
      if (i) $("coordonnees").appendChild(document.createElement("i"));
      const s = document.createElement("span"); s.textContent = c; $("coordonnees").appendChild(s);
    });
    $("ligne3").textContent = entree.h ? ligne3AvecHeure : calcul.dataset.ligne3Sans;
    $("releve-deg").textContent = "0";
    $("releve-signe").textContent = "· · ·";
    diamant.classList.remove("on");
    montrerLigne(0);

    envoi = LLN.appel("/api/reading", {
      date: entree.d.iso, time: entree.h, tz_user: Intl.DateTimeFormat().resolvedOptions().timeZone,
      place: { name: entree.lieu.label, lat: entree.lieu.lat, lon: entree.lieu.lon, tz: entree.lieu.tz },
    }).then((r) => {
      if (r.statut === 200) {
        reponse = r.data;
        $("releve-signe").textContent = reponse.sign_label.toUpperCase();
        $("resolution").textContent = reponse.sign_label.toUpperCase() +
          (reponse.house_roman ? ` — ${calcul.dataset.maison} ${reponse.house_roman}` : "");
        tDeg = performance.now();
      } else erreurApi = r;
    }).catch(() => { erreurApi = { statut: 0 }; });

    function image(t) {
      if (fini) return;
      const ecoule = t - t0;
      // anneau : se ferme en 5,4 s, puis boucle tant que le ciel ne répond pas
      const p = MIN ? (ecoule % MIN) / MIN * 100 : 100;
      anneau.parentElement.style.setProperty("--p", (reponse && ecoule >= MIN) ? 100 : p);
      if (p > 93 || (reponse && ecoule >= MIN)) diamant.classList.add("on");
      // degré : compte jusqu'au degré dans le signe, jamais au-delà
      if (reponse) {
        const duree = Math.max(MIN - (tDeg - t0), 900);
        const k = Math.min((t - tDeg) / duree, 1);
        degAff = Math.round(k * reponse.deg);
        $("releve-deg").textContent = String(degAff);
      }
      // statut : une ligne toutes les 1,8 s
      if (!reponse || ecoule < MIN) montrerLigne(Math.min(Math.floor(ecoule / 1800), 2));
      if (erreurApi) return echec(erreurApi);
      if (ecoule > TROP_LONG && !reponse) return lent();
      if (reponse && ecoule >= MIN) return resoudre();
      requestAnimationFrame(image);
    }
    function resoudre() {
      fini = true;
      $("releve-deg").textContent = String(reponse.deg);
      montrerLigne(3);
      setTimeout(() => { window.location.href = `/l/${reponse.token}`; }, RESOLUTION);
    }
    function lent() { fini = true; montrerLigne(4); }
    function echec(r) {
      fini = true;
      if (r.statut === 400) {           // retour au formulaire, message sous la date
        calcul.hidden = true; $("entree").hidden = false; $("voile").classList.remove("on");
        erreur("err-date", (r.data && r.data.message) || M.errInexistante);
        return;
      }
      $("calcul-message").textContent = (r.data && r.data.message) || $("calcul-message").textContent;
      montrerLigne(4);
    }
    requestAnimationFrame(image);
  }

  let derniere = null;
  $("reessayer").addEventListener("click", () => { if (derniere) ceremonie(derniere); });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const s = etat();
    if (!s.d.iso) return erreur("err-date", s.d.vide ? M.errVide : M.errInexistante);
    if (!sansHeure && !s.h) return erreur("err-heure", M.errHeure);
    if (!s.lieu) return erreur("err-lieu", M.errLieu);
    derniere = s;
    bouton.disabled = true;
    $("voile").classList.add("on");                       // fondu au noir (0,6 s)
    setTimeout(() => {
      $("entree").hidden = true;
      calcul.hidden = false;
      window.scrollTo(0, 0);
      $("voile").classList.remove("on");
    }, LLN.reduit ? 0 : 600);
    ceremonie(s);
  });

  majBouton();
})();
