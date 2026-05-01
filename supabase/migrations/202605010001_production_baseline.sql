create extension if not exists pgcrypto;
create schema if not exists public;

do $$
declare
    role_name text;
begin
    foreach role_name in array array['anon', 'authenticated', 'service_role'] loop
        if exists (select 1 from pg_roles where rolname = role_name) then
            execute format('grant usage on schema public to %I', role_name);
        end if;
    end loop;
end $$;

create table if not exists public.admins (
    id bigserial primary key,
    name varchar(120) not null,
    phone varchar(20) not null unique,
    password_hash varchar(255) not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_admins_phone_normalized on public.admins (phone);

create table if not exists public.farmers (
    id bigserial primary key,
    unique_code integer not null unique,
    name varchar(120) not null,
    phone varchar(20) not null unique,
    village varchar(120),
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create index if not exists idx_farmers_name on public.farmers (name);
create index if not exists idx_farmers_phone on public.farmers (phone);
create index if not exists idx_farmers_unique_code on public.farmers (unique_code);
create unique index if not exists uq_farmers_name_lower on public.farmers ((lower(btrim(name))));

create table if not exists public.rates (
    id bigserial primary key,
    rate numeric(10,2) not null,
    effective_from timestamptz not null,
    created_by varchar(120) not null
);

create table if not exists public.milk_entries (
    id bigserial primary key,
    farmer_id bigint not null references public.farmers(id) on delete cascade,
    date date not null,
    session varchar(20) not null,
    quantity numeric(10,2) not null,
    rate numeric(10,2) not null,
    amount numeric(12,2) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (farmer_id, date, session)
);

create index if not exists idx_milk_entries_date_session on public.milk_entries (date, session);
create index if not exists idx_milk_entries_farmer_date on public.milk_entries (farmer_id, date);

create table if not exists public.payments (
    id bigserial primary key,
    farmer_id bigint not null references public.farmers(id) on delete cascade,
    amount_paid numeric(12,2) not null,
    payment_date date not null,
    note varchar(255),
    created_at timestamptz not null default now()
);

create index if not exists idx_payments_farmer_date on public.payments (farmer_id, payment_date);

create table if not exists public.store_transactions (
    id bigserial primary key,
    farmer_id bigint not null references public.farmers(id) on delete cascade,
    bill_date date not null,
    item_count integer not null default 0,
    total_amount numeric(12,2) not null,
    note varchar(255),
    entry_source varchar(30) not null default 'dashboard',
    duplicate_guard varchar(64) unique,
    is_locked boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_store_transactions_farmer_date on public.store_transactions (farmer_id, bill_date);
create index if not exists idx_store_transactions_bill_date on public.store_transactions (bill_date);

create table if not exists public.store_transaction_items (
    id bigserial primary key,
    transaction_id bigint not null references public.store_transactions(id) on delete cascade,
    item_name varchar(160) not null,
    quantity numeric(10,2) not null,
    unit varchar(40),
    unit_price numeric(12,2) not null,
    subtotal numeric(12,2) not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_store_transaction_items_transaction on public.store_transaction_items (transaction_id);

create table if not exists public.monthly_settlements (
    id bigserial primary key,
    farmer_id bigint not null references public.farmers(id) on delete cascade,
    settlement_month date not null,
    milk_total numeric(12,2) not null,
    store_credit_total numeric(12,2) not null,
    net_amount numeric(12,2) not null,
    status varchar(30) not null,
    is_locked boolean not null default true,
    settled_on timestamptz,
    note text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (farmer_id, settlement_month)
);

create index if not exists idx_monthly_settlements_month on public.monthly_settlements (settlement_month);

create table if not exists public.payment_logs (
    id bigserial primary key,
    farmer_id bigint not null references public.farmers(id) on delete cascade,
    settlement_id bigint references public.monthly_settlements(id) on delete set null,
    payment_date date not null,
    amount numeric(12,2) not null,
    direction varchar(20) not null,
    note varchar(255),
    created_at timestamptz not null default now()
);

create index if not exists idx_payment_logs_farmer_date on public.payment_logs (farmer_id, payment_date);

create table if not exists public.app_settings (
    key varchar(80) primary key,
    value text not null
);

create table if not exists public.whatsapp_states (
    phone varchar(20) primary key,
    role varchar(20) not null,
    state varchar(60) not null,
    context_value varchar(60),
    last_entry_id bigint,
    last_farmer_id bigint,
    updated_at timestamptz not null default now()
);

create table if not exists public.processed_messages (
    message_id varchar(120) primary key,
    phone varchar(20) not null,
    processed_at timestamptz not null default now()
);

create table if not exists public.session_closures (
    id uuid primary key default gen_random_uuid(),
    session_name text not null,
    target_date date not null,
    is_closed boolean not null default false,
    created_at timestamptz not null default now()
);

alter table public.session_closures
    add column if not exists id uuid,
    add column if not exists session_name text,
    add column if not exists target_date date,
    add column if not exists is_closed boolean,
    add column if not exists created_at timestamptz;

do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'session_closures'
          and column_name = 'session'
    ) then
        execute '
            update public.session_closures
            set session_name = coalesce(session_name, session)
            where session_name is null
        ';
    end if;

    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'session_closures'
          and column_name = 'date'
    ) then
        execute '
            update public.session_closures
            set target_date = coalesce(target_date, "date")
            where target_date is null
        ';
    end if;

    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'session_closures'
          and column_name = 'closed_at'
    ) then
        execute '
            update public.session_closures
            set created_at = coalesce(created_at, closed_at)
            where created_at is null
        ';
    end if;
end $$;

update public.session_closures
set id = coalesce(id, gen_random_uuid()),
    session_name = coalesce(nullif(session_name, ''), 'unknown'),
    target_date = coalesce(target_date, current_date),
    is_closed = coalesce(is_closed, true),
    created_at = coalesce(created_at, now());

do $$
begin
    begin
        alter table public.session_closures drop constraint if exists session_closures_pkey;
    exception when undefined_table then
        null;
    end;

    alter table public.session_closures
        add constraint session_closures_pkey primary key (id);
exception when duplicate_table then
    null;
when duplicate_object then
    null;
end $$;

create unique index if not exists uq_session_closures_session_target_date
on public.session_closures (session_name, target_date);

alter table public.session_closures
    alter column id set default gen_random_uuid(),
    alter column id set not null,
    alter column session_name set not null,
    alter column target_date set not null,
    alter column is_closed set default false,
    alter column is_closed set not null,
    alter column created_at set default now(),
    alter column created_at set not null;

alter table public.session_closures
    drop column if exists "date",
    drop column if exists session,
    drop column if exists closed_at;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_admins_phone_digits'
    ) then
        alter table public.admins
            add constraint chk_admins_phone_digits
            check (phone ~ '^[0-9]{10,20}$');
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_farmers_unique_code_positive'
    ) then
        alter table public.farmers
            add constraint chk_farmers_unique_code_positive
            check (unique_code > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_farmers_phone_digits'
    ) then
        alter table public.farmers
            add constraint chk_farmers_phone_digits
            check (phone ~ '^[0-9]{10,20}$');
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_rates_positive'
    ) then
        alter table public.rates
            add constraint chk_rates_positive
            check (rate > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_milk_entries_session'
    ) then
        alter table public.milk_entries
            add constraint chk_milk_entries_session
            check (session in ('morning', 'evening'));
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_milk_entries_quantity_nonnegative'
    ) then
        alter table public.milk_entries
            add constraint chk_milk_entries_quantity_nonnegative
            check (quantity >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_milk_entries_rate_nonnegative'
    ) then
        alter table public.milk_entries
            add constraint chk_milk_entries_rate_nonnegative
            check (rate >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_milk_entries_amount_nonnegative'
    ) then
        alter table public.milk_entries
            add constraint chk_milk_entries_amount_nonnegative
            check (amount >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_payments_amount_positive'
    ) then
        alter table public.payments
            add constraint chk_payments_amount_positive
            check (amount_paid > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transactions_item_count_nonnegative'
    ) then
        alter table public.store_transactions
            add constraint chk_store_transactions_item_count_nonnegative
            check (item_count >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transactions_total_amount_nonnegative'
    ) then
        alter table public.store_transactions
            add constraint chk_store_transactions_total_amount_nonnegative
            check (total_amount >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transaction_items_quantity_positive'
    ) then
        alter table public.store_transaction_items
            add constraint chk_store_transaction_items_quantity_positive
            check (quantity > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transaction_items_unit_price_nonnegative'
    ) then
        alter table public.store_transaction_items
            add constraint chk_store_transaction_items_unit_price_nonnegative
            check (unit_price >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transaction_items_subtotal_nonnegative'
    ) then
        alter table public.store_transaction_items
            add constraint chk_store_transaction_items_subtotal_nonnegative
            check (subtotal >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_monthly_settlements_status'
    ) then
        alter table public.monthly_settlements
            add constraint chk_monthly_settlements_status
            check (status in ('Pay Farmer', 'Farmer Owes', 'Settled', 'pay_farmer', 'farmer_owes', 'settled'));
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_payment_logs_amount_positive'
    ) then
        alter table public.payment_logs
            add constraint chk_payment_logs_amount_positive
            check (amount > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_payment_logs_direction'
    ) then
        alter table public.payment_logs
            add constraint chk_payment_logs_direction
            check (direction in ('to_farmer', 'from_farmer'));
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_whatsapp_states_role'
    ) then
        alter table public.whatsapp_states
            add constraint chk_whatsapp_states_role
            check (role in ('owner', 'farmer'));
    end if;
end $$;

do $$
declare
    table_name text;
    role_name text;
    app_tables text[] := array[
        'admins',
        'farmers',
        'rates',
        'milk_entries',
        'payments',
        'store_transactions',
        'store_transaction_items',
        'monthly_settlements',
        'payment_logs',
        'app_settings',
        'whatsapp_states',
        'processed_messages',
        'session_closures'
    ];
begin
    foreach table_name in array app_tables loop
        execute format('alter table public.%I disable row level security', table_name);
    end loop;

    foreach role_name in array array['anon', 'authenticated', 'service_role'] loop
        if exists (select 1 from pg_roles where rolname = role_name) then
            execute format('grant select, insert, update, delete on all tables in schema public to %I', role_name);
            execute format('grant usage, select on all sequences in schema public to %I', role_name);
        end if;
    end loop;
end $$;

alter default privileges in schema public grant select, insert, update, delete on tables to anon, authenticated, service_role;
alter default privileges in schema public grant usage, select on sequences to anon, authenticated, service_role;

notify pgrst, 'reload schema';
