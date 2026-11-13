import Fastify from "fastify";
import { createInvoice, listInvoices, payInvoice } from "./invoices.js";

const app = Fastify({ logger: true });

app.get("/invoices", async () => listInvoices());

app.post("/invoices", async (req, reply) => {
  const invoice = await createInvoice(req.body as { customerId: string; amountCents: number });
  return reply.code(201).send(invoice);
});

app.post("/invoices/:id/pay", async (req) => {
  const { id } = req.params as { id: string };
  return payInvoice(id);
});

app.listen({ port: Number(process.env.PORT ?? 3000), host: "0.0.0.0" });
