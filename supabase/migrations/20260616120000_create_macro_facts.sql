-- AI 資金流儀表 v1 — raw facts 時間序列表
-- Spec: Obsidian/Khouse/Macro_Weekly/90_AI_Drafts/2026-06-16_AI資金流儀表-設計spec.md §6.1
-- 只存「直接觀測值」(raw facts);衍生 lamp 不入此表(讀取時計算)。

create table if not exists public.macro_facts (
  fact_id      text primary key,                 -- hash(indicator_key + period_end + version)
  indicator_key text not null,
  edge_id      text,
  node_id      text,
  layer        text,                             -- L1..L5
  entity       text,
  metric_type  text,                             -- liquidity/rate/spread/price/employment...
  value        numeric not null,
  unit         text not null,                    -- usd_millions/pct/index...
  currency     text,
  period_end   date not null,
  release_date date,
  freq         text not null,                    -- daily/weekly/monthly/quarterly/irregular
  source_type  text not null,                    -- api/scrape/manual/nlm
  source_ref   text,                             -- e.g. "FRED:WALCL"
  value_hash   text,
  version      int not null default 1,
  ingested_at  timestamptz not null default now(),
  constraint macro_facts_identity unique (indicator_key, period_end, version)
);

create index if not exists macro_facts_key_period on public.macro_facts (indicator_key, period_end desc);

-- RLS: 前端 anon 只讀
alter table public.macro_facts enable row level security;
create policy macro_facts_anon_read on public.macro_facts for select to anon using (true);

-- rollback:
-- drop table if exists public.macro_facts cascade;
