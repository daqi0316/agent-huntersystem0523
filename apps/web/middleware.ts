import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = [
  "/login",
  "/register",
  "/help",
  "/pricing",
  "/blog",
  "/cases",
  "/integrations",
  "/legal/terms-of-service",
  "/legal/privacy-policy",
  "/legal/data-processing-agreement",
  "/_next",
  "/api",
  "/favicon.ico",
  "/robots.txt",
  "/sitemap.xml",
];

const PUBLIC_PREFIXES = ["/_next/", "/api/", "/legal/"];

function is_public(pathname: string): boolean {
  if (PUBLIC_PATHS.includes(pathname)) return true;
  return PUBLIC_PREFIXES.some((p) => pathname.startsWith(p));
}

export function middleware(request: NextRequest) {
  const token = request.cookies.get("ai-recruitment-token")?.value;
  const { pathname } = request.nextUrl;

  if (is_public(pathname)) {
    return NextResponse.next();
  }

  if (!token) {
    const login_url = new URL("/login", request.url);
    login_url.searchParams.set("redirect", pathname);
    return NextResponse.redirect(login_url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
