create extension if not exists pgcrypto;

alter table if exists session_closures
    add column if not exists id uuid default gen_random_uuid(),
    add column if not exists session_name text,
    add column if not exists target_date date,
    add column if not exists is_closed boolean not null default false,
    add column if not exists created_at timestamptz not null default now();

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
            update session_closures
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
            update session_closures
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
            update session_closures
            set created_at = coalesce(created_at, closed_at)
            where created_at is null
        ';
    end if;
end $$;

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
set is_closed = true
where is_closed is distinct from true;

do $$
begin
    if exists (
        select 1
        from pg_constraint
        where conrelid = 'public.session_closures'::regclass
          and conname = 'session_closures_pkey'
    ) then
        alter table public.session_closures
            drop constraint session_closures_pkey;
    end if;
exception
    when undefined_table then
        null;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.session_closures'::regclass
          and contype = 'p'
    ) then
        alter table public.session_closures
            add constraint session_closures_pkey primary key (id);
    end if;
exception
    when undefined_table then
        null;
end $$;

create unique index if not exists uq_session_closures_session_date
    on session_closures (session_name, target_date);

alter table session_closures
    alter column id set not null,
    alter column session_name set not null,
    alter column target_date set not null,
    alter column is_closed set default false,
    alter column created_at set default now();

alter table if exists session_closures
    drop column if exists "date",
    drop column if exists session,
    drop column if exists closed_at;

notify pgrst, 'reload schema';
