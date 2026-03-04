import type { Metadata } from "next";
import { Geist } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { Providers } from "@/components/Providers";

const geist = Geist({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Trading Crew Dashboard",
  description: "Real-time monitoring for the Trading Crew multi-agent system",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/orders", label: "Orders" },
  { href: "/signals", label: "Signals" },
  { href: "/history", label: "History" },
  { href: "/agents", label: "Agents" },
  { href: "/backtest", label: "Backtest" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geist.className} bg-gray-50 text-gray-900 antialiased`}>
        <Providers>
          <div className="flex min-h-screen">
            {/* Sidebar */}
            <aside className="w-52 shrink-0 border-r border-gray-200 bg-white">
              <div className="flex h-14 items-center border-b border-gray-100 px-4">
                <span className="font-bold text-indigo-600">Trading Crew</span>
              </div>
              <nav className="mt-2 px-2">
                {NAV.map((n) => (
                  <Link
                    key={n.href}
                    href={n.href}
                    className="flex items-center rounded-lg px-3 py-2 text-sm font-medium text-gray-600 hover:bg-indigo-50 hover:text-indigo-700"
                  >
                    {n.label}
                  </Link>
                ))}
              </nav>
            </aside>
            {/* Main content */}
            <main className="flex-1 overflow-y-auto p-6">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
