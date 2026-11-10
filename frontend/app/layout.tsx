import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans_Thai } from "next/font/google";

import { Providers } from "./providers";
import "./globals.css";

const plexSansThai = IBM_Plex_Sans_Thai({
  variable: "--font-sans",
  subsets: ["thai", "latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "AURA OFFICE AI",
    template: "%s · AURA OFFICE AI",
  },
  description: "แพลตฟอร์มบริหารจัดการงานสำนักงานด้วย AI สำหรับองค์กร",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="th" className={`${plexSansThai.variable} ${plexMono.variable} h-full antialiased`}>
      <body className="bg-background min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
