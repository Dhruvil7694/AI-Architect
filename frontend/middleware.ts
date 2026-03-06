import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED_PATH_PREFIXES = [
  "/dashboard",
  "/planner",
  "/plots",
  "/users",
  "/admin",
];

const LOGIN_PATH = "/login";
const DEFAULT_AUTHENTICATED_REDIRECT = "/dashboard";
const ACCESS_TOKEN_COOKIE = "access_token";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const accessToken = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;

  const isProtected = PROTECTED_PATH_PREFIXES.some((path) =>
    pathname.startsWith(path),
  );

  const isLoginRoute = pathname === LOGIN_PATH;

  if (isProtected && !accessToken) {
    const loginUrl = new URL(LOGIN_PATH, request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (isLoginRoute && accessToken) {
    const targetUrl = new URL(DEFAULT_AUTHENTICATED_REDIRECT, request.url);
    return NextResponse.redirect(targetUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/login",
    "/dashboard/:path*",
    "/planner/:path*",
    "/plots/:path*",
    "/users/:path*",
    "/admin/:path*",
  ],
};

