"use client";

import { HeroContent } from "./HeroContent";
import { HeroImage } from "./HeroImage";

export function HeroSection() {
  return (
    <section className="relative flex-1 grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-6 items-center px-8 md:px-12 lg:px-16 py-4 lg:py-0 min-h-[calc(100vh-160px)]">
      {/* Left: Text content */}
      <div className="flex flex-col justify-center order-2 lg:order-1">
        <HeroContent />
      </div>

      {/* Right: House image */}
      <div className="flex items-center justify-center order-1 lg:order-2 lg:h-full">
        <HeroImage />
      </div>
    </section>
  );
}
