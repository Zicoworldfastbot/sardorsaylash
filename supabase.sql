-- Supabase -> SQL Editor ga shu kodni to'liq tashlab, RUN bosing.
 
create table if not exists public.applications (
  id                bigint generated always as identity primary key,
  created_at        timestamptz not null default now(),
  telegram_id       bigint not null unique,   -- bitta akkaunt = bitta ariza
  telegram_username text,
  grade             int not null check (grade between 5 and 11),
  full_name         text not null,
  direction         text not null,
  region            text,
  institution       text,
  birth_date        date,
  phone             text,
  contact           text,
  answers           jsonb not null,
  signature         text,                     -- imzo rasmi (base64)
  agreed            boolean not null default false
);
 
-- Xavfsizlik: tashqaridan hech kim o'qiy/yoza olmasin.
-- Faqat bizning bot (secret/service_role kalit bilan) yozadi.
alter table public.applications enable row level security;