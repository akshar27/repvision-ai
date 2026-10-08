import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Activity } from "lucide-react";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "RepVision AI",
  description: "Pose-based rep counting and movement feedback for squats, push-ups and pull-ups.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans">
        <header className="border-b border-line/70 backdrop-blur sticky top-0 z-10 bg-bg/70">
          <nav className="mx-auto max-w-6xl px-4 h-14 flex items-center justify-between" aria-label="Main">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <Activity className="text-accent" size={20} aria-hidden /> RepVision<span className="text-accent">AI</span>
            </Link>
            <div className="flex gap-5 text-sm text-muted">
              <Link href="/" className="hover:text-ink">Analyze video</Link>
              <Link href="/webcam" className="hover:text-ink">Webcam</Link>
              <a href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/docs`} className="hover:text-ink" target="_blank" rel="noreferrer">API docs</a>
            </div>
          </nav>
        </header>
        <main className="flex-1 mx-auto w-full max-w-6xl px-4 py-8">{children}</main>
        <footer className="border-t border-line/70 text-xs text-muted">
          <p className="mx-auto max-w-6xl px-4 py-5">
            RepVision AI gives <strong>estimated</strong> movement feedback from 2D pose estimation. It is not a medical
            assessment, injury-risk diagnosis, or guarantee of exercise safety or technique quality.
          </p>
        </footer>
      </body>
    </html>
  );
}
