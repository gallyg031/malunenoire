-- 002 — limites de débit (spec 05 §4, §7) : compteur par clé et par fenêtre fixe.
-- La clé est un hachage salé (IP ou token), jamais la valeur en clair.

create table if not exists ratelimit (
  key         text not null,
  bucket      timestamptz not null,
  count       integer not null default 0,
  primary key (key, bucket)
);
create index if not exists ratelimit_bucket_idx on ratelimit (bucket);
