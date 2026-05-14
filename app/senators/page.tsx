import { redirect } from "next/navigation";

export default async function SenatorsDirectoryRedirect({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string; state?: string }>;
}) {
  const params = await searchParams;
  const sp = new URLSearchParams();
  if (params.sort) sp.set("sort", params.sort);
  if (params.state) sp.set("state", params.state);
  const qs = sp.toString();
  redirect(`/members/senate${qs ? `?${qs}` : ""}`);
}
