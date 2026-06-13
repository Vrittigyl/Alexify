import { TopBrand } from "@/components/landing/TopBrand";
import { HeroSection } from "@/components/landing/HeroSection";
import { ProcessSteps } from "@/components/landing/ProcessSteps";
import { HouseholdStories } from "@/components/landing/HouseholdStories";
import { PrivacySection } from "@/components/landing/PrivacySection";
import { FutureVision } from "@/components/landing/FutureVision";
import { Footer } from "@/components/landing/Footer";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col overflow-hidden" style={{ backgroundColor: "#faf7f3" }}>
      {/* Header */}
      <TopBrand />

      {/* Hero: two-column layout */}
      <HeroSection />

      {/* Bottom process steps panel */}
      <section className="px-8 md:px-12 lg:px-16 pb-10 pt-4">
        <ProcessSteps />
      </section>

      {/* Real Household Stories */}
      <HouseholdStories />

      {/* Privacy Section */}
      <PrivacySection />

      {/* Future Vision & Closing Quote */}
      <FutureVision />

      {/* Footer */}
      <Footer />
    </main>
  );
}

