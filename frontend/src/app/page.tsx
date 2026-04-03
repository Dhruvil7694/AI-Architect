"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import ArchitectLoader from "@/components/ArchitectLoader";
import Link from "next/link";
import { useAuthStore } from "@/state/authStore";


import { 
  Sparkles, 
  Pencil, 
  Camera, 
  ArrowRight, 
  Plus, 
  Twitter, 
  Facebook, 
  Instagram, 
  Linkedin,
  Map,
  Check,
  TrendingUp,
  Users,
  Zap,
  Clock,
  Globe,
  Star
} from "lucide-react";
import SpotlightCard from "@/components/SpotlightCard";
import Masonry from "@/components/Masonry";
import Silk from "@/components/Silk";
import CurvedLoop from "@/components/CurvedLoop";
import StaggeredMenu from "@/components/StaggeredMenu";
import TextPressure from "@/components/TextPressure";
import FlowingMenu from "@/components/FlowingMenu";

const fadeIn: any = {
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.8, ease: "easeOut" }
};

export default function Home() {
  const { isAuthenticated, user } = useAuthStore();
  const [loading, setLoading] = useState(true);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const flowingMenuItems: Array<{ link: string; text: string; image: string }> = [
    { link: '#', text: 'Generative Floor Plans', image: '/floor_plan_ultra_hd.png' },
    { link: '#', text: 'Instant 3D Renderings', image: '/interior_render_1.png' },
    { link: '#', text: 'Iterative Editing', image: '/architectural_sketch_1.png' },
    { link: '#', text: 'Build-Ready Exports', image: '/10-Best-Modern-Architecture-Proj.png' },
    { link: '#', text: 'Structural Analysis', image: '/floor_plan_1.png' }
  ];

  const faqs = [
    { q: "What is Elevation Studio?", a: "Elevation Studio is a generative AI platform built specifically for architects, designers, and builders. It automates residential floor plan generation, letting you explore endless layouts in minutes." },
    { q: "How does it work?", a: "Simply input your project requirements—such as lot size, desired rooms, and square footage. Our AI instantly generates multiple floor plan variations that fit your constraints." },
    { q: "Can AI really generate floor plans?", a: "Yes. Unlike ChatGPT, Elevation Studio is purpose-built for architecture. Our generative AI creates real, editable floorplans for home design with accurate dimensions." },
    { q: "Is Elevation Studio free to try?", a: "We offer an early-access tier that allows you to explore the basic generation tools. Advanced editing and high-resolution exports are part of our premium studio offerings." },
    { q: "Do I need architecture experience?", a: "No. While Elevation Studio gives professionals powerful tools to speed up their workflow, our intuitive interface is designed so anyone can explore and iterate on residential designs." }
  ];

  const galleryItems = [
    { id: "1", img: "/floor_plan_ultra_hd.png", url: "#", height: 600 },
    { id: "2", img: "/interior_render_1.png", url: "#", height: 400 },
    { id: "3", img: "/3.png", url: "#", height: 500 },
    { id: "4", img: "/architectural_sketch_1.png", url: "#", height: 350 },
    { id: "5", img: "/A-3-bedroom-house-plan-with-an-a.png", url: "#", height: 450 },
    { id: "6", img: "/w991x660.png", url: "#", height: 400 },
    { id: "7", img: "/floor_plan_1.png", url: "#", height: 550 },
    { id: "8", img: "/1.png", url: "#", height: 650 },
    { id: "9", img: "/23841-1-1200.png", url: "#", height: 380 },
    { id: "10", img: "/4.png", url: "#", height: 420 },
    { id: "11", img: "/06694d32f44c05d1e1dd2bb341695090.png", url: "#", height: 520 },
    { id: "12", img: "/10-Best-Modern-Architecture-Proj.png", url: "#", height: 480 },
    { id: "13", img: "/11.png", url: "#", height: 360 },
    { id: "14", img: "/AD_4nXc-xXRWFRGRDzJg-gh2nsGLHzVO.png", url: "#", height: 580 },
    { id: "15", img: "/Arch2O-8-buildings-architects-dr.png", url: "#", height: 440 },
    { id: "16", img: "/MOSCOW,%20RUSSIA,%20postcard%20view%20of.png", url: "#", height: 410 },
    { id: "17", img: "/Sydney%20Opera%20House-1.png", url: "#", height: 620 },
    { id: "18", img: "/b1a641de222ffe1e1e8cc8f339958faf.png", url: "#", height: 390 },
    { id: "19", img: "/blany-floorplan-1024x585.png", url: "#", height: 510 },
    { id: "20", img: "/catgusto_01.png", url: "#", height: 570 },
    { id: "21", img: "/shutterstock_1257310975%201.png", url: "#", height: 460 }
  ];

  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 2000);
    return () => clearTimeout(timer);
  }, []);

  if (loading) return <ArchitectLoader label="Entering AI Architect Studio..." />;

  return (
    <div className="home-wrapper">

      {/* ── Navigation (Staggered Menu) ── */}
      <StaggeredMenu
        position="right"
        isFixed={true}
        isAuthenticated={isAuthenticated}
        onMenuOpen={() => setIsMenuOpen(true)}
        onMenuClose={() => setIsMenuOpen(false)}
        socialItems={[
          { label: 'Twitter', link: '#', icon: <Twitter size={20} style={{ display: 'block' }}/> },
          { label: 'LinkedIn', link: '#', icon: <Linkedin size={20} style={{ display: 'block' }}/> },
          { label: 'Instagram', link: '#', icon: <Instagram size={20} style={{ display: 'block' }}/> }
        ] as any}
        displaySocials={true}
        className=""
        displayItemNumbering={false}
        openMenuButtonColor="#fff"
        changeMenuColorOnOpen={true}
        colors={['#ff9c63', '#ff5900']}
        logoUrl=""
      />

      <div style={{
          filter: isMenuOpen ? 'blur(15px)' : 'none',
          transition: 'filter 0.5s ease',
          pointerEvents: isMenuOpen ? 'none' : 'auto',
          willChange: 'filter',
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center'
      }}>
        {/* ── Hero ── */}
        <section className="home-hero" style={{ maxWidth: '100%', padding: '20px 24px 60px 24px', marginTop: '160px' }}>
          <motion.div 
            className="home-hero-title-interactive" 
            style={{ 
              position: 'relative', 
              width: '100%', 
              height: '45vh', 
              minHeight: '200px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              gap: '10px'
            }} 
            {...fadeIn}
          >
            <div style={{ position: 'relative', width: '100%', flex: 1 }}>
              <TextPressure
                text="ELEVATION"
                flex={true}
                alpha={false}
                stroke={false}
                width={true}
                weight={true}
                italic={true}
                textColor="#000"
                strokeColor="#ff5900"
                minFontSize={36}
              />
            </div>
            <div style={{ position: 'relative', width: '100%', flex: 1 }}>
              <TextPressure
                text="STUDIO"
                flex={true}
                alpha={false}
                stroke={false}
                width={true}
                weight={true}
                italic={true}
                textColor="#000"
                strokeColor="#ff5900"
                minFontSize={36}
              />
            </div>
          </motion.div>
        </section>

      {/* ── Studio Gallery (GSAP Masonry) ── */}
      <section className="gallery-section">
        <Masonry 
          items={galleryItems} 
          ease="power3.out"
          duration={0.8}
          stagger={0.06}
          animateFrom="bottom"
          scaleOnHover={true}
          hoverScale={0.98}
          blurToFocus={true}
          colorShiftOnHover={false}
        />
      </section>

      {/* ── Curved Loop Marquee & CTA ── */}
      <section className="marquee-section">
        <div className="marquee-content">
          <div className="marquee-badge">Powering the future of Design</div>
          <h2>Join the absolute best workflow<br/>for modern architects.</h2>
          <p>Go from idea to rendering in under 5 minutes without opening a single CAD program. Trusted by over 100,000 architectural studios.</p>
        </div>
        <CurvedLoop 
          marqueeText="ARCHITECTURE ✦ GENERATIVE DESIGN ✦ ITERATION ✦ INTELLIGENCE ✦ 3D VISUALIZATION ✦"
          speed={1.5}
          curveAmount={300}
          direction="right"
          interactive={true}
          className="marquee-black-text"
        />
      </section>

      {/* ── Features Bento Grid ── */}
      <section className="features-section">
        <div className="features-header">
          <h2>An ecosystem built for scale.</h2>
          <p>Everything you need to conceptualize, iterate, and present world-class architecture in a fraction of the time.</p>
        </div>
      </section>

      {/* ── Flowing Menu Full Bleed ── */}
      <section style={{ maxWidth: '100%', padding: 0 }}>
        <div style={{ height: '750px', width: '100vw', position: 'relative', overflow: 'hidden' }}>
          <FlowingMenu 
            items={flowingMenuItems as any}
            speed={15}
            textColor="#ffffff"
            bgColor="#000"
            marqueeBgColor="#ff5900"
            marqueeTextColor="#fff"
            borderColor="#333"
          />
        </div>
      </section>

      {/* ── Anyone Can Design ── */}
      <section className="anyone-section">
        <motion.h2 className="sub-title" {...fadeIn}>Anyone can design a home</motion.h2>
        <motion.p className="home-hero-desc" {...fadeIn}>
          More than 1M people used Elevation Studio v1. <br />
          v2 is almost here: smarter, more flexible, and radically simple.
        </motion.p>
        <motion.div {...fadeIn} transition={{ delay: 0.2 }} style={{ marginTop: '30px' }}>
          <Link href="/signup" className="home-nav-cta" style={{ transform: 'scale(1.1)', padding: '14px 30px' }}>
            Get early access <ArrowRight size={18} />
          </Link>
        </motion.div>
      </section>

      {/* ── Stats Bento Grid ── */}
      <section className="stats-bento-section">
        <div className="stats-bento-header">
          <span className="stats-bento-label">By the numbers</span>
          <h2>Platform impact,<br/>at a glance</h2>
          <p>Real data from architects, designers, and homebuilders using Elevation Studio every day.</p>
        </div>

        <div className="stats-bento-grid">

          {/* Card 1 — Floor Plans (large, spans 2 rows & 2 cols) */}
          <motion.div className="sbc sbc-purple sbc-large" {...fadeIn}>
            <SpotlightCard className="sbc-spotlight sbc-spotlight-flex" spotlightColor="rgba(139,92,246,0.25)">
              <div className="sbc-chip"><TrendingUp size={13}/> Designs Generated</div>
              <div className="sbc-number">8M+</div>
              <div className="sbc-title">Floor plans created</div>
              <p className="sbc-desc">From quick sketches to detailed layouts — generated in minutes, ready to refine.</p>
              <div className="sbc-sparkline sbc-sparkline-large">
                <svg viewBox="0 0 120 40" style={{ display: 'block' }}>
                  <defs>
                    <linearGradient id="gPurple" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.4"/>
                      <stop offset="100%" stopColor="#a78bfa" stopOpacity="0"/>
                    </linearGradient>
                  </defs>
                  <path d="M0,36 C15,35 25,28 40,24 C55,20 60,26 75,18 C90,10 105,6 120,2" stroke="#a78bfa" strokeWidth="2" fill="none" strokeLinecap="round"/>
                  <path d="M0,36 C15,35 25,28 40,24 C55,20 60,26 75,18 C90,10 105,6 120,2 L120,40 L0,40 Z" fill="url(#gPurple)"/>
                </svg>
              </div>
              <div style={{ marginTop: 'auto', paddingTop: '16px' }}>
                <div className="sbc-trend"><TrendingUp size={14}/> +34% vs last year</div>
              </div>
            </SpotlightCard>
          </motion.div>

          {/* Card 2 — Spaces Imagined */}
          <motion.div className="sbc sbc-peach" {...fadeIn} transition={{ delay: 0.1 }}>
            <SpotlightCard className="sbc-spotlight" spotlightColor="rgba(251,146,60,0.2)">
              <div className="sbc-chip"><Camera size={13}/> Renders</div>
              <div className="sbc-number">6M+</div>
              <div className="sbc-title">Spaces imagined</div>
              <p className="sbc-desc">Photorealistic renders — bringing design concepts to life before a single brick is laid.</p>
              <div className="sbc-bars">
                {[
                  { label: 'Living', pct: 88 },
                  { label: 'Bedroom', pct: 72 },
                  { label: 'Kitchen', pct: 65 },
                  { label: 'Outdoor', pct: 49 },
                ].map(b => (
                  <div key={b.label} className="sbc-bar-row">
                    <span>{b.label}</span>
                    <div className="sbc-bar-track">
                      <div className="sbc-bar-fill sbc-bar-orange" style={{ width: `${b.pct}%` }}/>
                    </div>
                    <span className="sbc-bar-pct">{b.pct}%</span>
                  </div>
                ))}
              </div>
            </SpotlightCard>
          </motion.div>

          {/* Card 3 — Users */}
          <motion.div className="sbc sbc-dark" {...fadeIn} transition={{ delay: 0.15 }}>
            <SpotlightCard className="sbc-spotlight" spotlightColor="rgba(0,229,255,0.15)">
              <div className="sbc-chip sbc-chip-light"><Users size={13}/> Community</div>
              <div className="sbc-number sbc-number-light">1M+</div>
              <div className="sbc-title sbc-title-light">Users onboarded</div>
              <p className="sbc-desc sbc-desc-light">Homeowners, builders, and real estate pros planning smarter with AI.</p>
              <div className="sbc-donut-wrap">
                <svg viewBox="0 0 80 80" className="sbc-donut">
                  <circle cx="40" cy="40" r="30" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10"/>
                  <circle cx="40" cy="40" r="30" fill="none" stroke="#7dd3fc" strokeWidth="10"
                    strokeDasharray="113 75" strokeLinecap="round"
                    transform="rotate(-90 40 40)"/>
                  <circle cx="40" cy="40" r="30" fill="none" stroke="#34d399" strokeWidth="10"
                    strokeDasharray="56 132" strokeLinecap="round"
                    transform="rotate(60 40 40)"/>
                  <circle cx="40" cy="40" r="30" fill="none" stroke="#f472b6" strokeWidth="10"
                    strokeDasharray="19 169" strokeLinecap="round"
                    transform="rotate(168 40 40)"/>
                </svg>
                <div className="sbc-donut-legend">
                  <div className="sbc-legend-row"><span className="sbc-dot" style={{background:'#7dd3fc'}}/> Homeowners 60%</div>
                  <div className="sbc-legend-row"><span className="sbc-dot" style={{background:'#34d399'}}/> Builders 30%</div>
                  <div className="sbc-legend-row"><span className="sbc-dot" style={{background:'#f472b6'}}/> Realtors 10%</div>
                </div>
              </div>
            </SpotlightCard>
          </motion.div>

          {/* Card 4 — Generation Speed */}
          <motion.div className="sbc sbc-teal" {...fadeIn} transition={{ delay: 0.2 }}>
            <SpotlightCard className="sbc-spotlight" spotlightColor="rgba(52,211,153,0.2)">
              <div className="sbc-chip"><Zap size={13}/> Performance</div>
              <div className="sbc-number">4.2s</div>
              <div className="sbc-title">Avg. generation time</div>
              <p className="sbc-desc">From prompt to floor plan — faster than brewing a cup of coffee.</p>
              <div className="sbc-speed-track">
                <div className="sbc-speed-label"><span>0s</span><span>10s</span></div>
                <div className="sbc-speed-bar-wrap">
                  <div className="sbc-speed-fill" style={{ width: '42%' }}/>
                  <div className="sbc-speed-marker" style={{ left: '42%' }}/>
                </div>
              </div>
              <div className="sbc-stat-row">
                <div className="sbc-mini-stat"><div className="sbc-mini-num">99.6%</div><div className="sbc-mini-lbl">Uptime</div></div>
                <div className="sbc-mini-stat"><div className="sbc-mini-num">12M</div><div className="sbc-mini-lbl">API calls/mo</div></div>
              </div>
            </SpotlightCard>
          </motion.div>

          {/* Card 5 — Global Reach (wide) */}
          <motion.div className="sbc sbc-slate sbc-wide" {...fadeIn} transition={{ delay: 0.25 }}>
            <SpotlightCard className="sbc-spotlight" spotlightColor="rgba(148,163,184,0.15)">
              <div className="sbc-chip"><Globe size={13}/> Global</div>
              <div className="sbc-number">180+</div>
              <div className="sbc-title">Countries</div>
              <p className="sbc-desc">Elevation Studio is used by designers worldwide, from São Paulo to Singapore.</p>
              <div className="sbc-activity">
                {Array.from({ length: 28 }).map((_, i) => (
                  <div key={i} className="sbc-activity-col">
                    {Array.from({ length: 5 }).map((_, j) => {
                      const intensity = Math.random();
                      const bg = intensity > 0.7 ? '#6366f1' : intensity > 0.4 ? '#a5b4fc' : intensity > 0.2 ? '#e0e7ff' : '#f1f5f9';
                      return <div key={j} className="sbc-activity-cell" style={{ background: bg }}/>
                    })}
                  </div>
                ))}
              </div>
              <p className="sbc-activity-caption">Contribution map — last 28 days</p>
            </SpotlightCard>
          </motion.div>

          {/* Card 6 — Accuracy / Satisfaction */}
          <motion.div className="sbc sbc-amber" {...fadeIn} transition={{ delay: 0.3 }}>
            <SpotlightCard className="sbc-spotlight" spotlightColor="rgba(251,191,36,0.2)">
              <div className="sbc-chip"><Star size={13}/> Satisfaction</div>
              <div className="sbc-number">4.9★</div>
              <div className="sbc-title">User rating</div>
              <p className="sbc-desc">Rated by 120K+ architects, builders, and homeowners on the platform.</p>
              <div className="sbc-ratings">
                {[5,4,3,2,1].map((star, i) => {
                  const pcts = [76, 18, 4, 1, 1];
                  return (
                    <div key={star} className="sbc-rating-row">
                      <span>{star}★</span>
                      <div className="sbc-bar-track">
                        <div className="sbc-bar-fill sbc-bar-amber" style={{ width: `${pcts[i]}%` }}/>
                      </div>
                      <span className="sbc-bar-pct">{pcts[i]}%</span>
                    </div>
                  );
                })}
              </div>
            </SpotlightCard>
          </motion.div>

          {/* Card 7 — Time Saved */}
          <motion.div className="sbc sbc-dark sbc-wide2" {...fadeIn} transition={{ delay: 0.35 }}>
            <SpotlightCard className="sbc-spotlight" spotlightColor="rgba(99,102,241,0.2)">
              <div className="sbc-chip sbc-chip-light"><Clock size={13}/> Efficiency</div>
              <div className="sbc-number sbc-number-light">73%</div>
              <div className="sbc-title sbc-title-light">Time saved per project</div>
              <p className="sbc-desc sbc-desc-light">Architects report spending 73% less time on schematic design when using Elevation Studio vs traditional workflows.</p>
              <div className="sbc-compare">
                <div className="sbc-compare-row">
                  <span className="sbc-compare-label sbc-compare-label-light">Traditional CAD</span>
                  <div className="sbc-bar-track">
                    <div className="sbc-bar-fill sbc-bar-dimgray" style={{ width: '100%' }}/>
                  </div>
                  <span className="sbc-bar-pct sbc-bar-pct-light">48h</span>
                </div>
                <div className="sbc-compare-row">
                  <span className="sbc-compare-label sbc-compare-label-light">Elevation Studio</span>
                  <div className="sbc-bar-track">
                    <div className="sbc-bar-fill sbc-bar-indigo" style={{ width: '27%' }}/>
                  </div>
                  <span className="sbc-bar-pct sbc-bar-pct-light">13h</span>
                </div>
              </div>
              <div className="sbc-checks">
                {['AI-generated schematics', 'Instant iteration', 'One-click exports'].map(t => (
                  <div key={t} className="sbc-check-row"><Check size={13} color="#34d399"/> <span>{t}</span></div>
                ))}
              </div>
            </SpotlightCard>
          </motion.div>

        </div>
      </section>

      {/* ── FAQ ── */}
      <section>
        <div className="faq-wrap">
          <div>
            <h2 className="sub-title" style={{ fontSize: '36px' }}>Your questions, answered</h2>
            <p className="home-hero-desc" style={{ fontSize: '16px' }}>Get quick answers to the most common questions about our platform and services.</p>
            <button className="home-nav-link" style={{ border: '1px solid #000', padding: '8px 20px', borderRadius: '100px', cursor: 'pointer', background: 'transparent' }}>
              See all FAQs
            </button>
          </div>
          <div className="faq-list">
            {faqs.map((faq, i) => (
              <motion.div 
                key={i} 
                className={`faq-item ${openFaq === i ? 'open' : ''}`}
                onClick={() => setOpenFaq(openFaq === i ? null : i)}
                {...fadeIn} 
                transition={{ delay: i * 0.1 }}
              >
                <div className="faq-question">
                  {faq.q} 
                  <motion.div
                    animate={{ rotate: openFaq === i ? 45 : 0 }}
                    transition={{ duration: 0.2, ease: "easeInOut" }}
                  >
                    <Plus className="faq-plus" size={20} strokeWidth={1} />
                  </motion.div>
                </div>
                <motion.div 
                  className="faq-answer"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ 
                    height: openFaq === i ? 'auto' : 0,
                    opacity: openFaq === i ? 1 : 0,
                    marginTop: openFaq === i ? 16 : 0
                  }}
                  transition={{ duration: 0.3, ease: "easeInOut" }}
                >
                  {faq.a}
                </motion.div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="home-footer">
        <div className="footer-pattern">
          <Silk 
            speed={4} 
            scale={1} 
            color="#2a2b2e" 
            noiseIntensity={1.2} 
            rotation={1.5} 
          />
        </div>
        <div className="footer-top">
          <Link href="/planner" className="home-nav-cta" style={{ transform: 'scale(1.2)', background: '#fff', color: '#000' }}>
            Open Studio <ArrowRight size={18} />
          </Link>
          <div className="footer-links">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <Link href="/">Platform</Link>
              <Link href="/planner">Studio</Link>
              <Link href="/planner">Floor Plans</Link>
              <Link href="/planner">3D Renders</Link>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/pricing">Pricing</Link>
              <Link href="/contact">Support</Link>
            </div>
          </div>
        </div>
        <div className="footer-bottom">
          <div className="socials">
            <div className="social-circle"><Twitter size={14} /></div>
            <div className="social-circle"><Facebook size={14} /></div>
            <div className="social-circle"><Instagram size={14} /></div>
            <div className="social-circle"><Linkedin size={14} /></div>
            <div className="social-circle"><Map size={14} /></div>
          </div>
          <div className="footer-email">hello@aiarchitect.com</div>
        </div>
      </footer>
      </div>
    </div>
  );
}
