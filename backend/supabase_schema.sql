create table if not exists admins (
    id bigserial primary key,
    name varchar(120) not null,
    phone varchar(20) unique not null,
    password_hash varchar(255) not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_admins_phone_normalized on admins (phone);

create table if not exists farmers (
    id bigserial primary key,
    unique_code integer unique not null,
    name varchar(120) not null,
    phone varchar(20) unique not null,
    village varchar(120),
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create index if not exists idx_farmers_name on farmers (name);
create index if not exists idx_farmers_phone on farmers (phone);
create index if not exists idx_farmers_unique_code on farmers (unique_code);
create unique index if not exists uq_farmers_name_lower on farmers ((lower(btrim(name))));

create table if not exists rates (
    id bigserial primary key,
    rate numeric(10,2) not null,
    effective_from timestamptz not null,
    created_by varchar(120) not null
);

create table if not exists milk_entries (
    id bigserial primary key,
    farmer_id bigint not null references farmers(id) on delete cascade,
    date date not null,
    session varchar(20) not null check (session in ('morning', 'evening')),
    quantity numeric(10,2) not null,
    rate numeric(10,2) not null,
    amount numeric(12,2) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (farmer_id, date, session)
);

create index if not exists idx_milk_entries_date_session on milk_entries (date, session);
create index if not exists idx_milk_entries_farmer_date on milk_entries (farmer_id, date);

create table if not exists payments (
    id bigserial primary key,
    farmer_id bigint not null references farmers(id) on delete cascade,
    amount_paid numeric(12,2) not null,
    payment_date date not null,
    note varchar(255),
    created_at timestamptz not null default now()
);

create table if not exists store_transactions (
    id bigserial primary key,
    farmer_id bigint not null references farmers(id) on delete cascade,
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

create index if not exists idx_store_transactions_farmer_date on store_transactions (farmer_id, bill_date);
create index if not exists idx_store_transactions_bill_date on store_transactions (bill_date);

create table if not exists store_transaction_items (
    id bigserial primary key,
    transaction_id bigint not null references store_transactions(id) on delete cascade,
    item_name varchar(160) not null,
    quantity numeric(10,2) not null,
    unit varchar(40),
    unit_price numeric(12,2) not null,
    subtotal numeric(12,2) not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_store_transaction_items_transaction on store_transaction_items (transaction_id);

create table if not exists monthly_settlements (
    id bigserial primary key,
    farmer_id bigint not null references farmers(id) on delete cascade,
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

create index if not exists idx_monthly_settlements_month on monthly_settlements (settlement_month);

create table if not exists payment_logs (
    id bigserial primary key,
    farmer_id bigint not null references farmers(id) on delete cascade,
    settlement_id bigint references monthly_settlements(id) on delete set null,
    payment_date date not null,
    amount numeric(12,2) not null,
    direction varchar(20) not null check (direction in ('to_farmer', 'from_farmer')),
    note varchar(255),
    created_at timestamptz not null default now()
);

create index if not exists idx_payment_logs_farmer_date on payment_logs (farmer_id, payment_date);

create table if not exists app_settings (
    key varchar(80) primary key,
    value text not null
);

create table if not exists whatsapp_states (
    phone varchar(20) primary key,
    role varchar(20) not null,
    state varchar(60) not null,
    context_value varchar(60),
    last_entry_id bigint,
    last_farmer_id bigint,
    updated_at timestamptz not null default now()
);

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_admins_phone_digits'
    ) then
        alter table admins
            add constraint chk_admins_phone_digits
            check (phone ~ '^[0-9]{10,20}$');
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_farmers_unique_code_positive'
    ) then
        alter table farmers
            add constraint chk_farmers_unique_code_positive
            check (unique_code > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_farmers_phone_digits'
    ) then
        alter table farmers
            add constraint chk_farmers_phone_digits
            check (phone ~ '^[0-9]{10,20}$');
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_rates_positive'
    ) then
        alter table rates
            add constraint chk_rates_positive
            check (rate > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_milk_entries_quantity_nonnegative'
    ) then
        alter table milk_entries
            add constraint chk_milk_entries_quantity_nonnegative
            check (quantity >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_milk_entries_rate_nonnegative'
    ) then
        alter table milk_entries
            add constraint chk_milk_entries_rate_nonnegative
            check (rate >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_milk_entries_amount_nonnegative'
    ) then
        alter table milk_entries
            add constraint chk_milk_entries_amount_nonnegative
            check (amount >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_payments_amount_positive'
    ) then
        alter table payments
            add constraint chk_payments_amount_positive
            check (amount_paid > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transactions_item_count_nonnegative'
    ) then
        alter table store_transactions
            add constraint chk_store_transactions_item_count_nonnegative
            check (item_count >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transactions_total_amount_nonnegative'
    ) then
        alter table store_transactions
            add constraint chk_store_transactions_total_amount_nonnegative
            check (total_amount >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transaction_items_quantity_positive'
    ) then
        alter table store_transaction_items
            add constraint chk_store_transaction_items_quantity_positive
            check (quantity > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transaction_items_unit_price_nonnegative'
    ) then
        alter table store_transaction_items
            add constraint chk_store_transaction_items_unit_price_nonnegative
            check (unit_price >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_store_transaction_items_subtotal_nonnegative'
    ) then
        alter table store_transaction_items
            add constraint chk_store_transaction_items_subtotal_nonnegative
            check (subtotal >= 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_monthly_settlements_status'
    ) then
        alter table monthly_settlements
            add constraint chk_monthly_settlements_status
            check (status in ('pay_farmer', 'farmer_owes', 'settled'));
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_payment_logs_amount_positive'
    ) then
        alter table payment_logs
            add constraint chk_payment_logs_amount_positive
            check (amount > 0);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_whatsapp_states_role'
    ) then
        alter table whatsapp_states
            add constraint chk_whatsapp_states_role
            check (role in ('owner', 'farmer'));
    end if;
end $$;
