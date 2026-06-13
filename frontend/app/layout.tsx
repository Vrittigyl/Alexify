import type { Metadata } from "next";
import { Inter, Space_Grotesk, Space_Mono, Newsreader } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const spaceMono = Space_Mono({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-space-mono",
  display: "swap",
});

const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-newsreader",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SAATHI — AI Powered Home Intelligence",
  description:
    "We create a digital understanding of your household so everything works seamlessly for your family.",
  keywords: ["smart home", "AI", "home intelligence", "SAATHI"],
  openGraph: {
    title: "SAATHI — AI Powered Home Intelligence",
    description:
      "We create a digital understanding of your household so everything works seamlessly for your family.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${spaceGrotesk.variable} ${spaceMono.variable} ${newsreader.variable} h-full antialiased`}
    >
      <body
        className={`min-h-full ${spaceGrotesk.className}`}
      >
        {children}
      </body>
    </html>
  );
}
