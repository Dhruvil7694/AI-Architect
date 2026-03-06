import { redirect } from "next/navigation";

export default function Home() {
  // Once authentication is wired, this can route based on session state.
  redirect("/dashboard");
}

