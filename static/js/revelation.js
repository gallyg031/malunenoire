/* Ma Lune Noire — la révélation (spec 01 §6, 04 §6-7). */
(function () {
  "use strict";
  const LLN = window.LLN;
  const $ = (id) => document.getElementById(id);
  const corps = document.body;
  const shareId = corps.dataset.shareId, token = corps.dataset.token;

  // ---------------------------------------------------------------- séquence du héro (une seule fois par lecture)
  corps.classList.add("anime");
  const cleVu = `lln:vu:${shareId}`;
  if (LLN.memoire.lire(cleVu)) {
    corps.classList.add("vu");
  } else {
    LLN.memoire.ecrire(cleVu, "1");
    requestAnimationFrame(() => requestAnimationFrame(() => corps.classList.add("joue")));
  }

  // ---------------------------------------------------------------- bandeau épinglé
  const bandeau = $("bandeau"), hero = $("hero");
  new IntersectionObserver(([e]) => bandeau.classList.toggle("visible", !e.isIntersecting),
    { threshold: 0 }).observe(hero);

  // ---------------------------------------------------------------- éclats : s'allument sous 78 % de l'écran
  const allumer = new IntersectionObserver((entrees) => entrees.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("on"); allumer.unobserve(e.target); }
  }), { rootMargin: "0px 0px -22% 0px" });
  document.querySelectorAll(".allume").forEach((el) => allumer.observe(el));

  // ---------------------------------------------------------------- le fond du signe affleure (0 → 0,22 entre 18 % et 58 %)
  const fond = $("eclats-fond"), voile = $("eclats-voile");
  if (fond) {
    fond.style.backgroundImage = `url("${fond.dataset.fond}")`;
    let attente = false;
    const maj = () => {
      attente = false;
      const max = document.documentElement.scrollHeight - innerHeight;
      const prog = max > 0 ? scrollY / max : 0;
      const k = Math.min(Math.max((prog - 0.18) / 0.40, 0), 1);
      fond.style.opacity = String(k * 0.22);
      voile.style.opacity = String(k);
    };
    addEventListener("scroll", () => { if (!attente) { attente = true; requestAnimationFrame(maj); } }, { passive: true });
    maj();
  }

  // ---------------------------------------------------------------- j'ai retrouvé mon heure
  const ouvrirHeure = $("ouvrir-heure");
  if (ouvrirHeure) {
    const f = $("heure-inline"), champ = $("heure-retrouvee"), err = f.querySelector(".erreur");
    ouvrirHeure.addEventListener("click", () => { f.hidden = false; ouvrirHeure.hidden = true; champ.focus(); });
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const r = champ.value.trim().match(/^(\d{1,2})\s*[:h. ]?\s*(\d{2})$/);
      if (!r || +r[1] > 23 || +r[2] > 59) { err.hidden = false; return; }
      const heure = `${r[1].padStart(2, "0")}:${r[2]}`;
      const rep = await LLN.appel(`/api/reading/${token}`, { time: heure }, "PATCH").catch(() => null);
      if (!rep || rep.statut !== 200) { err.hidden = false; return; }
      location.reload();
    });
  }

  // ---------------------------------------------------------------- carrousel des designs
  const carrousel = $("carrousel");
  const items = Array.from(carrousel.querySelectorAll(".carrousel-item"));
  const points = Array.from(document.querySelectorAll("#points i"));
  const PAS = 286;                                     // 262 + 24
  const cleDesign = `lln:design:${shareId}`;
  const designs = items.map((i) => i.dataset.design);
  let index = Math.max(designs.indexOf(LLN.memoire.lire(cleDesign) || ""), 0);
  let minuteurPatch = null;
  LLN.designActif = () => designs[index];

  function majDesign(i, memoriser) {
    index = i;
    points.forEach((p, k) => p.classList.toggle("on", k === i));
    const d = designs[i];
    document.querySelectorAll("#enregistrer, #feuille-enregistrer").forEach((a) => {
      a.href = `/c/${shareId}/carte.png?d=${d}&v=${corps.dataset.version}`;
    });
    if (!memoriser) return;
    LLN.memoire.ecrire(cleDesign, d);
    clearTimeout(minuteurPatch);
    minuteurPatch = setTimeout(() => {
      LLN.appel(`/api/reading/${token}`, { design: d }, "PATCH").catch(() => {});
      LLN.evenement("design_change", { design: d });
    }, 800);
  }
  carrousel.scrollLeft = index * PAS;
  majDesign(index, false);
  let attenteC = false;
  carrousel.addEventListener("scroll", () => {
    if (attenteC) return;
    attenteC = true;
    requestAnimationFrame(() => {
      attenteC = false;
      const i = Math.min(Math.max(Math.round(carrousel.scrollLeft / PAS), 0), items.length - 1);
      if (i !== index) majDesign(i, true);
    });
  }, { passive: true });

  // ---------------------------------------------------------------- partager (spec 04 §6)
  const partager = $("partager");
  const urlPartage = () => `${location.origin}/c/${shareId}?d=${designs[index]}`;
  partager.addEventListener("click", async () => {
    const design = designs[index];
    LLN.evenement("share_click", { design });
    if (!navigator.share) return LLN.ouvrir($("feuille-partage"));
    const donnees = { title: partager.dataset.titre, text: partager.dataset.phrase, url: urlPartage() };
    const essai = new File([""], "ma-lune-noire.png", { type: "image/png" });
    if (navigator.canShare && navigator.canShare({ files: [essai] })) {   // l'image seulement si l'OS sait la partager
      try {
        const r = await fetch(`/c/${shareId}/carte.png?d=${design}&v=${corps.dataset.version}`);
        if (r.ok) donnees.files = [new File([await r.blob()], "ma-lune-noire.png", { type: "image/png" })];
      } catch (e) { /* on partage sans l'image */ }
    }
    try {
      await navigator.share(donnees);
      LLN.evenement("share_done", { design });
    } catch (e) { /* annulé */ }
  });
  const feuilleCopier = $("feuille-copier");
  feuilleCopier.addEventListener("click", () => LLN.copier(urlPartage(), feuilleCopier));
})();
