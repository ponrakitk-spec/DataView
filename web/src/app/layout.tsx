import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DataView by Cheese Ponrakit",
  description: "วิเคราะห์ยอดวิว YouTube, TikTok และ Facebook Reels จากลิงก์ช่องหรือโปรไฟล์ โดย Cheese Ponrakit",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="th"><body>{children}</body></html>;
}
