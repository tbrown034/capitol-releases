import { redirect } from "next/navigation";

export const metadata = {
  title: "Methodology · Capitol Releases",
  description: "Redirects to the Capitol Releases methodology and about page.",
};

export default async function MethodologyRedirect({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const params = await searchParams;
  const qs = params.sort ? `?sort=${params.sort}` : "";
  redirect(`/about${qs}`);
}
