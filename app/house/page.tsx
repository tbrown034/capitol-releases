import { redirect } from "next/navigation";

export const metadata = {
  title: "House · Capitol Releases",
  description: "Redirects to the U.S. House member directory.",
};

export const revalidate = 3600;

export default function HouseDirectoryRedirect() {
  redirect("/members/house");
}
