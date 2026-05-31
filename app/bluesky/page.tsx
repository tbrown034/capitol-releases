import { redirect } from "next/navigation";

export const metadata = {
  title: "Bluesky · Capitol Releases",
  description: "Redirects to collected social posts from official accounts.",
};

export default function BlueskyPage() {
  redirect("/social");
}
