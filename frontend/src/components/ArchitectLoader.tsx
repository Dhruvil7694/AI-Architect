"use client";

import { motion } from "framer-motion";

interface ArchitectLoaderProps {
  label?: string;
  fullscreen?: boolean;
}

export default function ArchitectLoader({ 
  label = "Processing Scenarios...", 
  fullscreen = true 
}: ArchitectLoaderProps) {
  
  const containerClasses = fullscreen 
    ? "architect-loader-overlay" 
    : "architect-loader-inline";

  return (
    <div className={containerClasses}>
      <div className="loader-visual-wrapper">
        <div className="loader-svg-container">
          <svg viewBox="0 0 100 100" className="architect-svg">
            <motion.path
              initial={{ opacity: 0 }}
              animate={{ opacity: [0, 0.2, 0.1] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
              d="M10 10 h80 v80 h-80 z M10 30 h80 M10 50 h80 M10 70 h80 M30 10 v80 M50 10 v80 M70 10 v80"
              stroke="#000"
              strokeWidth="0.2"
              fill="none"
            />
            
            <motion.path
              d="M25 75 L25 45 L50 25 L75 45 L75 75 Z"
              fill="none"
              stroke="#f97316"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ 
                pathLength: [0, 1, 1],
                opacity: [0, 1, 0],
              }}
              transition={{ 
                duration: 3, 
                repeat: Infinity, 
                ease: "easeInOut",
                times: [0, 0.8, 1] 
              }}
            />

            <motion.path
              d="M25 55 L75 55 M50 25 L50 75"
              fill="none"
              stroke="#000"
              strokeWidth="1"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ 
                pathLength: [0, 0, 1, 1],
                opacity: [0, 0, 0.4, 0]
              }}
              transition={{ 
                duration: 3, 
                repeat: Infinity, 
                ease: "easeInOut",
                times: [0, 0.4, 0.9, 1]
              }}
            />

            <motion.rect
              width="60"
              height="1"
              fill="url(#scanGradient)"
              x="20"
              initial={{ y: 20, opacity: 0 }}
              animate={{ 
                y: [20, 80],
                opacity: [0, 0.8, 0]
              }}
              transition={{ 
                duration: 2, 
                repeat: Infinity, 
                ease: "linear" 
              }}
            />

            <defs>
              <linearGradient id="scanGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="transparent" />
                <stop offset="50%" stopColor="#f97316" />
                <stop offset="100%" stopColor="transparent" />
              </linearGradient>
            </defs>
          </svg>

          <motion.div 
            className="loader-pulse"
            animate={{ scale: [1, 1.5], opacity: [0.3, 0] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: "easeOut" }}
          />
        </div>

        <div className="loader-text-area">
          <motion.h4
            animate={{ opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="loader-brand"
          >
            AI ARCHITECT
          </motion.h4>
          <p className="loader-label">{label}</p>
        </div>
      </div>
    </div>
  );
}
