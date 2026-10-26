# Indicative Cost for IBEDC Resources Utilization

**Status:** Indicative — confirm against actual Hostinger invoice
**Date:** 11 September 2026
**FX rate used:** ₦1,332 / $1 (official/mid-market, 9 Sept 2026 — see Sources)

What the ERP tool's hosting and file-storage footprint costs on the Hostinger VPS it runs on, converted to Naira. Built from a live read of the server and the staging database, priced against Hostinger's public rate card.

---

## 01 — Headline estimate

Two ways to attribute the VPS bill, depending on whether the server is dedicated to this tool or shared with other work. Both use the server's current disk footprint (**46% used**) as the allocation basis — see §04.

| Scenario | Promo rate | Renewal rate |
|---|---|---|
| **Dedicated** — whole VPS is this tool's cost | ₦18,635 /mo | ₦38,615 /mo |
| **Shared, by usage** — 46% of the VPS bill | ₦8,572 /mo | ₦17,763 /mo |

*(Dedicated = full plan cost. Shared = plan cost × 46% disk-usage share.)*

---

## 02 — Server specification

**Hostinger KVM 4**

| Item | Value |
|---|---|
| Plan | KVM 4 — 4 vCPU · 16 GB RAM |
| Allocated storage | 200 GB NVMe (204,800 MB) |
| Usable filesystem | 193 GB |
| Disk used / free | 88 GB used · 106 GB free (≈46%) |
| Bandwidth allowance | 16 TB / cycle |
| Bandwidth used | 134,578 MB (≈0.82%) |

Bandwidth is a rounding error at 0.82% of allowance — disk footprint is the only allocation basis worth using.

---

## 03 — What's actually in the uploads folder

Queried the `attachments` table directly (staging database, read-only): **15 files, 2.02 MB total** — 13 JPEGs, 2 PDFs. Against 88 GB of disk in use, that's effectively nothing.

Which means the 88 GB isn't mostly IBEDC document storage — it's the OS, Docker images/layers, the Postgres database itself, and logs. If the real goal is costing *document storage* specifically rather than the server as a whole, that number will stay negligible until production accumulates real file volume.

---

## 04 — Cost calculation

| Basis | Monthly | Annual | ₦ / GB / mo |
|---|---|---|---|
| Promo (intro term) | ₦18,635 | ₦223,616 | ₦93 |
| Renewal (standard) | ₦38,615 | ₦463,376 | ₦193 |

Shared-allocation row in §01 = rate × 46% disk share:

| Basis | Monthly | Annual |
|---|---|---|
| Promo, shared | ₦8,572 | ₦102,863 |
| Renewal, shared | ₦17,763 | ₦213,153 |

The ₦/GB figure lets you re-project this as production storage grows — e.g. 10 GB of real documents would be ≈₦930–₦1,930/mo of shared VPS cost, on top of whatever baseline the server already carries.

---

## 05 — Assumptions to confirm before this goes to IBEDC

- **Pricing is a public list price, not your invoice.** Hostinger's advertised KVM 4 rate as of Sept 2026 — your actual billed amount (currency, term, any add-ons) should replace it for a final figure.
- **FX rate will move.** ₦1,332/$1 was the official/mid-market rate on 9 Sept 2026; the parallel-market rate that day was closer to ₦1,410/$1. Re-check the rate at time of invoicing — Naira volatility means this can shift materially.
- **Only staging was queried.** No production DB credentials on this machine — if production holds materially more files, the §03 figure understates real document storage.
- **Dedicated vs. shared was never confirmed.** Whether anything besides this ERP tool runs on the VPS decides which row in §01 applies — worth a direct answer rather than an assumption.
- **88 GB is whole-server disk, not document storage.** Don't present it to IBEDC as "their" file volume — §03's 2.02 MB is the actual attachment footprint today.

---

## Sources

- [Hostinger VPS Hosting — plan pricing](https://www.hostinger.com/vps-hosting)
- [HostAdvice — Hostinger VPS renewal pricing](https://hostadvice.com/hosting-company/hostinger-reviews/vps-pricing/)
- [XE — USD to NGN](https://www.xe.com/en-us/currencyconverter/convert/?Amount=1&From=USD&To=NGN)
