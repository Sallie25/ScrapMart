import localFont from "next/font/local";
import { Welcome } from "@/components/landing/welcome";
import "@/components/landing/landing.css";

const dmSans = localFont({
  src: "./fonts/dm-sans.woff2",
  weight: "400 800",
  variable: "--font-landing-dm-sans",
  display: "swap",
});
const manrope = localFont({
  src: "./fonts/manrope.woff2",
  weight: "600 800",
  variable: "--font-landing-manrope",
  display: "swap",
});

export default function Home() {
  return (
    <div className={`${dmSans.variable} ${manrope.variable}`}>
      <Welcome />
    </div>
  );
}
