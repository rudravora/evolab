import { Landing } from "@/components/landing/Landing";
import "../landing.css";

// Sign-in: the landing page with the sign-in card already open. lib/api sends signed-out
// visitors here as /login?next=<page>; after signing in they return to that page.
export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string | string[] }> }) {
  const { next } = await searchParams;
  return <Landing openAccess next={typeof next === "string" ? next : undefined} />;
}
