-- Reference list of supported currencies (curated major currencies only).
create table public.currencies (
    code text primary key,
    name text not null,
    is_active boolean not null default true
);

insert into public.currencies (code, name) values
    ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'British Pound'),
    ('INR', 'Indian Rupee'), ('JPY', 'Japanese Yen'), ('AUD', 'Australian Dollar'),
    ('CAD', 'Canadian Dollar'), ('CHF', 'Swiss Franc'), ('CNY', 'Chinese Yuan'),
    ('SGD', 'Singapore Dollar'), ('NZD', 'New Zealand Dollar'), ('AED', 'UAE Dirham');

-- Per-user watched currency pairs.
create table public.watchlist (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    base_code text not null references public.currencies (code),
    quote_code text not null references public.currencies (code),
    created_at timestamptz not null default now(),
    unique (user_id, base_code, quote_code)
);

alter table public.watchlist enable row level security;

create policy "watchlist_owner_select" on public.watchlist
    for select using (auth.uid() = user_id);
create policy "watchlist_owner_insert" on public.watchlist
    for insert with check (auth.uid() = user_id);
create policy "watchlist_owner_update" on public.watchlist
    for update using (auth.uid() = user_id);
create policy "watchlist_owner_delete" on public.watchlist
    for delete using (auth.uid() = user_id);

-- Cached daily exchange rates (written by the backend/cron via service role only).
create table public.rates_cache (
    id bigserial primary key,
    base_code text not null references public.currencies (code),
    quote_code text not null references public.currencies (code),
    rate numeric not null,
    as_of date not null,
    fetched_at timestamptz not null default now(),
    unique (base_code, quote_code, as_of)
);

alter table public.rates_cache enable row level security;
create policy "rates_cache_public_read" on public.rates_cache
    for select using (true);

-- Generated predictions (written by the backend/cron via service role only).
create table public.predictions (
    id bigserial primary key,
    base_code text not null references public.currencies (code),
    quote_code text not null references public.currencies (code),
    horizon_days integer not null,
    predicted_rate numeric not null,
    lower_bound numeric not null,
    upper_bound numeric not null,
    confidence text not null check (confidence in ('normal', 'low')),
    generated_at timestamptz not null default now()
);

alter table public.predictions enable row level security;
create policy "predictions_public_read" on public.predictions
    for select using (true);

-- User-defined alerts.
create table public.alerts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    base_code text not null references public.currencies (code),
    quote_code text not null references public.currencies (code),
    alert_type text not null check (alert_type in ('threshold', 'recommendation_change')),
    threshold_rate numeric,
    direction text check (direction in ('above', 'below')),
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

alter table public.alerts enable row level security;

create policy "alerts_owner_select" on public.alerts
    for select using (auth.uid() = user_id);
create policy "alerts_owner_insert" on public.alerts
    for insert with check (auth.uid() = user_id);
create policy "alerts_owner_update" on public.alerts
    for update using (auth.uid() = user_id);
create policy "alerts_owner_delete" on public.alerts
    for delete using (auth.uid() = user_id);

-- Per-user notification linking state.
create table public.notification_settings (
    user_id uuid primary key references auth.users (id) on delete cascade,
    telegram_chat_id text,
    telegram_linked_at timestamptz,
    email_verified boolean not null default false,
    email_verified_at timestamptz
);

alter table public.notification_settings enable row level security;

create policy "notification_settings_owner_select" on public.notification_settings
    for select using (auth.uid() = user_id);
create policy "notification_settings_owner_insert" on public.notification_settings
    for insert with check (auth.uid() = user_id);
create policy "notification_settings_owner_update" on public.notification_settings
    for update using (auth.uid() = user_id);

-- Per-user LLM provider configuration.
create table public.llm_settings (
    user_id uuid primary key references auth.users (id) on delete cascade,
    provider text not null check (provider in ('gemini', 'openai', 'deepseek', 'groq', 'openrouter')),
    api_key_encrypted text not null,
    model text,
    updated_at timestamptz not null default now()
);

alter table public.llm_settings enable row level security;

create policy "llm_settings_owner_select" on public.llm_settings
    for select using (auth.uid() = user_id);
create policy "llm_settings_owner_insert" on public.llm_settings
    for insert with check (auth.uid() = user_id);
create policy "llm_settings_owner_update" on public.llm_settings
    for update using (auth.uid() = user_id);
