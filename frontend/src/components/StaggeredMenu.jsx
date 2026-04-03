"use client";

import React, { useCallback, useLayoutEffect, useEffect, useRef, useState, cloneElement, isValidElement } from 'react';
import Link from 'next/link';
import { gsap } from 'gsap';
import GlassSurface from './GlassSurface';
import { useSidebarNavigation } from '@/modules/navigation/useSidebarNavigation';
import { useAuthStore } from '@/state/authStore';
import { NavNode } from '@/modules/navigation/navigationTree';

function getBrandOrangeFromCss() {
  if (typeof document === 'undefined') return '#ff5900';
  return getComputedStyle(document.documentElement).getPropertyValue('--brand-orange').trim() || '#ff5900';
}

export const StaggeredMenu = ({
  position = 'right',
  colors = ['#B19EEF', '#5227FF'],
  items = [],
  isAuthenticated = false,
  socialItems = [],
  displaySocials = true,
  displayItemNumbering = true,
  className,
  logoUrl = '/src/assets/logos/reactbits-gh-white.svg',
  menuButtonColor,
  openMenuButtonColor = '#fff',
  accentColor,
  changeMenuColorOnOpen = true,
  isFixed = false,
  closeOnClickAway = true,
  onMenuOpen,
  onMenuClose,
  open: controlledOpen,
  onOpenChange,
  hideHeader = false,
  trigger = null
}) => {
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = controlledOpen !== undefined && onOpenChange != null;
  const open = isControlled ? controlledOpen : internalOpen;
  const setOpen = isControlled ? (v) => onOpenChange?.(v) : setInternalOpen;
  const openRef = useRef(false);
  const panelRef = useRef(null);
  const preLayersRef = useRef(null);
  const preLayerElsRef = useRef([]);
  const plusHRef = useRef(null);
  const plusVRef = useRef(null);
  const iconRef = useRef(null);
  const textInnerRef = useRef(null);
  const textWrapRef = useRef(null);
  const [textLines, setTextLines] = useState(['Menu', 'Close']);

  const openTlRef = useRef(null);
  const closeTweenRef = useRef(null);
  const spinTweenRef = useRef(null);
  const textCycleAnimRef = useRef(null);
  const colorTweenRef = useRef(null);
  const toggleBtnRef = useRef(null);
  const busyRef = useRef(false);
  const itemEntranceTweenRef = useRef(null);

  const resolvedMenuColor = menuButtonColor ?? getBrandOrangeFromCss();
  const resolvedAccent = accentColor ?? 'var(--brand-orange)';
  const logoColor = menuButtonColor ?? 'var(--brand-orange)';

  const { currentLevel, currentTitle, canGoBack, goForward, goBack } = useSidebarNavigation();
  const { logout, user } = useAuthStore();
  const isAdmin = user?.roles?.includes('admin') ?? false;

  const useIsomorphicLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect;

  useIsomorphicLayoutEffect(() => {
    const ctx = gsap.context(() => {
      const panel = panelRef.current;
      const preContainer = preLayersRef.current;
      const plusH = plusHRef.current;
      const plusV = plusVRef.current;
      const icon = iconRef.current;
      const textInner = textInnerRef.current;

      const offscreen = position === 'left' ? -100 : 100;

      // Always set panel (and prelayers) offscreen when closed — required when hideHeader (icon refs are null)
      if (panel) {
        let preLayers = [];
        if (preContainer) {
          preLayers = Array.from(preContainer.querySelectorAll('.sm-prelayer'));
        }
        preLayerElsRef.current = preLayers;
        gsap.set([panel, ...preLayers], { xPercent: offscreen });
      }

      if (plusH) gsap.set(plusH, { transformOrigin: '50% 50%', rotate: 0 });
      if (plusV) gsap.set(plusV, { transformOrigin: '50% 50%', rotate: 90 });
      if (icon) gsap.set(icon, { rotate: 0, transformOrigin: '50% 50%' });
      if (textInner) gsap.set(textInner, { yPercent: 0 });
      if (toggleBtnRef.current) gsap.set(toggleBtnRef.current, { color: resolvedMenuColor });
    });
    return () => ctx.revert();
  }, [resolvedMenuColor, position]);

  const buildOpenTimeline = useCallback(() => {
    const panel = panelRef.current;
    const layers = preLayerElsRef.current;
    if (!panel) return null;

    openTlRef.current?.kill();
    if (closeTweenRef.current) {
      closeTweenRef.current.kill();
      closeTweenRef.current = null;
    }
    itemEntranceTweenRef.current?.kill();

    const itemEls = Array.from(panel.querySelectorAll('.sm-panel-itemLabel'));
    const numberEls = Array.from(panel.querySelectorAll('.sm-panel-list[data-numbering] .sm-panel-item'));
    const socialTitle = panel.querySelector('.sm-socials-title');
    const socialLinks = Array.from(panel.querySelectorAll('.sm-socials-link'));

    const layerStates = layers.map(el => ({ el, start: Number(gsap.getProperty(el, 'xPercent')) }));
    const panelStart = Number(gsap.getProperty(panel, 'xPercent'));

    if (itemEls.length) {
      gsap.set(itemEls, { yPercent: 140, rotate: 10 });
    }
    if (numberEls.length) {
      gsap.set(numberEls, { '--sm-num-opacity': 0 });
    }
    if (socialTitle) {
      gsap.set(socialTitle, { opacity: 0 });
    }
    if (socialLinks.length) {
      gsap.set(socialLinks, { y: 25, opacity: 0 });
    }

    const tl = gsap.timeline({ paused: true });

    layerStates.forEach((ls, i) => {
      tl.fromTo(ls.el, { xPercent: ls.start }, { xPercent: 0, duration: 0.5, ease: 'power4.out' }, i * 0.07);
    });
    const lastTime = layerStates.length ? (layerStates.length - 1) * 0.07 : 0;
    const panelInsertTime = lastTime + (layerStates.length ? 0.08 : 0);
    const panelDuration = 0.65;
    tl.fromTo(
      panel,
      { xPercent: panelStart },
      { xPercent: 0, duration: panelDuration, ease: 'power4.out' },
      panelInsertTime
    );

    if (itemEls.length) {
      const itemsStartRatio = 0.15;
      const itemsStart = panelInsertTime + panelDuration * itemsStartRatio;
      tl.to(
        itemEls,
        {
          yPercent: 0,
          rotate: 0,
          duration: 1,
          ease: 'power4.out',
          stagger: { each: 0.1, from: 'start' }
        },
        itemsStart
      );
      if (numberEls.length) {
        tl.to(
          numberEls,
          {
            duration: 0.6,
            ease: 'power2.out',
            '--sm-num-opacity': 1,
            stagger: { each: 0.08, from: 'start' }
          },
          itemsStart + 0.1
        );
      }
    }

    if (socialTitle || socialLinks.length) {
      const socialsStart = panelInsertTime + panelDuration * 0.4;
      if (socialTitle) {
        tl.to(
          socialTitle,
          {
            opacity: 1,
            duration: 0.5,
            ease: 'power2.out'
          },
          socialsStart
        );
      }
      if (socialLinks.length) {
        tl.to(
          socialLinks,
          {
            y: 0,
            opacity: 1,
            duration: 0.55,
            ease: 'power3.out',
            stagger: { each: 0.08, from: 'start' },
            onComplete: () => {
              gsap.set(socialLinks, { clearProps: 'opacity' });
            }
          },
          socialsStart + 0.04
        );
      }
    }

    openTlRef.current = tl;
    return tl;
  }, []);

  const playOpen = useCallback(() => {
    if (busyRef.current) return;
    busyRef.current = true;
    const tl = buildOpenTimeline();
    if (tl) {
      tl.eventCallback('onComplete', () => {
        busyRef.current = false;
      });
      tl.play(0);
    } else {
      busyRef.current = false;
    }
  }, [buildOpenTimeline]);

  const playClose = useCallback(() => {
    openTlRef.current?.kill();
    openTlRef.current = null;
    itemEntranceTweenRef.current?.kill();

    const panel = panelRef.current;
    const layers = preLayerElsRef.current;
    if (!panel) return;

    const all = [...layers, panel];
    closeTweenRef.current?.kill();
    const offscreen = position === 'left' ? -100 : 100;
    closeTweenRef.current = gsap.to(all, {
      xPercent: offscreen,
      duration: 0.32,
      ease: 'power3.in',
      overwrite: 'auto',
      onComplete: () => {
        const itemEls = Array.from(panel.querySelectorAll('.sm-panel-itemLabel'));
        if (itemEls.length) {
          gsap.set(itemEls, { yPercent: 140, rotate: 10 });
        }
        const numberEls = Array.from(panel.querySelectorAll('.sm-panel-list[data-numbering] .sm-panel-item'));
        if (numberEls.length) {
          gsap.set(numberEls, { '--sm-num-opacity': 0 });
        }
        const socialTitle = panel.querySelector('.sm-socials-title');
        const socialLinks = Array.from(panel.querySelectorAll('.sm-socials-link'));
        if (socialTitle) gsap.set(socialTitle, { opacity: 0 });
        if (socialLinks.length) gsap.set(socialLinks, { y: 25, opacity: 0 });
        busyRef.current = false;
      }
    });
  }, [position]);

  const animateIcon = useCallback(opening => {
    const icon = iconRef.current;
    if (!icon) return;
    spinTweenRef.current?.kill();
    if (opening) {
      spinTweenRef.current = gsap.to(icon, { rotate: 225, duration: 0.8, ease: 'power4.out', overwrite: 'auto' });
    } else {
      spinTweenRef.current = gsap.to(icon, { rotate: 0, duration: 0.35, ease: 'power3.inOut', overwrite: 'auto' });
    }
  }, []);

  const animateColor = useCallback(
    opening => {
      const btn = toggleBtnRef.current;
      if (!btn) return;
      colorTweenRef.current?.kill();
      if (changeMenuColorOnOpen) {
        const targetColor = opening ? openMenuButtonColor : resolvedMenuColor;
        colorTweenRef.current = gsap.to(btn, {
          color: targetColor,
          delay: 0.18,
          duration: 0.3,
          ease: 'power2.out'
        });
      } else {
        gsap.set(btn, { color: resolvedMenuColor });
      }
    },
    [openMenuButtonColor, resolvedMenuColor, changeMenuColorOnOpen]
  );

  React.useEffect(() => {
    if (toggleBtnRef.current) {
      if (changeMenuColorOnOpen) {
        const targetColor = openRef.current ? openMenuButtonColor : resolvedMenuColor;
        gsap.set(toggleBtnRef.current, { color: targetColor });
      } else {
        gsap.set(toggleBtnRef.current, { color: resolvedMenuColor });
      }
    }
  }, [changeMenuColorOnOpen, resolvedMenuColor, openMenuButtonColor]);

  const animateText = useCallback(opening => {
    const inner = textInnerRef.current;
    if (!inner) return;
    textCycleAnimRef.current?.kill();

    const currentLabel = opening ? 'Menu' : 'Close';
    const targetLabel = 'Menu';
    const cycles = 3;
    const seq = [currentLabel];
    let last = currentLabel;
    for (let i = 0; i < cycles; i++) {
      last = last === 'Menu' ? 'Close' : 'Menu';
      seq.push(last);
    }
    if (last !== targetLabel) seq.push(targetLabel);
    seq.push(targetLabel);
    setTextLines(seq);

    gsap.set(inner, { yPercent: 0 });
    const lineCount = seq.length;
    const finalShift = ((lineCount - 1) / lineCount) * 100;
    textCycleAnimRef.current = gsap.to(inner, {
      yPercent: -finalShift,
      duration: 0.5 + lineCount * 0.07,
      ease: 'power4.out'
    });
  }, []);

  const toggleMenu = useCallback(() => {
    const target = !openRef.current;
    openRef.current = target;
    setOpen(target);
    if (target) {
      onMenuOpen?.();
      playOpen();
    } else {
      onMenuClose?.();
      playClose();
    }
    animateIcon(target);
    animateColor(target);
    animateText(target);
  }, [playOpen, playClose, animateIcon, animateColor, animateText, onMenuOpen, onMenuClose]);

  const closeMenu = useCallback(() => {
    if (openRef.current) {
      openRef.current = false;
      setOpen(false);
      onMenuClose?.();
      playClose();
      animateIcon(false);
      animateColor(false);
      animateText(false);
    }
  }, [setOpen, playClose, animateIcon, animateColor, animateText, onMenuClose]);

  React.useEffect(() => {
    openRef.current = open;
  }, [open]);

  // When open is false, force panel offscreen so it can't stay stuck visible (e.g. if animation failed or controlled state was reset)
  React.useEffect(() => {
    if (!open) {
      const panel = panelRef.current;
      const layers = preLayerElsRef.current;
      if (panel) {
        const offscreen = position === 'left' ? -100 : 100;
        gsap.set([panel, ...(layers || [])], { xPercent: offscreen });
      }
    }
  }, [open, position]);

  React.useEffect(() => {
    if (!closeOnClickAway || !open) return;

    const handleClickOutside = event => {
      const triggerEl = hideHeader ? document.querySelector('.staggered-menu-external-trigger') : toggleBtnRef.current;
      if (
        panelRef.current &&
        !panelRef.current.contains(event.target) &&
        triggerEl &&
        !triggerEl.contains(event.target)
      ) {
        closeMenu();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [closeOnClickAway, open, closeMenu, hideHeader]);

  const handleTriggerClick = useCallback(() => {
    if (isControlled && onOpenChange) onOpenChange(true);
    else setInternalOpen(true);
    onMenuOpen?.();
    openRef.current = true;
    playOpen();
    animateIcon(true);
    animateColor(true);
    animateText(true);
  }, [isControlled, onOpenChange, onMenuOpen, playOpen, animateIcon, animateColor, animateText]);

  return (
    <div
      className={(className ? className + ' ' : '') + 'staggered-menu-wrapper' + (isFixed ? ' fixed-wrapper' : '') + (hideHeader ? ' staggered-menu-embedded' : '') + (hideHeader && trigger ? ' staggered-menu-has-trigger' : '')}
      style={{ ['--sm-accent']: resolvedAccent }}
      data-position={position}
      data-open={open || undefined}
    >
      {hideHeader && trigger && isValidElement(trigger) && (
        <div className="staggered-menu-external-trigger" style={{ pointerEvents: 'auto', display: 'inline-flex' }}>
          {cloneElement(trigger, {
            onClick: (e) => {
              handleTriggerClick();
              trigger.props.onClick?.(e);
            },
          })}
        </div>
      )}
      <div ref={preLayersRef} className="sm-prelayers" aria-hidden="true">
        {(() => {
          const raw = colors && colors.length ? colors.slice(0, 4) : ['#1e1e22', '#35353c'];
          let arr = [...raw];
          if (arr.length >= 3) {
            const mid = Math.floor(arr.length / 2);
            arr.splice(mid, 1);
          }
          return arr.map((c, i) => <div key={i} className="sm-prelayer" style={{ background: c }} />);
        })()}
      </div>
      {!hideHeader && (
      <header className="staggered-menu-header" aria-label="Main navigation header">
        <div className="sm-logo" aria-label="Logo" onClick={() => window.location.href = '/'} style={{ cursor: 'pointer' }}>
          <GlassSurface 
            width="auto"
            height="auto"
            borderRadius={100}
            borderWidth={0}
            displace={0.5}
            distortionScale={-180}
            redOffset={0}
            greenOffset={10}
            blueOffset={20}
            brightness={open ? 10 : 110}
            opacity={0.8}
            mixBlendMode="screen"
          >
            <div style={{ padding: '12px 24px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {logoUrl && logoUrl.includes('reactbits') ? ( // Only use default logo if it's the placeholder
              <span style={{ 
                fontSize: '22px', 
                fontWeight: '850', 
                color: logoColor,
                letterSpacing: '-1.2px', 
                transition: 'color 0.3s ease'
               }}>Formless architects</span>
            ) : logoUrl ? (
              <img
                src={logoUrl}
                alt="Logo"
                className="sm-logo-img"
                draggable={false}
                width={110}
                height={24}
                style={{ filter: changeMenuColorOnOpen && open ? 'invert(1)' : 'none' }}
              />
            ) : (
              <span style={{ 
                fontSize: '22px', 
                fontWeight: '850', 
                color: logoColor,
                letterSpacing: '-1.2px', 
                transition: 'color 0.3s ease'
               }}>Formless architects</span>
            )}
            </div>
          </GlassSurface>
        </div>

        {/* Only show open trigger when menu is closed. Close is handled only by the X inside the panel. */}
        {!open && (
          <button
            ref={toggleBtnRef}
            className="sm-toggle"
            aria-label="Open menu"
            aria-expanded={false}
            aria-controls="staggered-menu-panel"
            onClick={toggleMenu}
            type="button"
          >
            <GlassSurface 
              width="auto"
              height="auto"
              borderRadius={8}
              borderWidth={0}
              displace={0.5}
              distortionScale={-180}
              redOffset={0}
              greenOffset={10}
              blueOffset={20}
              brightness={110}
              opacity={0.9}
              mixBlendMode="screen"
              style={{ border: '1px solid rgba(255, 255, 255, 0.2)' }}
            >
              <div style={{ padding: '12px 24px', display: 'inline-flex', alignItems: 'center', gap: '10px', justifyContent: 'center' }}>
                <span ref={textWrapRef} className="sm-toggle-textWrap" aria-hidden="true">
                  <span ref={textInnerRef} className="sm-toggle-textInner">
                    <span className="sm-toggle-line">Menu</span>
                  </span>
                </span>
                <span ref={iconRef} className="sm-icon" aria-hidden="true">
                  <span ref={plusHRef} className="sm-icon-line" />
                  <span ref={plusVRef} className="sm-icon-line sm-icon-line-v" />
                </span>
              </div>
            </GlassSurface>
          </button>
        )}
      </header>
      )}

      <aside id="staggered-menu-panel" ref={panelRef} className="staggered-menu-panel" aria-hidden={!open}>
        <div className="sm-panel-inner">
          {open && (
            <div className="flex w-full self-stretch items-center justify-end gap-2 p-4 pb-0">
              <span className="flex-1 min-w-0" aria-hidden />
              <div className="sm-socials-list flex items-center gap-2 shrink-0" role="list">
              {isAuthenticated && (
                <>
                  <Link
                    href="/profile"
                    className="sm-socials-link"
                    aria-label="Profile"
                    style={{ background: 'transparent', padding: 0 }}
                    onClick={() => { if (isControlled && onOpenChange) onOpenChange(false); closeMenu(); }}
                  >
                    <GlassSurface
                      width={44}
                      height={44}
                      borderRadius={100}
                      borderWidth={0}
                      displace={0.5}
                      distortionScale={-180}
                      redOffset={0}
                      greenOffset={10}
                      blueOffset={20}
                      brightness={10}
                      opacity={0.8}
                      mixBlendMode="screen"
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(255, 255, 255, 0.3)' }}
                    >
                      <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                    </GlassSurface>
                  </Link>
                  {isAdmin && (
                    <Link
                      href="/admin"
                      className="sm-socials-link"
                      aria-label="Admin"
                      style={{ background: 'transparent', padding: 0 }}
                      onClick={() => { if (isControlled && onOpenChange) onOpenChange(false); closeMenu(); }}
                    >
                      <GlassSurface
                        width={44}
                        height={44}
                        borderRadius={100}
                        borderWidth={0}
                        displace={0.5}
                        distortionScale={-180}
                        redOffset={0}
                        greenOffset={10}
                        blueOffset={20}
                        brightness={10}
                        opacity={0.8}
                        mixBlendMode="screen"
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(255, 255, 255, 0.3)' }}
                      >
                        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                      </GlassSurface>
                    </Link>
                  )}
                </>
              )}
              <button
                type="button"
                className="sm-socials-link"
                style={{ background: 'transparent', padding: 0, border: 'none', cursor: 'pointer' }}
                onClick={() => {
                  if (isControlled && onOpenChange) onOpenChange(false);
                  closeMenu();
                }}
                aria-label="Close menu"
              >
                <GlassSurface
                  width={44}
                  height={44}
                  borderRadius={100}
                  borderWidth={0}
                  displace={0.5}
                  distortionScale={-180}
                  redOffset={0}
                  greenOffset={10}
                  blueOffset={20}
                  brightness={10}
                  opacity={0.8}
                  mixBlendMode="screen"
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(255, 255, 255, 0.3)' }}
                >
                  <svg className="w-5 h-5 text-white transition-transform duration-150 active:scale-90 active:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5} aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </GlassSurface>
              </button>
              </div>
            </div>
          )}
          <ul className="sm-panel-list" role="list" data-numbering={displayItemNumbering || undefined}>
            {canGoBack && (
              <li className="sm-panel-itemWrap w-full">
                <button 
                  onClick={goBack}
                  className="sm-panel-item flex items-center gap-2 text-white/60 hover:text-white"
                  style={{ fontSize: '1.5rem', marginBottom: '1rem', padding: 0 }}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                  Back to {currentTitle === "AI Planner" || currentTitle === "AI Interior" ? "Main Menu" : "Previous"}
                </button>
              </li>
            )}
            
            {(() => {
              let displayItems = [...(currentLevel || [])];
              
              // If we are at the root level, we can inject/manage basic links
              // This ensures we have Home, Sign In/Up, etc.
              if (!canGoBack) {
                // Profile is only in the top-right icon; do not add it to the nav list.
                const hasAuthItems = displayItems.some(it => it.key === 'auth' || it.key === 'profile');
                if (!hasAuthItems && !isAuthenticated) {
                  displayItems.push({ title: "Sign In", key: "login", href: "/login" });
                }
              }

              return displayItems.map((it, idx) => (
                <li className="sm-panel-itemWrap" key={it.key + idx}>
                  <a 
                    className="sm-panel-item sm-panel-item-flex" 
                    href={it.href || "#"} 
                    aria-label={it.title} 
                    onClick={(e) => {
                      if (it.children && it.children.length > 0) {
                        e.preventDefault();
                        goForward(it);
                      }
                    }}
                  >
                    <span className="sm-panel-itemLabel">{it.title}</span>
                    {it.children && it.children.length > 0 && (
                      <span className="sm-arrow-wrap">
                        <span className="sm-arrow">→</span>
                      </span>
                    )}
                  </a>
                </li>
              ));
            })()}
          </ul>
          <footer className="sm-footer">
            {displaySocials && socialItems && socialItems.length > 0 && (
              <div className="sm-socials" aria-label="Social links">
                <h3 className="sm-socials-title">Follow Us</h3>
                <ul className="sm-socials-list" role="list">
                  {socialItems.map((s, i) => (
                    <li key={s.label + i} className="sm-socials-item">
                      <a href={s.link} target="_blank" rel="noopener noreferrer" className="sm-socials-link" aria-label={s.label} style={{ background: 'transparent', padding: 0 }}>
                        <GlassSurface 
                          width={44}
                          height={44}
                          borderRadius={100}
                          borderWidth={0}
                          displace={0.5}
                          distortionScale={-180}
                          redOffset={0}
                          greenOffset={10}
                          blueOffset={20}
                          brightness={10}
                          opacity={0.8}
                          mixBlendMode="screen"
                          style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(255, 255, 255, 0.3)' }}
                        >
                          {s.icon ? s.icon : s.label}
                        </GlassSurface>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="sm-auth-actions">
              {isAuthenticated ? (
                <button 
                  onClick={() => {
                    logout();
                    window.location.href = '/login';
                  }}
                  className="sm-auth-btn"
                >
                  Logout
                </button>
              ) : (
                <a href="/login" className="sm-auth-btn" style={{ background: 'white', color: '#ff5900', borderColor: 'white' }}>
                  Sign In / Sign Up
                </a>
              )}
            </div>
          </footer>
        </div>
      </aside>
    </div>
  );
};

export default StaggeredMenu;
