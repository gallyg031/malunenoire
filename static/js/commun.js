/* Ma Lune Noire — comportements communs (feedback, e-mail, feuilles, mesure). ES2020, sans build. */
(function () {
  "use strict";
  const LLN = (window.LLN = {});
  const corps = document.body;
  const token = corps.dataset.token || null;

  LLN.appel = async function (url, corpsJson, methode) {
    const r = await fetch(url, {
      method: methode || "POST",
      headers: { "content-type": "application/json" },
      body: corpsJson === undefined ? undefined : JSON.stringify(corpsJson),
    });
    let data = null;
    if (r.status !== 204) data = await r.json().catch(() => null);
    return { statut: r.status, data };
  };

  LLN.evenement = function (name, props) {
    try {
      const b = new Blob([JSON.stringify({ name, props: props || null })], { type: "application/json" });
      if (!navigator.sendBeacon || !navigator.sendBeacon("/api/event", b)) {
        LLN.appel("/api/event", { name, props: props || null }).catch(() => {});
      }
    } catch (e) { /* la mesure ne bloque jamais rien */ }
  };

  LLN.memoire = {
    lire(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    ecrire(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* navigation privée */ } },
  };

  LLN.reduit = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  LLN.copier = async function (texte, bouton) {
    try {
      await navigator.clipboard.writeText(texte);
    } catch (e) {
      const t = document.createElement("textarea");
      t.value = texte; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); } catch (e2) { /* rien */ }
      t.remove();
    }
    if (bouton && bouton.dataset.ok) {
      const avant = bouton.textContent;
      bouton.textContent = bouton.dataset.ok;
      setTimeout(() => { bouton.textContent = avant; }, 2200);
    }
  };

  // liens et boutons qui comptent un événement (sans identifiant personnel)
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-event]");
    if (el) LLN.evenement(el.dataset.event, LLN.designActif ? { design: LLN.designActif() } : null);
  });

  // ---------------------------------------------------------------- feedback (spec 01 §8)
  document.querySelectorAll(".feedback").forEach((f) => {
    const cle = `lln:fb:${f.dataset.textId}:${f.dataset.version}:${f.dataset.part}`;
    const merci = f.querySelector(".feedback-merci");
    const fermer = () => { f.classList.add("fait"); merci.hidden = false; };
    if (LLN.memoire.lire(cle)) fermer();
    f.querySelectorAll(".feedback-vote").forEach((b) => b.addEventListener("click", () => {
      fermer();
      LLN.memoire.ecrire(cle, b.dataset.vote);
      LLN.appel("/api/feedback", {
        text_id: f.dataset.textId, text_version: Number(f.dataset.version), part: f.dataset.part,
        vote: Number(b.dataset.vote), no_time: f.dataset.noTime === "true",
      }).catch(() => {});
    }));
  });

  // ---------------------------------------------------------------- e-mail (spec 01 §9)
  const EMAIL = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/;
  const formulairesEmail = Array.from(document.querySelectorAll("form.email"));
  function emailEnregistre(masque) {
    formulairesEmail.forEach((form) => {
      const deja = form.querySelector(".email-deja-texte");
      deja.textContent = deja.dataset.gabarit.replace("{email}", masque);
      form.querySelector(".email-deja").hidden = false;
      form.querySelector(".email-saisie").hidden = true;
    });
  }
  formulairesEmail.forEach((form) => {
    const champ = form.querySelector(".email-champ");
    const err = form.querySelector(".email-erreur");
    form.querySelector(".email-modifier").addEventListener("click", () => {
      form.querySelector(".email-deja").hidden = true;
      form.querySelector(".email-saisie").hidden = false;
      champ.focus();
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const valeur = champ.value.trim().toLowerCase();
      if (!EMAIL.test(valeur)) { err.hidden = false; return; }
      err.hidden = true;
      const r = await LLN.appel(`/api/reading/${form.dataset.token}/email`, { email: valeur }).catch(() => null);
      if (!r || r.statut !== 200) { err.hidden = false; return; }
      emailEnregistre(r.data.email);
      form.querySelector(".email-deja").hidden = true;
      form.querySelector(".email-ok").hidden = false;
    });
  });

  // ---------------------------------------------------------------- feuilles
  function ouvrir(feuille) {
    feuille.hidden = false;
    const focus = feuille.querySelector("input, button, a");
    if (focus) focus.focus();
  }
  LLN.ouvrir = ouvrir;
  document.querySelectorAll(".ouvre-bientot").forEach((b) => b.addEventListener("click", () => {
    const f = document.getElementById("feuille-bientot");
    if (f) ouvrir(f);
  }));
  document.querySelectorAll(".feuille").forEach((f) => {
    f.addEventListener("click", (e) => { if (e.target === f || e.target.closest(".feuille-fermer")) f.hidden = true; });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.querySelectorAll(".feuille").forEach((f) => { f.hidden = true; });
  });

  // ---------------------------------------------------------------- lien personnel
  const copierLien = document.getElementById("copier-lien");
  if (copierLien && token) copierLien.addEventListener("click", () => {
    LLN.copier(`${location.origin}/l/${token}`, copierLien);
    LLN.evenement("copy_link");
  });

  // ---------------------------------------------------------------- effacement
  const effacer = document.getElementById("effacer");
  if (effacer) document.getElementById("effacer-bouton").addEventListener("click", async () => {
    const r = await LLN.appel(`/api/reading/${effacer.dataset.token}`, undefined, "DELETE").catch(() => null);
    if (!r || r.statut !== 200) { document.getElementById("effacer-erreur").hidden = false; return; }
    document.getElementById("effacer-texte").hidden = true;
    document.getElementById("effacer-actions").hidden = true;
    document.getElementById("efface").hidden = false;
  });
})();
