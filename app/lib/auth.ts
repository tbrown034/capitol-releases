import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { dbDrizzle } from "./db-drizzle";
import * as schema from "./auth-schema";

// No fallback: a deployment without ADMIN_EMAIL gets no admin, not a
// default identity baked into source. isAdmin fails closed on undefined.
const ADMIN_EMAIL = process.env.ADMIN_EMAIL;

export const auth = betterAuth({
  trustedOrigins: [
    "http://localhost:3003",
    "https://capitolreleases.com",
    "https://www.capitolreleases.com",
    ...(process.env.VERCEL_URL ? [`https://${process.env.VERCEL_URL}`] : []),
  ],
  database: drizzleAdapter(dbDrizzle, {
    provider: "pg",
    schema,
  }),
  emailAndPassword: {
    enabled: true,
  },
  socialProviders: {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID as string,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET as string,
    },
  },
  user: {
    additionalFields: {
      tier: {
        type: "string",
        defaultValue: "free",
        input: false,
      },
    },
  },
  plugins: [nextCookies()],
});

export function isAdmin(email: string | undefined | null): boolean {
  return Boolean(ADMIN_EMAIL) && email === ADMIN_EMAIL;
}
