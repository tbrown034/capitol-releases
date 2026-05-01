import { redirect } from "next/navigation";

export default async function RecapDatePage({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const { date } = await params;
  redirect(`/brief/${date}`);
}
