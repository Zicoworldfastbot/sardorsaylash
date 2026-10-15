-- Supabase -> SQL Editor ga shu kodni to'liq tashlab, RUN bosing.
-- Bu kodni qayta-qayta ishga tushirish xavfsiz: mavjud ma'lumot o'chmaydi.
 
-- 1) Arizalar jadvali
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
 
-- 2) YANGI: "Kimga ovoz berasiz?" javobi alohida ustunda
alter table public.applications add column if not exists vote_for text;
 
-- 3) YANGI: sozlamalar jadvali (ovoz berish yoqilgan yoki to'xtatilgan)
create table if not exists public.settings (
  key   text primary key,
  value text not null
);
insert into public.settings (key, value) values ('voting_open', 'true')
  on conflict (key) do nothing;
 
-- Xavfsizlik: tashqaridan hech kim o'qiy/yoza olmasin.
-- Faqat bizning bot (secret/service_role kalit bilan) o'qiydi va yozadi.
alter table public.applications enable row level security;
alter table public.settings enable row level security;
 