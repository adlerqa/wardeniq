/** Number formats shared by the job logs, the usage screen and cost estimates. */

/** 12345 → "12,345" in the browser's locale. */
export const fmtTok = (n) => Number(n || 0).toLocaleString();

/** Dollars, 4 decimals under $1, else 2; "—" when unknown. */
export const fmtUsd = (c) => (c == null ? "—" : "$" + Number(c).toFixed(Number(c) < 1 ? 4 : 2));
