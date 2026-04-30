-- 1. Enable extension (required for UUID)
create extension if not exists pgcrypto;

-- 2. Ensure table exists in FINAL structure (fresh DB case)
create table if not exists session_closures (
    id uuid primary key default gen_random_uuid(),
    session_name text not null,
    target_date date not null,
    is_closed boolean not null default false,
    created_at timestamptz not null default now(),
    unique(session_name, target_date)
);

-- 3. Add missing columns if upgrading from old schema
alter table session_closures
    add column if not exists id uuid,
    add column if not exists session_name text,
    add column if not exists target_date date,
    add column if not exists is_closed boolean default false,
    add column if not exists created_at timestamptz;

-- 4. Migrate old data → new columns (only if old columns exist)
do $$
begin
    -- session → session_name
    if exists (
        select 1 from information_schema.columns
        where table_name = 'session_closures' and column_name = 'session'
    ) then
        execute '
            update session_closures
            set session_name = coalesce(session_name, session)
        ';
    end if;

    -- date → target_date
    if exists (
        select 1 from information_schema.columns
        where table_name = 'session_closures' and column_name = ''date''
    ) then
        execute '
            update session_closures
            set target_date = coalesce(target_date, "date")
        ';
    end if;

    -- closed_at → created_at
    if exists (
        select 1 from information_schema.columns
        where table_name = 'session_closures' and column_name = 'closed_at'
    ) then
        execute '
            update session_closures
            set created_at = coalesce(created_at, closed_at)
        ';
    end if;
end $$;

-- 5. Fill required values safely
update session_closures
set id = gen_random_uuid()
where id is null;

update session_closures
set session_name = coalesce(session_name, 'unknown')
where session_name is null;

update session_closures
set target_date = coalesce(target_date, current_date)
where target_date is null;

update session_closures
set is_closed = coalesce(is_closed, false);

update session_closures
set created_at = coalesce(created_at, now());

-- 6. Fix primary key
do $$
begin
    -- drop old composite PK if exists
    if exists (
        select 1 from pg_constraint
        where conrelid = 'session_closures'::regclass
        and contype = 'p'
    ) then
        alter table session_closures drop constraint session_closures_pkey;
    end if;
exception when undefined_table then null;
end $$;

alter table session_closures
    add primary key (id);

-- 7. Add unique constraint
create unique index if not exists uq_session_closures_session_date
on session_closures (session_name, target_date);

-- 8. Enforce NOT NULL + defaults
alter table session_closures
    alter column id set not null,
    alter column session_name set not null,
    alter column target_date set not null,
    alter column is_closed set default false,
    alter column created_at set default now();

-- 9. Remove old columns (cleanup)
alter table session_closures
    drop column if exists "date",
    drop column if exists session,
    drop column if exists closed_at;

-- 10. Reload Supabase schema cache
notify pgrst, 'reload schema';