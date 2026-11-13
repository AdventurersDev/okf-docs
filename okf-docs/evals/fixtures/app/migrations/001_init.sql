create table invoices (
  id uuid primary key default gen_random_uuid(),
  customer_id text not null,
  amount_cents integer not null check (amount_cents > 0),
  issued_at timestamptz not null default now(),
  paid_at timestamptz
);

create table reminders (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references invoices (id),
  sent_at timestamptz not null default now()
);
