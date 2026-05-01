import { drizzle } from "drizzle-orm/neon-http";
import { neon } from "@neondatabase/serverless";

// Drizzle handle scoped to the auth tables. The rest of the app reads/writes
// via the raw template-tag client in app/lib/db.ts. Keeping these separate
// means the project stays raw-SQL by default; Drizzle is here only because
// Better Auth's adapter needs typed schema bindings.
const conn = neon(process.env.DATABASE_URL!);
export const dbDrizzle = drizzle(conn);
