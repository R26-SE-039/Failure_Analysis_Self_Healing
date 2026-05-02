import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NEXTGEN QA Dashboard",
  description: "Failure Analysis and Self-Healing Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}