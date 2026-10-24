-- 001 — schéma initial (spec 05 §2). Phase 2 modélisée, non créée.

create table if not exists readings (
  id              uuid primary key default gen_random_uuid(),
  token           text unique not null,
  share_id        text unique not null,
  birth_date      date not null,
  birth_time      time,
  place_name      text not null,
  lat             double precision not null,
  lon             double precision not null,
  tz_birth        text not null,
  utc_offset_min  integer not null,
  tz_user         text,
  ln_lon          double precision not null,
  ln_sign         smallint not null,
  ln_house        smallint,
  house_reason    text,
  sign_changes_today boolean not null default false,
  cross_json      jsonb not null,
  intensity       double precision not null,
  text_id         text not null,
  text_version    integer not null,
  design          text not null default 'eclipse',
  email           text,
  email_consent_at timestamptz,
  email_unsub_at  timestamptz,
  activations_until date,
  engine_version  text not null,
  created_at      timestamptz not null default now(),
  last_seen_at    timestamptz not null default now(),
  deleted_at      timestamptz
);
create index if not exists readings_email_idx on readings (email) where email is not null;

create table if not exists activations (
  id          text primary key,
  reading_id  uuid not null references readings(id) on delete cascade,
  kind        text not null,
  body        text not null,
  aspect      text,
  point       text,
  sign_to     smallint,
  weight      smallint not null,
  enter_at    timestamptz not null,
  exit_at     timestamptz,
  exacts      timestamptz[] not null,
  created_at  timestamptz not null default now()
);
create index if not exists activations_reading_enter_idx on activations (reading_id, enter_at);
create index if not exists activations_exacts_idx on activations using gin (exacts);

create table if not exists feedback (
  id          bigserial primary key,
  text_id     text not null,
  text_version integer not null,
  part        text not null,
  vote        smallint not null,
  no_time     boolean not null,
  visitor_day text not null,
  created_at  timestamptz not null default now(),
  unique (text_id, part, visitor_day)
);

create table if not exists events (
  id          bigserial primary key,
  name        text not null,
  props       jsonb,
  created_at  timestamptz not null default now()
);

create table if not exists email_queue (
  id          bigserial primary key,
  reading_id  uuid not null references readings(id) on delete cascade,
  kind        text not null,
  ref         text,
  send_after  timestamptz not null,
  sent_at     timestamptz,
  attempts    smallint not null default 0,
  last_error  text,
  unique (reading_id, kind, ref)
);

create table if not exists purchases (
  id                bigserial primary key,
  reading_id        uuid not null references readings(id) on delete cascade,
  product           text not null,
  stripe_session_id text unique not null,
  amount_cents      integer not null,
  currency          text not null default 'eur',
  status            text not null,
  snapshot          jsonb,
  created_at        timestamptz not null default now(),
  paid_at           timestamptz
);

create table if not exists geocache (
  q           text primary key,
  results     jsonb not null,
  created_at  timestamptz not null default now()
);
