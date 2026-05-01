import { redirect } from "next/navigation";

// /recap is an alias for /brief — kept because users naturally type both.
export default function RecapPage() {
  redirect("/brief");
}
