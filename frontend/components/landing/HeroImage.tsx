"use client";

import { motion } from "framer-motion";
import Image from "next/image";

export function HeroImage() {
  return (
    <motion.div
      initial={{ opacity: 0, x: 40, y: 10 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ delay: 0.15, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
      className="relative flex items-center justify-center w-full h-full -translate-x-6 lg:-translate-x-12"
    >
      {/* Floor shadow to make it look grounded */}
      <div
        className="absolute bottom-[8%] left-1/2 -translate-x-1/2 w-[75%] h-[12%] bg-[#111827] opacity-20 blur-[24px] rounded-[100%] rotate-2 pointer-events-none"
      />

      {/* Image wrapper */}
      <div className="relative w-full z-10">
        <Image
          src="/images/house-updated.png"
          alt="3D isometric view of a modern smart home floor plan"
          width={1200}
          height={950}
          priority
          className="w-full h-auto object-contain scale-110 lg:scale-[1.2] origin-center rotate-2"
          style={{ maxHeight: "85vh" }}
        />
      </div>
    </motion.div>
  );
}
