import { Cta } from "@/components/home/cta";
import { Hero } from "@/components/home/hero";
import { HowItWorks } from "@/components/home/how-it-works";
import { PartCatalog } from "@/components/home/part-catalog";
import { QuestionMarquee } from "@/components/home/question-marquee";
import { TrustBento } from "@/components/home/trust-bento";
import { Footer } from "@/components/site/footer";

export default function Home() {
  return (
    <>
      <Hero />
      <QuestionMarquee />
      <PartCatalog />
      <HowItWorks />
      <TrustBento />
      <Cta />
      <Footer />
    </>
  );
}
