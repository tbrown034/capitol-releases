import { redirect } from "next/navigation";

export const metadata = {
  title: "Recap · Capitol Releases",
  description: "Redirects to the Capitol Releases daily brief.",
};

// /recap is an alias for /brief — kept because users naturally type both.
export default function RecapPage() {
  redirect("/brief");
}
