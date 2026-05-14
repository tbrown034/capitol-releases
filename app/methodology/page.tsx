import { redirect } from "next/navigation";

export default async function MethodologyRedirect({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const params = await searchParams;
  const qs = params.sort ? `?sort=${params.sort}` : "";
  redirect(`/about${qs}`);
}
