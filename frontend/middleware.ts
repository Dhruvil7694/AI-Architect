import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  // Session is HttpOnly; auth state is restored client-side via GET /api/auth/me
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/login",
    "/signup",
  ],
};
