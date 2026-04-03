import type { Metadata } from "next";
import { Inter, Outfit } from "next/font/google";
import "./globals.css";

import { ReactQueryProvider } from "@/lib/react-query-provider";
import Toaster from "@/components/Toaster";
import CookieConsent from "@/components/CookieConsent";
import { AuthHydration } from "@/components/AuthHydration";
import { AuthGate } from "@/components/AuthGate";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Site Planning Dashboard",
  description:
    "Interactive AI-assisted architectural site planning dashboard for plots, metrics, geometry, and development scenarios.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} ${outfit.variable} antialiased font-sans`}
      >
        <ReactQueryProvider>
          <AuthHydration />
          <AuthGate>
            {children}
            <Toaster />
            <CookieConsent />
          </AuthGate>
        </ReactQueryProvider>
      </body>
    </html>
  );
}

