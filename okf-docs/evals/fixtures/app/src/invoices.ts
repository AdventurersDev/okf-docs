import pg from "pg";

const db = new pg.Pool({ connectionString: process.env.DATABASE_URL });

export const DAYS_UNTIL_LATE = 30;
export const LATE_FEE_RATE = 0.02; // 2% of the amount, charged once
export const MAX_REMINDERS = 3;

export type Invoice = {
  id: string;
  customerId: string;
  amountCents: number;
  issuedAt: Date;
  paidAt: Date | null;
};

export async function listInvoices(): Promise<Invoice[]> {
  const { rows } = await db.query("select * from invoices order by issued_at desc");
  return rows;
}

export async function getInvoice(id: string): Promise<Invoice | null> {
  const { rows } = await db.query("select * from invoices where id = $1", [id]);
  return rows[0] ?? null;
}

export async function createInvoice(input: { customerId: string; amountCents: number }): Promise<Invoice> {
  const { rows } = await db.query(
    "insert into invoices (customer_id, amount_cents) values ($1, $2) returning *",
    [input.customerId, input.amountCents],
  );
  return rows[0];
}

export async function payInvoice(id: string): Promise<Invoice> {
  const { rows } = await db.query("update invoices set paid_at = now() where id = $1 returning *", [id]);
  return rows[0];
}

export function lateFeeCents(invoice: Invoice, today: Date): number {
  if (invoice.paidAt) return 0;
  const days = (today.getTime() - invoice.issuedAt.getTime()) / 86_400_000;
  return days > DAYS_UNTIL_LATE ? Math.round(invoice.amountCents * LATE_FEE_RATE) : 0;
}
