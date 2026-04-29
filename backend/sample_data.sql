insert into admins (name, phone, password_hash)
values ('Owner', '919999999999', 'PASTE_GENERATED_WERKZEUG_PASSWORD_HASH_HERE')
on conflict (phone) do nothing;

insert into farmers (unique_code, name, phone, village, is_active) values
(1, 'Ramesh', '919900000001', 'Mandya', true),
(2, 'Suresh', '919900000002', 'Mysuru', true),
(3, 'Lakshmi', '919900000003', 'Hassan', true)
on conflict (unique_code) do nothing;

insert into rates (rate, effective_from, created_by)
values (42.00, now(), 'seed')
on conflict do nothing;

insert into app_settings (key, value) values
('morning_start', '06:00'),
('morning_end', '09:00'),
('evening_start', '18:00'),
('evening_end', '21:00')
on conflict (key) do nothing;

insert into milk_entries (farmer_id, date, session, quantity, rate, amount)
select id, current_date, 'morning', 5.50, 42.00, 231.00
from farmers
where unique_code = 1
on conflict (farmer_id, date, session) do nothing;

insert into milk_entries (farmer_id, date, session, quantity, rate, amount)
select id, current_date, 'evening', 4.75, 42.00, 199.50
from farmers
where unique_code = 1
on conflict (farmer_id, date, session) do nothing;

insert into payments (farmer_id, amount_paid, payment_date, note)
select id, 5000.00, current_date, 'Advance payment'
from farmers
where unique_code = 1;

with base_tx as (
    insert into store_transactions (farmer_id, bill_date, item_count, total_amount, note, entry_source, duplicate_guard)
    select id, current_date, 2, 480.00, 'Seed grocery bill', 'dashboard', md5('seed-store-1')
    from farmers
    where unique_code = 1
    on conflict (duplicate_guard) do update set total_amount = excluded.total_amount
    returning id
)
insert into store_transaction_items (transaction_id, item_name, quantity, unit, unit_price, subtotal)
select id, 'Rice', 5.00, 'kg', 60.00, 300.00 from base_tx
where not exists (select 1 from store_transaction_items where transaction_id = base_tx.id and item_name = 'Rice')
union all
select id, 'Oil', 1.00, 'L', 180.00, 180.00 from base_tx
where not exists (select 1 from store_transaction_items where transaction_id = base_tx.id and item_name = 'Oil');

insert into monthly_settlements (farmer_id, settlement_month, milk_total, store_credit_total, net_amount, status, is_locked, settled_on, note)
select id, date_trunc('month', current_date)::date, 430.50, 480.00, -49.50, 'Farmer Owes', true, now(), 'Seed settlement'
from farmers
where unique_code = 1
on conflict (farmer_id, settlement_month) do nothing;

insert into payment_logs (farmer_id, payment_date, amount, direction, note)
select id, current_date, 49.50, 'from_farmer', 'Seed recovery entry'
from farmers
where unique_code = 1;
