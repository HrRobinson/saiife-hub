import { Geist, Geist_Mono } from "next/font/google";
import localFont from "next/font/local";

import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { AppThemeProvider } from "@/lib/theme";

const display = localFont({
  src: "./fonts/ClashDisplay-Variable.woff2",
  weight: "700",
  display: "swap",
  variable: "--font-display",
});
const sans = Geist({ subsets: ["latin"], variable: "--font-sans-src" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono-src" });

export const metadata = {
  title: "saiife hub",
  description: "Hosted webhook ingress for your saiife install.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen antialiased">
        <AppThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </AppThemeProvider>
      </body>
    </html>
  );
}
