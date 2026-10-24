/* Désinscription en un clic : la page envoie le POST elle-même (spec 01 §9, 06 §5). */
(function () {
  "use strict";
  const f = document.getElementById("desinscription");
  if (f) f.submit();
})();
