import { redirect } from "next/navigation";

export const metadata = {
  title: "Recap · Capitol Releases",
  description: "Redirects dated recap URLs to the daily brief archive.",
};

export const revalidate = 3600;

export default async function RecapDatePage({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const { date } = await params;
  redirect(`/brief/${date}`);
}
