-- Inventory module schema
-- Namespaced (inventory_*) to coexist with the existing raffle/game system
-- (game_settings, qr_codes, finds, raffle_draws) and the shared `profiles` table.
--
-- Run this once in the Supabase SQL Editor for the new project.
-- These tables are only ever touched by the kiosk app using the service_role
-- key, so RLS is enabled with no policies -- nothing is exposed to anon/authenticated.

create table if not exists public.inventory_items (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    condition text,
    is_rented boolean not null default false,
    last_rented_person uuid references public.profiles(id),
    first_logged timestamptz not null default now()
);

-- Maps a physical card's raw scanned id (e.g. an 8-digit student id) to a profile.
-- Kept separate from `profiles` so the shared table stays free of kiosk-specific concerns.
create table if not exists public.inventory_card_links (
    card_id text primary key,
    profile_id uuid not null references public.profiles(id) on delete cascade,
    linked_at timestamptz not null default now()
);

-- One row per checkout. An open loan is a row with checked_in_at IS NULL.
-- Replaces the old free-text rental_history string mutation.
create table if not exists public.inventory_checkouts (
    id uuid primary key default gen_random_uuid(),
    item_id uuid not null references public.inventory_items(id) on delete cascade,
    user_id uuid not null references public.profiles(id) on delete cascade,
    checked_out_at timestamptz not null default now(),
    checked_out_by uuid references public.profiles(id),
    checked_in_at timestamptz,
    checked_in_by uuid references public.profiles(id),
    condition_at_return text
);

create index if not exists inventory_checkouts_open_item_idx
    on public.inventory_checkouts (item_id) where checked_in_at is null;
create index if not exists inventory_checkouts_open_user_idx
    on public.inventory_checkouts (user_id) where checked_in_at is null;

create table if not exists public.inventory_strikes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    item_id uuid references public.inventory_items(id) on delete set null,
    reason text not null,
    issued_by uuid references public.profiles(id),
    issued_at timestamptz not null default now()
);

alter table public.inventory_items enable row level security;
alter table public.inventory_card_links enable row level security;
alter table public.inventory_checkouts enable row level security;
alter table public.inventory_strikes enable row level security;
