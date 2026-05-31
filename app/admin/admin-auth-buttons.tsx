"use client";

import { signIn, signOut } from "@/app/lib/auth-client";

export function SignInButton() {
  return (
    <button
      type="button"
      onClick={async () => {
        const res = await signIn.social({
          provider: "google",
          callbackURL: "/admin",
        });
        if (res?.data?.url) window.location.href = res.data.url;
      }}
      className="w-full rounded-md border border-neutral-300 bg-white px-4 py-2.5 text-sm font-medium text-neutral-900 hover:bg-neutral-50 transition-colors cursor-pointer"
    >
      Sign in with Google
    </button>
  );
}

export function SignOutButton({ redirectTo = "/" }: { redirectTo?: string }) {
  return (
    <button
      type="button"
      onClick={async () => {
        await signOut();
        window.location.href = redirectTo;
      }}
      className="text-sm text-neutral-600 hover:text-neutral-900 underline cursor-pointer"
    >
      Sign out
    </button>
  );
}
